from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Response, BackgroundTasks
from pydantic import BaseModel
from core import db, SOURCES_DIR, now_iso, new_id, require_admin, verify_password, create_access_token
from ingestion import ingest_document, configure_module, rebuild_index, INDEX
from qgen import start_job, RUNNING

auth_router = APIRouter(prefix="/api/auth")
router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


class LoginIn(BaseModel):
    email: str
    password: str


@auth_router.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    ident = f"{request.client.host if request.client else 'x'}:{email}"
    rec = await db.login_attempts.find_one({"identifier": ident}, {"_id": 0})
    if rec and rec.get("count", 0) >= 5 and datetime.fromisoformat(rec["last"]) > datetime.now(timezone.utc) - timedelta(minutes=15):
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one({"identifier": ident}, {"$inc": {"count": 1}, "$set": {"last": now_iso()}}, upsert=True)
        raise HTTPException(401, "Invalid email or password")
    await db.login_attempts.delete_many({"identifier": ident})
    token = create_access_token(user["id"], email)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    return {"token": token, "user": {"id": user["id"], "email": email, "name": user["name"], "role": user["role"]}}


@auth_router.get("/me")
async def me(user=Depends(require_admin)):
    return user


@auth_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


# ---------------- Knowledge base ----------------
async def first_run_report(module):
    mod = await db.modules.find_one({"module": module}, {"_id": 0})
    g = await db.documents.find_one({"document_type": "easa_guideline", "active": True}, {"_id": 0})
    content = await db.documents.find_one({"document_id": (mod or {}).get("content_document_id")}, {"_id": 0}) if mod else None
    cfgs = await db.exam_configs.find({"module": module}, {"_id": 0}).to_list(20)
    cfg = next((c for c in cfgs if c["applies_to_content"]), None)
    validated = await db.questions.count_documents({"module": module, "status": "validated", "config_id": (cfg or {}).get("config_id")})
    retrieval = None
    if cfg:
        hits = {}
        for s in cfg["submodules"]:
            res, _ = INDEX.search(s["title"].replace("—", " "), module=module, submodule=s["parent_key"], k=1)
            hits[s["key"]] = bool(res)
        retrieval = {"ok": all(hits.values()), "per_submodule": hits}
    prereq = {
        "guideline_ingested": bool(g and g["ingestion_status"] == "completed"),
        "content_ingested": bool(content and content["ingestion_status"] == "completed" and content.get("active")),
        "configuration_extracted": bool(cfg),
        "knowledge_levels_valid": bool(cfg and cfg["knowledge_level_status"] == "VALID"),
        "distribution_valid": bool(cfg and cfg["distribution_status"] == "VALID"),
        "configuration_confirmed": bool(cfg and cfg["status"] == "confirmed"),
        "source_retrieval_functioning": bool(retrieval and retrieval["ok"]),
        "question_validation_functioning": validated > 0,
    }
    return {"module": module, "module_record": mod, "guideline": g, "content": content, "configs": cfgs, "config": cfg,
            "validated_questions": validated, "retrieval": retrieval, "prerequisites": prereq,
            "summary": {
                "guideline_processed": "YES" if prereq["guideline_ingested"] else "NO",
                "content_processed": "YES" if prereq["content_ingested"] else "NO",
                "module_detected": f"Module {module}" if cfg else None,
                "category_detected": cfg["course_category"] if cfg else None,
                "guideline_category_group": cfg["category_group"] if cfg else None,
                "question_count": cfg["question_count"] if cfg else None,
                "time_minutes": cfg["time_minutes"] if cfg else None,
                "format": f"{cfg['options_per_question']} alternatives / {cfg['correct_answers']} correct" if cfg else None,
                "pass_mark_percent": cfg["pass_mark_percent"] if cfg else None,
                "knowledge_level_status": cfg["knowledge_level_status"] if cfg else "INVALID",
                "distribution_status": cfg["distribution_status"] if cfg else "INVALID",
            }}


@router.get("/status")
async def kb_status():
    docs = await db.documents.find({}, {"_id": 0}).sort("provisioned_at", 1).to_list(200)
    mods = await db.modules.find({}, {"_id": 0}).sort("module", 1).to_list(50)
    counts = {}
    for m in mods:
        counts[m["module"]] = {s: await db.questions.count_documents({"module": m["module"], "status": s})
                               for s in ("validated", "rejected", "review_required")}
    flags = await db.flags.count_documents({"status": "open"})
    return {"documents": docs, "modules": mods, "question_counts": counts, "open_flags": flags}


