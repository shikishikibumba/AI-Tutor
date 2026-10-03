"""Source-locked question generation and multi-stage validation pipeline."""
import re
import random
import asyncio
import logging
from rapidfuzz import fuzz
from core import db, now_iso, new_id, llm_json, MISTAKE_TYPES, QUESTION_TYPES, LLM_MODEL
from ingestion import norm_text

log = logging.getLogger("qgen")
BANNED = re.compile(r"\b(all|none|both|neither) of (the )?(above|these)\b|\ball the above\b", re.I)
SEM = asyncio.Semaphore(3)
RUNNING = {}


def level_text(defs, level):
    d = defs.get(str(level), {})
    objs = "\n".join(f"  ({o['id']}) {o['text']}" for o in d.get("objectives", []))
    return f"LEVEL {level}: {d.get('summary', '')}\n{objs}"


def window(chunks, max_chars=16000, max_pages=7):
    if not chunks:
        return []
    start = random.randrange(len(chunks))
    out, size = [], 0
    for c in chunks[start:] + chunks[:start]:
        if out and (size + len(c["text"]) > max_chars or len(out) >= max_pages):
            break
        out.append(c)
        size += len(c["text"])
    return sorted(out, key=lambda c: c["page_number"])


def source_block(chunks):
    return "\n\n".join(
        f"=== SOURCE PAGE pdf_page={c['page_number']} (course page label {c.get('page_label')}) | submodule {c['submodule']} | section: {c.get('section') or c.get('heading') or '-'} ===\n{c['text']}"
        for c in chunks)


GEN_SYSTEM = """You are an EASA Part-66 basic examination question writer working under a STRICT SOURCE LOCK.
You may ONLY use facts, terminology, formulas, values and statements contained in the SOURCE PAGES provided.
You must NOT use general engineering knowledge, internet knowledge or memory to supply facts, to correct the source, or to complete missing information.
If the source pages do not contain enough information to write a question, return {"insufficient": true, "questions": []}.
Do not silently correct the source. If the source text appears internally inconsistent, unusual or possibly erroneous, still preserve it, and describe the concern in "source_issue".
Return ONLY valid JSON."""

VAL_SYSTEM = """You are an independent EASA Part-66 examination auditor under a STRICT SOURCE LOCK.
Judge ONLY against the SOURCE PAGES and the EASA rules provided. Never use outside knowledge to decide what is correct.
Return ONLY valid JSON."""


def gen_prompt(cfg, sub, chunks, rules, defs, n, existing, examples):
    level = sub["allowed_levels"][0]
    ex = "\n".join(f"- {e['question']} | A. {e['options'][0]} | B. {e['options'][1]} | C. {e['options'][2]}" for e in examples)
    return f"""TASK: Write up to {n} NEW multiple-choice questions for:
Module {cfg['module']} {cfg['module_title']} | Category {cfg['category_group']} | Submodule {sub['key']} {sub['title']}
EASA syllabus scope for this submodule (from the guideline): {sub.get('syllabus') or sub['title']}
REQUIRED EASA KNOWLEDGE LEVEL: {level} (taken from the guideline knowledge-level table; questions must be Level {level} and nothing else)

EASA KNOWLEDGE-LEVEL DEFINITIONS (verbatim from guideline):
{level_text(defs, 1)}
{level_text(defs, 2)}
{level_text(defs, 3)}

EASA BASIC EXAMINATION STANDARD (verbatim): {rules.get('format_source_text', '')}. {rules.get('distractor_standard', '')}

HARD RULES:
1. Exactly three alternatives A, B, C; exactly one correct. Never "all of the above", "none of the above", "both", "neither".
2. Distractors must be plausible, directly related, same terminology, similar grammar and similar length. For numerical questions each wrong answer must come from a realistic procedural error (wrong unit conversion, wrong formula, wrong substitution, sign error, series/parallel mix-up, arithmetic slip) - never random numbers.
3. Every fact in the question, correct answer and explanation must be stated in the SOURCE PAGES. Numerical questions may only use formulas that appear in the source; you choose simple values and must show the calculation.
4. Do not write questions that need the student to see a figure/diagram that is not described in text.
5. Level 1 = familiarity, typical terms, simple description (no calculations). Level 2 = theoretical fundamentals, general description, formulae with physical laws, reading schematics, practical application. Level 3 = detailed theory and interrelationships, preparing schematics, manufacturer instructions, interpreting results. Do NOT label a question Level 2 just because it is harder.
6. Each question must cite the exact pdf_page it is drawn from and include a VERBATIM supporting quote (copied exactly, 10-60 words) from that page.
7. Do not duplicate these existing questions: {existing[:30]}

STYLE REFERENCE ONLY (example question bank - use for tone/format/stem style only; NEVER copy, and NEVER take facts or answers from it; its answers are not authoritative):
{ex or '- (none)'}

SOURCE PAGES:
{source_block(chunks)}

Return JSON:
{{"insufficient": false, "questions": [{{
 "question_text": "...", "option_a": "...", "option_b": "...", "option_c": "...", "correct_answer": "A|B|C",
 "topic": "short topic name from the source heading", "question_type": one of {QUESTION_TYPES},
 "knowledge_level": {level}, "level_justification": "LEVEL {level} because ... (cite EASA objective letters)",
 "explanation": "explanation using only source content", "formula": "formula exactly as in source or null",
 "calculation_steps": "step-by-step working or null", "source_page": <pdf_page int>, "source_section": "section heading",
 "supporting_quote": "verbatim quote", "distractors": [{{"option": "A|B|C", "error_type": one of {MISTAKE_TYPES}, "rationale": "why plausible but wrong"}}],
 "source_issue": null }}]}}"""


