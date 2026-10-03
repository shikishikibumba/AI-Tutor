import math
import random
from datetime import datetime, timezone, timedelta, date
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import pymupdf
from core import db, PROFILE_ID, SOURCES_DIR, now_iso, new_id

router = APIRouter(prefix="/api")

PUBLIC_Q = {"_id": 0, "question_id": 1, "module": 1, "category": 1, "submodule": 1, "submodule_title": 1, "topic": 1,
            "knowledge_level": 1, "question_type": 1, "question_text": 1, "option_a": 1, "option_b": 1, "option_c": 1,
            "source_page": 1, "source_document_title": 1}


async def active_config(module: int):
    mod = await db.modules.find_one({"module": module, "status": "active"}, {"_id": 0})
    if not mod:
        raise HTTPException(404, "Module is not active")
    cfg = await db.exam_configs.find_one({"module": module, "status": "confirmed", "applies_to_content": True}, {"_id": 0})
    if not cfg:
        raise HTTPException(404, "No confirmed configuration")
    return mod, cfg


def source_info(q):
    return {"document_id": q.get("source_document_id"), "document_title": q.get("source_document_title"),
            "page": q.get("source_page"), "page_label": q.get("source_page_label"), "module": q.get("module"),
            "submodule": q.get("submodule"), "submodule_title": q.get("submodule_title"), "section": q.get("source_section"),
            "excerpt": q.get("supporting_quote"), "chunk_id": q.get("source_chunk_id")}


def reveal(q):
    return {"correct_answer": q["correct_answer"], "explanation": q.get("explanation"),
            "formula": q.get("formula_if_applicable"), "calculation_steps": q.get("calculation_steps_if_applicable"),
            "level_justification": q.get("level_justification"), "source": source_info(q), "source_issue": q.get("source_issue")}


def mistake_type_for(q, selected):
    for d in q.get("distractors") or []:
        if d.get("option") == selected:
            return d.get("error_type") or "Other"
    return "Other"


async def record_attempt(q, selected, mode, exam_id=None):
    correct = selected == q["correct_answer"]
    doc = {"attempt_id": new_id("att"), "profile_id": PROFILE_ID, "question_id": q["question_id"], "module": q["module"],
           "submodule": q["submodule"], "submodule_title": q["submodule_title"], "topic": q.get("topic"),
           "knowledge_level": q["knowledge_level"], "question_type": q.get("question_type"), "selected": selected,
           "correct": correct, "mistake_type": None if correct else mistake_type_for(q, selected), "mode": mode,
           "exam_id": exam_id, "created_at": now_iso()}
    await db.attempts.insert_one(dict(doc))
    return doc


# ---------------- Modules & config ----------------
@router.get("/modules")
async def list_modules():
    mods = await db.modules.find({"status": "active"}, {"_id": 0}).to_list(50)
    out = []
    for m in mods:
        cfg = await db.exam_configs.find_one({"module": m["module"], "status": "confirmed", "applies_to_content": True}, {"_id": 0})
        if cfg:
            out.append({"module": m["module"], "title": m["title"], "category": cfg["course_category"], "config": cfg})
    return out


@router.get("/modules/{module}/bank-readiness")
async def bank_readiness(module: int):
    _, cfg = await active_config(module)
    rows = []
    for s in cfg["submodules"]:
        n = await db.questions.count_documents({"config_id": cfg["config_id"], "submodule": s["key"], "status": "validated"})
        rows.append({"key": s["key"], "title": s["title"], "required": s["questions"], "available": n})
    return {"ready": all(r["available"] >= r["required"] for r in rows if r["required"]), "submodules": rows,
            "total_validated": sum(r["available"] for r in rows)}


