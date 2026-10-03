import os
import json
import logging
import asyncio
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from core import db, client, seed_admin, SOURCES_DIR
from ingestion import ingest_document, configure_module, rebuild_index
import routes_student
import routes_tutor
import routes_admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("server")

app = FastAPI(title="EASA Part-66 AI Study Assistant")
app.include_router(routes_admin.auth_router)
app.include_router(routes_admin.router)
app.include_router(routes_tutor.router)
app.include_router(routes_student.router)


@app.get("/api/")
async def root():
    return {"app": "EASA Part-66 AI Study Assistant", "status": "ok"}


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


async def first_run():
    """Provision manifest documents, ingest them and extract configuration (module stays inactive)."""
    manifest = json.loads((SOURCES_DIR / "manifest.json").read_text())
    for m in manifest:
        if not await db.documents.find_one({"filename": m["filename"]}):
            await routes_admin.register_document(m["filename"], m["document_type"], m.get("module"), m["title"])
    await db.documents.update_many({"ingestion_status": "processing"}, {"$set": {"ingestion_status": "pending"}})
    interrupted = await db.jobs.find({"status": {"$in": ["running", "queued"]}}, {"_id": 0}).to_list(20)
    await db.jobs.update_many({"status": {"$in": ["running", "queued"]}}, {"$set": {"status": "interrupted"}})
    pending = await db.documents.find({"ingestion_status": "pending"}, {"_id": 0}).sort("document_type", -1).to_list(50)
    pending.sort(key=lambda d: d["document_type"] != "easa_guideline")
    for d in pending:
        log.info("Ingesting %s", d["filename"])
        await ingest_document(d["document_id"])
    await rebuild_index()
    for m in manifest:
        if m["document_type"] != "module_content":
            continue
        if await db.exam_configs.count_documents({"module": m["module"]}) == 0:
            doc = await db.documents.find_one({"filename": m["filename"], "ingestion_status": "completed"}, {"_id": 0})
            if doc:
                await configure_module(m["module"], doc["document_id"])
                log.info("Module %s configuration extracted - awaiting administrator confirmation", m["module"])
    for j in interrupted:
        cfg = await db.exam_configs.find_one({"config_id": j["config_id"], "status": "confirmed"}, {"_id": 0})
        if j.get("exam_sets") and cfg:
            log.info("Resuming interrupted bank-fill job (%s exam sets)", j["exam_sets"])
            await routes_admin.create_job(cfg, routes_admin.GenIn(config_id=cfg["config_id"], exam_sets=j["exam_sets"]))
            break


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.chunks.create_index([("document_id", 1), ("submodule", 1), ("page_number", 1)])
    await db.questions.create_index([("config_id", 1), ("submodule", 1), ("status", 1)])
    await db.attempts.create_index([("profile_id", 1), ("module", 1)])
    await seed_admin()
    asyncio.create_task(first_run())


@app.on_event("shutdown")
async def shutdown():
    client.close()