def val_prompt(q, sub, chunks, defs, rules):
    level = sub["allowed_levels"][0]
    return f"""Audit this candidate EASA Part-66 question. FIRST answer it yourself using ONLY the source pages (you are not told the intended key).
Submodule: {sub['key']} {sub['title']} | Syllabus scope: {sub.get('syllabus') or sub['title']}
Required EASA level: {level}
{level_text(defs, 1)}
{level_text(defs, 2)}
{level_text(defs, 3)}
Exam standard: {rules.get('format_source_text', '')}. {rules.get('distractor_standard', '')}

QUESTION: {q['question_text']}
A. {q['option_a']}
B. {q['option_b']}
C. {q['option_c']}
Claimed level justification: {q.get('level_justification')}
Formula: {q.get('formula')} | Calculation: {q.get('calculation_steps')}

SOURCE PAGES:
{source_block(chunks)}

Return JSON:
{{"independent_answer": "A|B|C|NONE", "independent_reasoning": "...",
 "source_support": {{"result": "PASS|FAIL", "note": "is the correct answer explicitly supported by the source pages?"}},
 "single_correct": {{"result": "PASS|FAIL", "note": "exactly one option is correct per source"}},
 "distractors": {{"result": "PASS|FAIL", "note": "plausible, related, similar length/grammar, not obviously wrong"}},
 "level": {{"result": "PASS|FAIL", "note": "matches Level {level} criteria (not higher, not lower)"}},
 "numerical": {{"result": "PASS|FAIL|N/A", "note": "recompute any calculation"}},
 "syllabus": {{"result": "PASS|FAIL", "note": "inside the submodule syllabus scope"}},
 "exam_standard": {{"result": "PASS|FAIL", "note": "conforms to EASA examination standard"}},
 "source_issue": null or "describe any apparent inconsistency/error in the SOURCE text itself (do not correct it)"}}"""