# ---------------- Question bank ----------------
@router.get("/questions")
async def list_questions(module: int = 3, submodule: Optional[str] = None, level: Optional[int] = None,
                         question_type: Optional[str] = None, topic: Optional[str] = None, state: Optional[str] = None,
                         source_page: Optional[int] = None):
    _, cfg = await active_config(module)
    filt = {"config_id": cfg["config_id"], "status": "validated"}
    if submodule:
        filt["submodule"] = submodule
    if level:
        filt["knowledge_level"] = level
    if question_type:
        filt["question_type"] = question_type
    if topic:
        filt["topic"] = {"$regex": topic, "$options": "i"}
    if source_page:
        filt["source_page"] = source_page
    qs = await db.questions.find(filt, PUBLIC_Q).to_list(5000)
    atts = await db.attempts.find({"profile_id": PROFILE_ID, "module": module}, {"_id": 0}).sort("created_at", 1).to_list(50000)
    last = {}
    count = {}
    for a in atts:
        last[a["question_id"]] = a["correct"]
        count[a["question_id"]] = count.get(a["question_id"], 0) + 1
    for q in qs:
        q["attempts"] = count.get(q["question_id"], 0)
        q["last_result"] = None if q["question_id"] not in last else ("correct" if last[q["question_id"]] else "incorrect")
    if state == "attempted":
        qs = [q for q in qs if q["attempts"]]
    elif state == "unattempted":
        qs = [q for q in qs if not q["attempts"]]
    elif state in ("correct", "incorrect"):
        qs = [q for q in qs if q["last_result"] == state]
    order = {s["key"]: i for i, s in enumerate(cfg["submodules"])}
    qs.sort(key=lambda q: (order.get(q["submodule"], 99), q["knowledge_level"]))
    topics = sorted({q.get("topic") for q in qs if q.get("topic")})
    return {"questions": qs, "topics": topics, "applicable_levels": cfg["applicable_levels"]}


class AttemptIn(BaseModel):
    selected: str
    mode: str = "practice"


@router.get("/questions/{qid}")
async def get_question(qid: str):
    q = await db.questions.find_one({"question_id": qid, "status": "validated"}, PUBLIC_Q)
    if not q:
        raise HTTPException(404, "Question not found")
    return q