@router.get("/files")
async def available_files():
    registered = {d["filename"] for d in await db.documents.find({}, {"_id": 0, "filename": 1}).to_list(500)}
    return [{"filename": p.name, "size": p.stat().st_size, "registered": p.name in registered}
            for p in sorted(SOURCES_DIR.glob("*.pdf"))]


class DocIn(BaseModel):
    filename: str
    document_type: str
    module: Optional[int] = None
    title: str


async def register_document(filename, document_type, module, title):
    prev = await db.documents.find({"document_type": document_type, "module": module}, {"_id": 0}).to_list(100)
    doc = {"document_id": new_id("doc"), "filename": filename, "document_type": document_type, "module": module, "title": title,
           "version": len(prev) + 1, "provisioned_at": now_iso(), "ingestion_status": "pending", "active": False,
           "authoritative": document_type in ("easa_guideline", "module_content")}
    await db.documents.insert_one(dict(doc))
    return doc


@router.post("/documents")
async def add_document(body: DocIn, bg: BackgroundTasks):
    if body.document_type not in ("easa_guideline", "module_content", "example_questions"):
        raise HTTPException(400, "Invalid document type")
    if not (SOURCES_DIR / body.filename).is_file() or "/" in body.filename:
        raise HTTPException(400, "File is not present in the backend sources directory")
    if body.document_type != "easa_guideline" and not body.module:
        raise HTTPException(400, "Module is required")
    doc = await register_document(body.filename, body.document_type, body.module, body.title)
    bg.add_task(ingest_document, doc["document_id"])
    doc.pop("_id", None)
    return doc


@router.post("/documents/{doc_id}/ingest")
async def reingest(doc_id: str, bg: BackgroundTasks):
    if not await db.documents.find_one({"document_id": doc_id}, {"_id": 0}):
        raise HTTPException(404, "Not found")
    bg.add_task(ingest_document, doc_id)
    return {"ok": True}


@router.post("/documents/{doc_id}/activate")
async def activate_document(doc_id: str):
    d = await db.documents.find_one({"document_id": doc_id}, {"_id": 0})
    if not d or d["ingestion_status"] != "completed":
        raise HTTPException(400, "Only successfully processed documents can be activated")
    await db.documents.update_many({"document_type": d["document_type"], "module": d.get("module")}, {"$set": {"active": False}})
    await db.documents.update_one({"document_id": doc_id}, {"$set": {"active": True, "activated_at": now_iso()}})
    await rebuild_index()
    return {"ok": True}