def deterministic_checks(q, sub, chunks_by_page):
    opts = [str(q.get(k) or "").strip() for k in ("option_a", "option_b", "option_c")]
    checks = {}
    fmt_ok = all(opts) and len(set(o.lower() for o in opts)) == 3 and not any(q.get(k) for k in ("option_d", "option_e"))
    checks["format"] = {"result": "PASS" if fmt_ok else "FAIL", "note": "exactly 3 distinct non-empty alternatives"}
    banned = any(BANNED.search(o) for o in opts)
    lens = [len(o) for o in opts if o]
    ratio = max(lens) / max(1, min(lens)) if lens else 99
    checks["option_wording"] = {"result": "FAIL" if banned or (ratio > 3.5 and max(lens) > 25) else "PASS",
                                "note": f"banned phrases={banned}, length ratio={ratio:.1f}"}
    checks["answer_key"] = {"result": "PASS" if q.get("correct_answer") in ("A", "B", "C") else "FAIL", "note": "key is A, B or C"}
    lvl_ok = q.get("knowledge_level") in sub["allowed_levels"]
    checks["level_permitted"] = {"result": "PASS" if lvl_ok else "FAIL",
                                 "note": f"level {q.get('knowledge_level')} vs guideline-permitted {sub['allowed_levels']}"}
    page = chunks_by_page.get(q.get("source_page"))
    quote = norm_text(q.get("supporting_quote") or "")
    score = fuzz.partial_ratio(quote, norm_text(page["text"])) if page and len(quote) > 20 else 0
    checks["quote_traceable"] = {"result": "PASS" if score >= 88 else "FAIL",
                                 "note": f"verbatim quote match {score:.0f}% on pdf page {q.get('source_page')}"}
    checks["syllabus_page"] = {"result": "PASS" if page and page["submodule"] == sub["parent_key"] else "FAIL",
                               "note": f"cited page belongs to submodule {page['submodule'] if page else 'n/a'}"}
    return checks


async def generate_for_submodule(cfg, sub, n, job_id=None):
    """Generate up to n validated questions for one submodule. Returns (validated, rejected)."""
    if not sub["allowed_levels"]:
        return 0, 0
    rules_doc = await db.guideline_rules.find_one({"document_id": cfg["guideline_document_id"]}, {"_id": 0}) or {}
    rules, defs = rules_doc.get("rules", {}), rules_doc.get("level_definitions", {})
    chunks = await db.chunks.find({"document_id": cfg["content_document_id"], "submodule": sub["parent_key"],
                                   "source_type": "module_content"}, {"_id": 0}).sort("page_number", 1).to_list(2000)
    if not chunks:
        await log_job(job_id, f"{sub['key']}: no source content - question generation refused")
        return 0, 0
    examples = await db.example_questions.find({"module": cfg["module"], "submodule": sub["parent_key"]}, {"_id": 0}).to_list(300)
    validated = rejected = 0
    attempts = 0
    while validated < n and attempts < max(2, n * 2):
        attempts += 1
        win = window(chunks)
        by_page = {c["page_number"]: c for c in win}
        existing = [q["question_text"] for q in await db.questions.find(
            {"config_id": cfg["config_id"], "submodule": sub["key"]}, {"_id": 0, "question_text": 1}).to_list(300)]
        try:
            async with SEM:
                out = await llm_json(GEN_SYSTEM, gen_prompt(cfg, sub, win, rules, defs, min(3, n - validated), existing,
                                                            random.sample(examples, min(6, len(examples)))))
        except Exception as e:
            await log_job(job_id, f"{sub['key']}: generation call failed ({e})")
            continue
        if out.get("insufficient") or not out.get("questions"):
            await log_job(job_id, f"{sub['key']}: source insufficient for pages {list(by_page)} - nothing generated")
            continue
        for q in out["questions"][: n - validated]:
            ok = await validate_and_store(cfg, sub, q, win, by_page, rules, defs)
            validated += ok
            rejected += 0 if ok else 1
        await log_job(job_id, f"{sub['key']}: {validated}/{n} validated, {rejected} rejected")
    return validated, rejected