@router.post("/questions/{qid}/attempt")
async def attempt(qid: str, body: AttemptIn):
    if body.selected not in ("A", "B", "C"):
        raise HTTPException(400, "Answer must be A, B or C")
    q = await db.questions.find_one({"question_id": qid, "status": "validated"}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Question not found")
    a = await record_attempt(q, body.selected, body.mode if body.mode in ("practice", "bank", "tutor") else "practice")
    return {"correct": a["correct"], "selected": body.selected, "mistake_type": a["mistake_type"], "attempt_id": a["attempt_id"], **reveal(q)}


# ---------------- Adaptive practice ----------------
async def submodule_stats(module):
    atts = await db.attempts.find({"profile_id": PROFILE_ID, "module": module}, {"_id": 0}).to_list(50000)
    stats = {}
    for a in atts:
        s = stats.setdefault(a["submodule"], {"n": 0, "c": 0})
        s["n"] += 1
        s["c"] += a["correct"]
    return atts, stats


@router.get("/practice/next")
async def practice_next(module: int = 3, submodule: Optional[str] = None, level: Optional[int] = None, exclude: Optional[str] = None):
    _, cfg = await active_config(module)
    filt = {"config_id": cfg["config_id"], "status": "validated"}
    if submodule:
        filt["submodule"] = submodule
    if level:
        filt["knowledge_level"] = level
    qs = await db.questions.find(filt, PUBLIC_Q).to_list(5000)
    excl = set((exclude or "").split(","))
    qs = [q for q in qs if q["question_id"] not in excl] or qs
    if not qs:
        raise HTTPException(404, "No validated questions available for this selection yet")
    atts, stats = await submodule_stats(module)
    weights = {s["key"]: s["questions"] / cfg["question_count"] for s in cfg["submodules"]}
    allowed = {s["key"]: s["allowed_levels"] for s in cfg["submodules"]}
    per_q = {}
    for a in atts:
        p = per_q.setdefault(a["question_id"], {"wrong": 0, "last": None, "last_ok": None})
        p["wrong"] += 0 if a["correct"] else 1
        p["last"], p["last_ok"] = a["created_at"], a["correct"]
    now = datetime.now(timezone.utc)
    best, best_score, best_reason = None, -1, []
    for q in qs:
        if q["knowledge_level"] not in allowed.get(q["submodule"], []):
            continue
        st = stats.get(q["submodule"], {"n": 0, "c": 0})
        acc = st["c"] / st["n"] if st["n"] else 0.5
        p = per_q.get(q["question_id"])
        days = (now - datetime.fromisoformat(p["last"])).total_seconds() / 86400 if p else None
        parts = {"EASA weighting": 3 * weights.get(q["submodule"], 0) * 10 / 2,
                 "weakness": 2 * (1 - acc), "repeated errors": 1.5 * min(p["wrong"], 3) / 3 if p else 0,
                 "recency": 1.0 if p is None else min(days / 7, 1) * 0.8,
                 "coverage": 1.0 if st["n"] < 3 else 0}
        if p and p["last_ok"] and days < 0.01:
            continue
        score = sum(parts.values()) + random.random() * 0.4
        if score > best_score:
            best, best_score = q, score
            best_reason = [k for k, v in sorted(parts.items(), key=lambda kv: -kv[1]) if v > 0.3][:3]
    best = best or random.choice(qs)
    return {"question": best, "reasons": best_reason}


# ---------------- Mock exam ----------------
class ExamAnswer(BaseModel):
    question_id: str
    selected: Optional[str] = None
    flagged: Optional[bool] = None


@router.post("/exams")
async def start_exam(module: int = 3):
    _, cfg = await active_config(module)
    atts = await db.attempts.find({"profile_id": PROFILE_ID, "module": module}, {"_id": 0, "question_id": 1}).to_list(50000)
    seen = {}
    for a in atts:
        seen[a["question_id"]] = seen.get(a["question_id"], 0) + 1
    paper, short = [], []
    for s in cfg["submodules"]:
        if not s["questions"]:
            continue
        pool = await db.questions.find({"config_id": cfg["config_id"], "submodule": s["key"], "status": "validated",
                                        "knowledge_level": {"$in": s["allowed_levels"]}}, {"_id": 0, "question_id": 1}).to_list(2000)
        if len(pool) < s["questions"]:
            short.append({"key": s["key"], "title": s["title"], "required": s["questions"], "available": len(pool)})
            continue
        random.shuffle(pool)
        pool.sort(key=lambda q: seen.get(q["question_id"], 0))
        paper += [q["question_id"] for q in pool[: s["questions"]]]
    if short:
        raise HTTPException(409, {"message": "The validated question bank does not yet cover the full EASA distribution.", "shortfall": short})
    exam = {"exam_id": new_id("exam"), "profile_id": PROFILE_ID, "module": module, "config_id": cfg["config_id"],
            "category": cfg["course_category"], "question_ids": paper, "answers": {}, "flags": [],
            "duration_seconds": cfg["question_count"] * cfg["seconds_per_question"], "time_minutes": cfg["time_minutes"],
            "pass_mark_percent": cfg["pass_mark_percent"], "started_at": now_iso(), "status": "in_progress"}
    await db.exams.insert_one(dict(exam))
    return await get_exam(exam["exam_id"])


def exam_deadline(exam):
    return datetime.fromisoformat(exam["started_at"]) + timedelta(seconds=exam["duration_seconds"])


@router.get("/exams")
async def list_exams(module: int = 3):
    return await db.exams.find({"profile_id": PROFILE_ID, "module": module}, {"_id": 0, "question_ids": 0, "answers": 0, "review": 0}).sort("started_at", -1).to_list(100)


@router.get("/exams/{exam_id}")
async def get_exam(exam_id: str):
    exam = await db.exams.find_one({"exam_id": exam_id}, {"_id": 0})
    if not exam:
        raise HTTPException(404, "Exam not found")
    exam.pop("_id", None)
    qs = await db.questions.find({"question_id": {"$in": exam["question_ids"]}}, PUBLIC_Q).to_list(500)
    by_id = {q["question_id"]: q for q in qs}
    exam["questions"] = [by_id[i] for i in exam["question_ids"] if i in by_id]
    remaining = (exam_deadline(exam) - datetime.now(timezone.utc)).total_seconds()
    exam["remaining_seconds"] = max(0, int(remaining))
    exam["threshold"] = math.ceil(len(exam["question_ids"]) * exam["pass_mark_percent"] / 100)
    return exam


@router.post("/exams/{exam_id}/answer")
async def exam_answer(exam_id: str, body: ExamAnswer):
    exam = await db.exams.find_one({"exam_id": exam_id}, {"_id": 0})
    if not exam or exam["status"] != "in_progress":
        raise HTTPException(400, "Exam is not in progress")
    if datetime.now(timezone.utc) > exam_deadline(exam) + timedelta(seconds=5):
        raise HTTPException(400, "Time has expired")
    upd = {}
    if body.selected in ("A", "B", "C"):
        upd["$set"] = {f"answers.{body.question_id}": body.selected}
    if body.flagged is not None:
        upd["$addToSet" if body.flagged else "$pull"] = {"flags": body.question_id}
    if upd:
        await db.exams.update_one({"exam_id": exam_id}, upd)
    return {"ok": True}


@router.post("/exams/{exam_id}/submit")
async def exam_submit(exam_id: str):
    exam = await db.exams.find_one({"exam_id": exam_id}, {"_id": 0})
    if not exam:
        raise HTTPException(404, "Exam not found")
    if exam["status"] == "submitted":
        exam.pop("_id", None)
        return exam
    qs = await db.questions.find({"question_id": {"$in": exam["question_ids"]}}, {"_id": 0}).to_list(500)
    by_id = {q["question_id"]: q for q in qs}
    review, by_sub, by_level, score = [], {}, {}, 0
    for qid in exam["question_ids"]:
        q = by_id[qid]
        sel = exam["answers"].get(qid)
        ok = sel == q["correct_answer"]
        score += ok
        if sel:
            await record_attempt(q, sel, "exam", exam_id)
        s = by_sub.setdefault(q["submodule"], {"key": q["submodule"], "title": q["submodule_title"], "total": 0, "correct": 0})
        s["total"] += 1
        s["correct"] += ok
        lv = by_level.setdefault(str(q["knowledge_level"]), {"total": 0, "correct": 0})
        lv["total"] += 1
        lv["correct"] += ok
        review.append({"question_id": qid, "question_text": q["question_text"], "option_a": q["option_a"], "option_b": q["option_b"],
                       "option_c": q["option_c"], "selected": sel, "correct": ok, "submodule": q["submodule"],
                       "knowledge_level": q["knowledge_level"], "mistake_type": None if ok or not sel else mistake_type_for(q, sel), **reveal(q)})
    total = len(exam["question_ids"])
    threshold = math.ceil(total * exam["pass_mark_percent"] / 100)
    elapsed = min((datetime.now(timezone.utc) - datetime.fromisoformat(exam["started_at"])).total_seconds(), exam["duration_seconds"])
    results = {"score": score, "total": total, "percent": round(100 * score / total, 1), "threshold": threshold,
               "met_threshold": score >= threshold, "answered": len(exam["answers"]), "elapsed_seconds": int(elapsed),
               "by_submodule": list(by_sub.values()), "by_level": by_level}
    await db.exams.update_one({"exam_id": exam_id}, {"$set": {"status": "submitted", "submitted_at": now_iso(), "results": results, "review": review}})
    done = await db.exams.find_one({"exam_id": exam_id}, {"_id": 0})
    done.pop("_id", None)
    return done


# ---------------- Performance & mistakes ----------------
@router.get("/performance")
async def performance(module: int = 3):
    _, cfg = await active_config(module)
    atts, stats = await submodule_stats(module)
    levels = {}
    for lv in cfg["applicable_levels"]:
        la = [a for a in atts if a["knowledge_level"] == lv]
        levels[str(lv)] = {"attempts": len(la), "correct": sum(a["correct"] for a in la),
                           "percent": round(100 * sum(a["correct"] for a in la) / len(la), 1) if la else None}
    subs = []
    for s in cfg["submodules"]:
        st = stats.get(s["key"], {"n": 0, "c": 0})
        subs.append({"key": s["key"], "title": s["title"], "weight": s["questions"], "level": s["allowed_levels"],
                     "attempts": st["n"], "correct": st["c"], "percent": round(100 * st["c"] / st["n"], 1) if st["n"] else None})
    weak = sorted([s for s in subs if s["attempts"] >= 2], key=lambda s: (s["percent"], -s["weight"]))[:5]
    recent = sorted(atts, key=lambda a: a["created_at"])[-20:]
    exams = await db.exams.find({"profile_id": PROFILE_ID, "module": module, "status": "submitted"}, {"_id": 0, "exam_id": 1, "results.score": 1, "results.total": 1, "results.percent": 1, "submitted_at": 1}).sort("submitted_at", -1).to_list(10)
    return {"levels": levels, "applicable_levels": cfg["applicable_levels"], "submodules": subs, "weak_areas": weak,
            "total_attempts": len(atts), "total_correct": sum(a["correct"] for a in atts),
            "recent_percent": round(100 * sum(a["correct"] for a in recent) / len(recent), 1) if recent else None, "exams": exams}


@router.get("/mistakes")
async def mistakes(module: int = 3, submodule: Optional[str] = None, mistake_type: Optional[str] = None):
    filt = {"profile_id": PROFILE_ID, "module": module, "correct": False}
    if submodule:
        filt["submodule"] = submodule
    if mistake_type:
        filt["mistake_type"] = mistake_type
    wrong = await db.attempts.find(filt, {"_id": 0}).sort("created_at", -1).to_list(5000)
    qs = await db.questions.find({"question_id": {"$in": list({w["question_id"] for w in wrong})}}, {"_id": 0}).to_list(5000)
    by_id = {q["question_id"]: q for q in qs}
    times_wrong = {}
    for w in wrong:
        times_wrong[w["question_id"]] = times_wrong.get(w["question_id"], 0) + 1
    items = []
    for w in wrong:
        q = by_id.get(w["question_id"])
        if not q:
            continue
        items.append({**w, "question_text": q["question_text"], "option_a": q["option_a"], "option_b": q["option_b"],
                      "option_c": q["option_c"], "times_wrong": times_wrong[w["question_id"]], **reveal(q)})
    return items


@router.get("/mistakes/insights")
async def mistake_insights(module: int = 3):
    atts = await db.attempts.find({"profile_id": PROFILE_ID, "module": module}, {"_id": 0}).to_list(50000)
    groups = {}
    for a in atts:
        g = groups.setdefault((a["submodule"], a["knowledge_level"]), {"submodule": a["submodule"], "title": a["submodule_title"],
                                                                         "level": a["knowledge_level"], "answered": 0, "wrong": 0, "types": {}})
        g["answered"] += 1
        if not a["correct"]:
            g["wrong"] += 1
            g["types"][a["mistake_type"]] = g["types"].get(a["mistake_type"], 0) + 1
    out = []
    for g in groups.values():
        if not g["types"]:
            continue
        top, cnt = max(g["types"].items(), key=lambda kv: kv[1])
        g["top_type"], g["repeated"] = top, cnt >= 2
        g["message"] = (f"You have answered {g['answered']} Level {g['level']} question{'s' if g['answered'] != 1 else ''} on this topic "
                        f"and made {cnt} {top.lower()} mistake{'s' if cnt != 1 else ''}.")
        out.append(g)
    out.sort(key=lambda g: (-g["wrong"], g["submodule"]))
    repeated_q = {}
    for a in atts:
        if not a["correct"]:
            repeated_q[a["question_id"]] = repeated_q.get(a["question_id"], 0) + 1
    type_totals = {}
    for a in atts:
        if not a["correct"]:
            type_totals[a["mistake_type"]] = type_totals.get(a["mistake_type"], 0) + 1
    return {"groups": out, "repeated_questions": sum(1 for v in repeated_q.values() if v >= 2), "type_totals": type_totals}


# ---------------- Study plan ----------------
class PlanStart(BaseModel):
    start_date: Optional[str] = None


async def page_ranges(cfg):
    chunks = await db.chunks.find({"document_id": cfg["content_document_id"], "source_type": "module_content"},
                                  {"_id": 0, "submodule": 1, "page_number": 1}).to_list(5000)
    rng = {}
    for c in chunks:
        r = rng.setdefault(c["submodule"], [c["page_number"], c["page_number"]])
        r[0], r[1] = min(r[0], c["page_number"]), max(r[1], c["page_number"])
    return rng


def level_focus(levels):
    return ("Level 1 focus: be familiar with basic elements, typical terms and a simple description of the subject."
            if levels == [1] else
            "Level 2 focus: theoretical fundamentals, formulae with physical laws, reading schematics and practical application.")


@router.get("/study-plan")
async def study_plan(module: int = 3):
    _, cfg = await active_config(module)
    prof = await db.profile.find_one({"profile_id": PROFILE_ID}, {"_id": 0}) or {}
    plan_meta = (prof.get("plans") or {}).get(str(module), {})
    start = date.fromisoformat(plan_meta["start_date"]) if plan_meta.get("start_date") else None
    done = set(plan_meta.get("completed_days", []))
    _, stats = await submodule_stats(module)
    rng = await page_ranges(cfg)
    subs = [s for s in cfg["submodules"] if s["questions"]]
    total = sum(s["questions"] for s in subs)
    cover_days = 15
    days = {d: [] for d in range(1, cover_days + 1)}
    cum = 0
    for s in subs:
        d = min(cover_days, int((cum + s["questions"] / 2) / total * cover_days) + 1)
        days[d].append(s)
        cum += s["questions"]

    def item(s, extra=1):
        st = stats.get(s["key"], {"n": 0, "c": 0})
        pr = rng.get(s["parent_key"])
        return {"key": s["key"], "title": s["title"], "level": s["allowed_levels"], "exam_questions": s["questions"],
                "pages": pr, "accuracy": round(100 * st["c"] / st["n"]) if st["n"] else None,
                "practice_target": max(4, s["questions"] * 3 * extra), "focus": level_focus(s["allowed_levels"])}

    def priority(s):
        st = stats.get(s["key"], {"n": 0, "c": 0})
        acc = st["c"] / st["n"] if st["n"] else 0.6
        return (s["questions"] / total) * (1 + 2 * (1 - acc))

    ranked = sorted(subs, key=priority, reverse=True)
    plan = []
    for d in range(1, cover_days + 1):
        plan.append({"day": d, "type": "coverage", "title": " + ".join(s["key"] for s in days[d]) or "Consolidation",
                     "items": [item(s) for s in days[d]],
                     "tasks": ["Read the listed course pages", "Use the AI Tutor (Explain / Show Formula) on each heading",
                               "Answer the practice target questions", "Review every mistake with Explain My Mistake"]})
    plan.append({"day": 16, "type": "revision", "title": "Targeted revision I", "items": [item(s, 2) for s in ranked[:3]],
                 "tasks": ["High EASA weighting / weakest areas", "Re-read source pages", "Double practice target"]})
    plan.append({"day": 17, "type": "revision", "title": "Targeted revision II", "items": [item(s, 2) for s in ranked[3:6]],
                 "tasks": ["Next priority areas", "Work formula & calculation questions step-by-step"]})
    plan.append({"day": 18, "type": "mixed", "title": "Adaptive mixed practice + Mistake Bank", "items": [],
                 "tasks": ["40 adaptive practice questions across all submodules", "Clear repeated mistakes in the Mistake Bank"]})
    plan.append({"day": 19, "type": "mock", "title": f"Full mock examination ({cfg['question_count']} Q / {cfg['time_minutes']} min)", "items": [],
                 "tasks": ["Sit a full mock exam under timed conditions", "Review results by submodule and knowledge level"]})
    plan.append({"day": 20, "type": "mock", "title": "Final weak-area review + second mock", "items": [item(s) for s in ranked[:2]],
                 "tasks": ["Revise the two highest-priority areas", "Sit a second full mock exam"]})
    today = (date.today() - start).days + 1 if start else None
    for p in plan:
        p["completed"] = p["day"] in done
        p["date"] = (start + timedelta(days=p["day"] - 1)).isoformat() if start else None
    return {"start_date": start.isoformat() if start else None, "current_day": today,
            "days_remaining": max(0, 20 - today + 1) if today else 20, "plan": plan,
            "basis": "EASA question distribution, guideline knowledge levels, course page ranges, your performance and mistakes"}


@router.post("/study-plan/start")
async def plan_start(body: PlanStart, module: int = 3):
    sd = body.start_date or date.today().isoformat()
    await db.profile.update_one({"profile_id": PROFILE_ID}, {"$set": {f"plans.{module}": {"start_date": sd, "completed_days": []}}}, upsert=True)
    return {"start_date": sd}


@router.post("/study-plan/day/{day}/toggle")
async def plan_toggle(day: int, module: int = 3):
    prof = await db.profile.find_one({"profile_id": PROFILE_ID}, {"_id": 0}) or {}
    meta = (prof.get("plans") or {}).get(str(module), {"completed_days": []})
    done = set(meta.get("completed_days", []))
    done.symmetric_difference_update({day})
    await db.profile.update_one({"profile_id": PROFILE_ID}, {"$set": {f"plans.{module}.completed_days": sorted(done)}}, upsert=True)
    return {"completed_days": sorted(done)}


# ---------------- Source traceability ----------------
@router.get("/sources/chunk/{chunk_id}")
async def source_chunk(chunk_id: str):
    c = await db.chunks.find_one({"chunk_id": chunk_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Source not found")
    d = await db.documents.find_one({"document_id": c["document_id"]}, {"_id": 0, "title": 1, "version": 1, "document_type": 1})
    c.pop("_id", None)
    return {**c, "document_title": d["title"], "document_version": d["version"], "document_type": d["document_type"]}


@router.get("/sources/page-image/{doc_id}/{page}")
async def page_image(doc_id: str, page: int):
    d = await db.documents.find_one({"document_id": doc_id}, {"_id": 0})
    if not d or page < 1:
        raise HTTPException(404, "Not found")
    cache = SOURCES_DIR / "cache" / f"{doc_id}_{page}.png"
    if not cache.exists():
        pdf = pymupdf.open(SOURCES_DIR / d["filename"])
        if page > pdf.page_count:
            raise HTTPException(404, "Page out of range")
        cache.parent.mkdir(exist_ok=True)
        pdf[page - 1].get_pixmap(dpi=110).save(cache)
    return Response(cache.read_bytes(), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