@router.get("/documents/{doc_id}/pages")
async def doc_pages(doc_id: str, submodule: Optional[str] = None, skip: int = 0, limit: int = 20):
    filt = {"document_id": doc_id}
    if submodule:
        filt["submodule"] = submodule
    total = await db.chunks.count_documents(filt)
    items = await db.chunks.find(filt, {"_id": 0}).sort("page_number", 1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": items}


# ---------------- Modules & configuration ----------------
class ConfigureIn(BaseModel):
    module: int
    content_document_id: str


@router.post("/modules/configure")
async def configure(body: ConfigureIn):
    mod = await db.modules.find_one({"module": body.module}, {"_id": 0})
    if mod and mod.get("status") == "active":
        raise HTTPException(400, "Deactivate the module before re-extracting its configuration")
    content = await db.documents.find_one({"document_id": body.content_document_id, "document_type": "module_content"}, {"_id": 0})
    if not content or content.get("module") != body.module or content["ingestion_status"] != "completed":
        raise HTTPException(400, "Select a processed content document for this module")
    await db.exam_configs.delete_many({"module": body.module})
    try:
        await configure_module(body.module, body.content_document_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return await first_run_report(body.module)


@router.get("/modules/{module}/report")
async def module_report(module: int):
    return await first_run_report(module)


@router.post("/configs/{config_id}/confirm")
async def confirm_config(config_id: str, user=Depends(require_admin)):
    cfg = await db.exam_configs.find_one({"config_id": config_id}, {"_id": 0})
    if not cfg:
        raise HTTPException(404, "Not found")
    if cfg["knowledge_level_status"] != "VALID" or cfg["distribution_status"] != "VALID":
        raise HTTPException(400, "Configuration has validation issues that require review")
    await db.exam_configs.update_one({"config_id": config_id}, {"$set": {"status": "confirmed", "confirmed_at": now_iso(), "confirmed_by": user["email"]}})
    return {"ok": True}


@router.post("/modules/{module}/activate")
async def activate_module(module: int, user=Depends(require_admin)):
    rep = await first_run_report(module)
    missing = [k for k, v in rep["prerequisites"].items() if not v]
    if missing:
        raise HTTPException(400, {"message": "Activation prerequisites not met", "missing": missing})
    await db.modules.update_one({"module": module}, {"$set": {"status": "active", "activated_at": now_iso(), "activated_by": user["email"]}})
    return {"ok": True}


@router.post("/modules/{module}/deactivate")
async def deactivate_module(module: int):
    await db.modules.update_one({"module": module}, {"$set": {"status": "inactive"}})
    return {"ok": True}


# ---------------- Question generation ----------------
class GenIn(BaseModel):
    config_id: str
    submodule: Optional[str] = None
    count: int = 3
    exam_sets: Optional[int] = None


@router.post("/generate")
async def generate(body: GenIn):
    cfg = await db.exam_configs.find_one({"config_id": body.config_id}, {"_id": 0})
    if not cfg or cfg["status"] != "confirmed":
        raise HTTPException(400, "Question generator is only active after the configuration is confirmed")
    if any(j for j in RUNNING):
        raise HTTPException(409, "A generation job is already running")
    targets = {}
    if body.exam_sets:
        for s in cfg["submodules"]:
            have = await db.questions.count_documents({"config_id": cfg["config_id"], "submodule": s["key"], "status": "validated"})
            targets[s["key"]] = max(0, s["questions"] * body.exam_sets - have)
    elif body.submodule:
        targets[body.submodule] = max(1, min(body.count, 15))
    else:
        targets = {s["key"]: max(1, min(body.count, 10)) for s in cfg["submodules"] if s["questions"]}
    job = {"job_id": new_id("job"), "config_id": cfg["config_id"], "module": cfg["module"], "targets": targets,
           "status": "queued", "log": [], "progress": {}, "totals": {"validated": 0, "rejected": 0}, "created_at": now_iso()}
    await db.jobs.insert_one(dict(job))
    start_job(job["job_id"])
    job.pop("_id", None)
    return job


@router.get("/jobs")
async def jobs():
    js = await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(20)
    for j in js:
        j["log"] = j.get("log", [])[-25:]
    return js


@router.get("/questions")
async def audit_questions(module: int = 3, status: Optional[str] = None, submodule: Optional[str] = None, limit: int = 200):
    filt = {"module": module}
    if status:
        filt["status"] = status
    if submodule:
        filt["submodule"] = submodule
    return await db.questions.find(filt, {"_id": 0}).sort("created_at", -1).to_list(limit)


class DecisionIn(BaseModel):
    decision: str
    note: Optional[str] = None


@router.post("/questions/{qid}/decision")
async def decide(qid: str, body: DecisionIn, user=Depends(require_admin)):
    q = await db.questions.find_one({"question_id": qid}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Not found")
    if body.decision == "approve" and q["validation"]["status"] != "PASS":
        raise HTTPException(400, "Only questions that passed validation can be approved")
    status = {"approve": "validated", "reject": "rejected"}.get(body.decision)
    if not status:
        raise HTTPException(400, "Invalid decision")
    await db.questions.update_one({"question_id": qid}, {"$set": {"status": status, "admin_decision": {
        "decision": body.decision, "note": body.note, "by": user["email"], "at": now_iso()}}})
    await db.flags.update_many({"question_id": qid, "status": "open"}, {"$set": {"status": "resolved", "resolution": body.decision}})
    return {"ok": True}


@router.get("/flags")
async def flags(status: str = "open"):
    return await db.flags.find({"status": status}, {"_id": 0}).sort("created_at", -1).to_list(500)


class ResolveIn(BaseModel):
    resolution: str


@router.post("/flags/{flag_id}/resolve")
async def resolve_flag(flag_id: str, body: ResolveIn, user=Depends(require_admin)):
    await db.flags.update_one({"flag_id": flag_id}, {"$set": {"status": "resolved", "resolution": body.resolution,
                                                             "resolved_by": user["email"], "resolved_at": now_iso()}})
    return {"ok": True}