async def validate_and_store(cfg, sub, q, win, by_page, rules, defs):
    q["knowledge_level"] = int(q.get("knowledge_level") or 0)
    q["source_page"] = int(q.get("source_page") or 0) if str(q.get("source_page", "")).isdigit() else q.get("source_page")
    checks = deterministic_checks(q, sub, by_page)
    v = {}
    if all(c["result"] == "PASS" for c in checks.values()):
        try:
            async with SEM:
                v = await llm_json(VAL_SYSTEM, val_prompt(q, sub, win, defs, rules))
        except Exception as e:
            v = {"error": str(e)}
        ans_ok = v.get("independent_answer") == q.get("correct_answer")
        checks["answer_independent"] = {"result": "PASS" if ans_ok else "FAIL",
                                        "note": f"auditor answered {v.get('independent_answer')} vs key {q.get('correct_answer')}: {v.get('independent_reasoning', '')[:300]}"}
        for k in ("source_support", "single_correct", "distractors", "level", "numerical", "syllabus", "exam_standard"):
            r = v.get(k) or {"result": "FAIL", "note": "auditor did not return this check"}
            checks[k] = {"result": r.get("result", "FAIL"), "note": r.get("note", "")}
    passed = all(c["result"] in ("PASS", "N/A") for c in checks.values()) and "answer_independent" in checks
    source_issue = q.get("source_issue") or v.get("source_issue")
    status = ("review_required" if source_issue else "validated") if passed else "rejected"
    page = by_page.get(q.get("source_page")) or {}
    doc = await db.documents.find_one({"document_id": cfg["content_document_id"]}, {"_id": 0, "title": 1})
    record = {
        "question_id": new_id("q"), "module": cfg["module"], "category": cfg["category_group"], "config_id": cfg["config_id"],
        "submodule": sub["key"], "submodule_title": sub["title"], "topic": q.get("topic") or page.get("heading"),
        "knowledge_level": q["knowledge_level"], "question_type": q.get("question_type"),
        "difficulty_basis": f"EASA Level {q['knowledge_level']} (guideline knowledge-level table, submodule {sub['key']})",
        "level_justification": q.get("level_justification"),
        "source_document_id": cfg["content_document_id"], "source_document_title": (doc or {}).get("title"),
        "source_page": q.get("source_page"), "source_page_label": page.get("page_label"),
        "source_section": q.get("source_section") or page.get("section"), "source_chunk_id": page.get("chunk_id"),
        "supporting_quote": q.get("supporting_quote"), "question_text": q.get("question_text"),
        "option_a": q.get("option_a"), "option_b": q.get("option_b"), "option_c": q.get("option_c"),
        "correct_answer": q.get("correct_answer"), "explanation": q.get("explanation"),
        "formula_if_applicable": q.get("formula"), "calculation_steps_if_applicable": q.get("calculation_steps"),
        "distractors": q.get("distractors") or [], "validation": {"checks": checks, "status": "PASS" if passed else "FAIL"},
        "status": status, "source_issue": source_issue, "generator_model": LLM_MODEL, "created_at": now_iso(),
    }
    await db.questions.insert_one(dict(record))
    if source_issue and passed:
        await db.flags.insert_one({"flag_id": new_id("flag"), "question_id": record["question_id"], "module": cfg["module"],
                                   "submodule": sub["key"], "document_id": cfg["content_document_id"], "page": q.get("source_page"),
                                   "issue": source_issue, "status": "open", "created_at": now_iso()})
    return 1 if status == "validated" else 0


async def log_job(job_id, msg):
    if job_id:
        await db.jobs.update_one({"job_id": job_id}, {"$push": {"log": {"t": now_iso(), "msg": msg}}})


async def run_job(job_id):
    job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
    cfg = await db.exam_configs.find_one({"config_id": job["config_id"]}, {"_id": 0})
    subs = {s["key"]: s for s in cfg["submodules"]}
    await db.jobs.update_one({"job_id": job_id}, {"$set": {"status": "running", "started_at": now_iso()}})
    totals = {"validated": 0, "rejected": 0}

    async def one(key, n):
        v, r = await generate_for_submodule(cfg, subs[key], n, job_id)
        totals["validated"] += v
        totals["rejected"] += r
        await db.jobs.update_one({"job_id": job_id}, {"$set": {f"progress.{key.replace('.', '_')}": v, **{f"totals.{k}": x for k, x in totals.items()}}})

    try:
        await asyncio.gather(*[one(k, n) for k, n in job["targets"].items() if n > 0 and k in subs])
        await db.jobs.update_one({"job_id": job_id}, {"$set": {"status": "completed", "finished_at": now_iso(), "totals": totals}})
    except Exception as e:
        log.exception("job failed")
        await db.jobs.update_one({"job_id": job_id}, {"$set": {"status": "failed", "error": str(e), "totals": totals}})
    finally:
        RUNNING.pop(job_id, None)


def start_job(job_id):
    RUNNING[job_id] = asyncio.create_task(run_job(job_id))
