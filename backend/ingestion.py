"""Provisioned-document ingestion, chunking and BM25 retrieval over the controlled knowledge base."""
import re
import math
import asyncio
import logging
from collections import Counter
import pymupdf
from core import db, SOURCES_DIR, now_iso, new_id
from guideline_parser import extract_module_config

log = logging.getLogger("ingestion")

SUBMOD_RE = re.compile(r"SUB\s*MODULE\s*(\d+)\.(\d+)", re.I)
CATEGORY_RE = re.compile(r"CATEGORY\s+([AB][0-9.]*\s*(?:/\s*[AB][0-9L.]*)*)")
PAGE_LABEL_RE = re.compile(r"^Page:\s*(\d+)$")
HEAD_NUM_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)$")
HEAD_INLINE_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\s+([A-Z][A-Z0-9 ,/()&'’\-:.]{2,})$")
HEADER_LINE_RE = re.compile(r"^(CATEGORY |ISSUE \d+ REVISION|ELECTRICAL FUNDAMENTALS$|Page:\s*\d+$|.*SUB MODULE \d+\.\d+$)")
STOP = set("the a an of to in and or is are be for on by with as at it this that from which what how why explain me give please about its can do does".split())


def tokenize(text):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 1]


def norm_text(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t.lower())).strip()


# ---------------- Retrieval index ----------------
class BM25Index:
    def __init__(self):
        self.chunks, self.tfs, self.df, self.avgdl = [], [], Counter(), 1.0

    def build(self, chunks):
        self.chunks = chunks
        self.tfs = [Counter(tokenize(f"{c.get('heading', '')} {c['text']}")) for c in chunks]
        self.df = Counter()
        for tf in self.tfs:
            self.df.update(tf.keys())
        self.avgdl = (sum(sum(tf.values()) for tf in self.tfs) / len(self.tfs)) if self.tfs else 1.0

    def search(self, query, module=None, submodule=None, k=5):
        q = list(dict.fromkeys(tokenize(query)))
        n = len(self.chunks)
        out = []
        for c, tf in zip(self.chunks, self.tfs):
            if module is not None and c["module"] != module:
                continue
            if submodule and c["submodule"] != submodule:
                continue
            dl = sum(tf.values()) or 1
            score, matched = 0.0, 0
            for t in q:
                f = tf.get(t, 0)
                if not f:
                    continue
                matched += 1
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * dl / self.avgdl))
            if score > 0:
                out.append({"score": round(score, 3), "coverage": matched / len(q), "chunk": c})
        out.sort(key=lambda r: -r["score"])
        return out[:k], q


INDEX = BM25Index()


async def rebuild_index():
    active = await db.documents.find({"active": True, "document_type": "module_content"}, {"_id": 0}).to_list(100)
    ids = [d["document_id"] for d in active]
    chunks = await db.chunks.find({"document_id": {"$in": ids}, "source_type": "module_content"}, {"_id": 0}).to_list(20000)
    INDEX.build(chunks)
    log.info("Index rebuilt with %d chunks", len(chunks))


# ---------------- Page parsing ----------------
def parse_course_page(raw, module, carry):
    lines = [" ".join(l.split()) for l in raw.split("\n")]
    lines = [l for l in lines if l]
    sub, label, category = carry.get("submodule"), None, carry.get("category")
    body, headings = [], []
    pending_num = None
    for l in lines:
        m = SUBMOD_RE.search(l)
        if m and l.endswith(m.group(0)) and int(m.group(1)) == module:
            sub = f"{m.group(1)}.{m.group(2)}"
            continue
        m = CATEGORY_RE.match(l)
        if m:
            category = m.group(1).strip()
            continue
        m = PAGE_LABEL_RE.match(l)
        if m:
            label = int(m.group(1))
            continue
        if HEADER_LINE_RE.match(l):
            continue
        if pending_num and l.isupper():
            headings.append(f"{pending_num} {l}")
            pending_num = None
        elif HEAD_NUM_RE.match(l) and l.startswith(f"{module}."):
            pending_num = l
        else:
            m = HEAD_INLINE_RE.match(l)
            if m and l.startswith(f"{module}."):
                headings.append(l)
            pending_num = None
        body.append(l)
    text = "\n".join(body)
    is_toc = "TABLE OF CONTENT" in text or len(re.findall(r"-{6,}", text)) >= 5
    heading = headings[0] if headings else carry.get("heading")
    carry.update({"submodule": sub, "category": category, "heading": headings[-1] if headings else carry.get("heading")})
    return {"submodule": sub, "page_label": label, "category": category, "headings": headings,
            "heading": heading, "text": text, "is_toc": is_toc}


def parse_example_bank(full):
    out = []
    full = full.replace("\xa0", " ").replace("\u00ad", "-")
    sections = list(re.finditer(r"(?m)^(\d{2})\. ([A-Z][^\n]+?)\.? *$", full))
    for i, s in enumerate(sections):
        body = full[s.end(): sections[i + 1].start() if i + 1 < len(sections) else len(full)]
        sub = f"{int(s.group(1))}"
        for blk in re.split(r"Question Number\.\s*\n\s*\d+\.\s*\n", body)[1:]:
            m = re.search(r"^(.*?)Option A\.\s*(.*?)Option B\.\s*(.*?)Option C\.\s*(.*?)Correct Answer is\.\s*(.*?)Explanation\.\s*(.*)$", blk, re.S)
            if not m:
                continue
            clean = [" ".join(x.split()) for x in m.groups()]
            out.append({"section_no": sub, "section_title": s.group(2).strip(), "question": clean[0],
                        "options": clean[1:4], "stated_answer": clean[4], "explanation": clean[5][:400]})
    return out


# ---------------- Ingestion ----------------
async def set_doc(doc_id, **kw):
    await db.documents.update_one({"document_id": doc_id}, {"$set": kw})


def _read_pdf(path):
    pdf = pymupdf.open(path)
    return [(i + 1, p.get_text()) for i, p in enumerate(pdf)]


async def ingest_document(doc_id):
    doc = await db.documents.find_one({"document_id": doc_id}, {"_id": 0})
    path = SOURCES_DIR / doc["filename"]
    await set_doc(doc_id, ingestion_status="processing", ingestion_started_at=now_iso(), ingestion_errors=[])
    try:
        pages = await asyncio.to_thread(_read_pdf, path)
        chars = sum(len(t.strip()) for _, t in pages)
        if chars < 100 * len(pages) * 0.2:
            raise ValueError("Document has no readable text layer; a text-readable PDF is required.")
        await db.chunks.delete_many({"document_id": doc_id})
        stats = {"page_count": len(pages), "characters": chars}
        if doc["document_type"] == "easa_guideline":
            chunks = [{"chunk_id": f"{doc_id}_p{p}", "document_id": doc_id, "page_number": p, "page_label": None,
                       "module": None, "submodule": None, "section": None, "heading": None,
                       "text": "\n".join(" ".join(l.split()) for l in t.split("\n") if l.strip()),
                       "source_type": "easa_guideline"} for p, t in pages]
            await db.chunks.insert_many(chunks)
            probe = extract_module_config(pages, 3)
            stats.update({"rules_extracted": probe["rules"], "level_definitions_found": len(probe["level_definitions"]) == 3})
            await db.guideline_rules.update_one(
                {"document_id": doc_id},
                {"$set": {"document_id": doc_id, "rules": probe["rules"], "level_definitions": probe["level_definitions"],
                          "level_definitions_page": probe["level_definitions_page"], "extracted_at": now_iso()}}, upsert=True)
        elif doc["document_type"] == "module_content":
            module = doc["module"]
            carry, chunks, cats, subs = {}, [], Counter(), Counter()
            for p, t in pages:
                info = parse_course_page(t, module, carry)
                if info["category"]:
                    cats[info["category"]] += 1
                stype = "toc" if info["is_toc"] or len(info["text"]) < 60 else "module_content"
                if stype == "module_content" and info["submodule"]:
                    subs[info["submodule"]] += 1
                chunks.append({"chunk_id": f"{doc_id}_p{p}", "document_id": doc_id, "page_number": p,
                               "page_label": info["page_label"], "module": module, "submodule": info["submodule"],
                               "section": ", ".join(info["headings"][:4]) or info["heading"], "heading": info["heading"],
                               "text": info["text"], "source_type": stype})
            await db.chunks.insert_many(chunks)
            stats.update({"detected_category": cats.most_common(1)[0][0] if cats else None,
                          "pages_per_submodule": dict(sorted(subs.items(), key=lambda kv: [int(x) for x in kv[0].split(".")])),
                          "content_chunks": sum(subs.values())})
        elif doc["document_type"] == "example_questions":
            examples = parse_example_bank("\n".join(t for _, t in pages))
            await db.example_questions.delete_many({"document_id": doc_id})
            module = doc["module"]
            for e in examples:
                e.update({"document_id": doc_id, "module": module, "submodule": f"{module}.{e['section_no']}"})
            if examples:
                await db.example_questions.insert_many(examples)
            stats.update({"example_questions": len(examples)})
        first = await db.documents.count_documents({"document_type": doc["document_type"], "module": doc.get("module"), "active": True,
                                                    "document_id": {"$ne": doc_id}}) == 0
        await set_doc(doc_id, ingestion_status="completed", ingested_at=now_iso(), stats=stats,
                      **({"active": True, "activated_at": now_iso()} if first else {}))
        if doc["document_type"] == "module_content":
            await rebuild_index()
    except Exception as e:  # report ingestion failure to admin
        log.exception("ingestion failed")
        await set_doc(doc_id, ingestion_status="failed", ingestion_errors=[str(e)])


async def guideline_pages():
    g = await db.documents.find_one({"document_type": "easa_guideline", "active": True}, {"_id": 0})
    if not g:
        return None, None
    chunks = await db.chunks.find({"document_id": g["document_id"]}, {"_id": 0}).sort("page_number", 1).to_list(5000)
    return g, [(c["page_number"], c["text"]) for c in chunks]


async def configure_module(module, content_doc_id):
    g, pages = await guideline_pages()
    if not g:
        raise ValueError("No active, ingested EASA guideline")
    content = await db.documents.find_one({"document_id": content_doc_id}, {"_id": 0})
    report = await asyncio.to_thread(extract_module_config, pages, module)
    detected_cat = (content or {}).get("stats", {}).get("detected_category") or ""
    course_cats = {"B1" if c.startswith("B1") else c for c in re.findall(r"[AB][0-9L]*(?:\.\d)?", detected_cat)}
    await db.exam_configs.delete_many({"module": module, "status": {"$ne": "confirmed"}})
    configs = []
    for grp in report["groups"]:
        applies = bool(course_cats & set(grp["categories"]))
        cfg = {
            "config_id": new_id("cfg"), "module": module, "module_title": report["module_title"],
            "category_group": "/".join(grp["categories"]), "categories": grp["categories"],
            "course_category": detected_cat if applies else None, "applies_to_content": applies,
            "question_count": grp["question_count"], "time_minutes": grp["time_minutes"], "essay_questions": grp["essay_questions"],
            "options_per_question": report["rules"].get("options_per_question"), "correct_answers": report["rules"].get("correct_answers"),
            "seconds_per_question": report["rules"].get("seconds_per_question"), "pass_mark_percent": report["rules"].get("pass_mark_percent"),
            "submodules": grp["submodules"], "applicable_levels": grp["applicable_levels"], "checks": grp["checks"], "issues": grp["issues"],
            "knowledge_level_status": grp["knowledge_level_status"], "distribution_status": grp["distribution_status"],
            "source_pages": {"counts": grp["counts_source_page"], **report["sections_found"],
                             "format": report["rules"].get("format_source_page"), "pass_mark": report["rules"].get("pass_mark_source_page"),
                             "time_rule": report["rules"].get("time_source_page")},
            "counts_source_text": grp["source_text"], "guideline_document_id": g["document_id"], "guideline_version": g["version"],
            "content_document_id": content_doc_id, "status": "extracted", "created_at": now_iso(),
        }
        configs.append(cfg)
    if configs:
        await db.exam_configs.insert_many([dict(c) for c in configs])
    mod = await db.modules.find_one({"module": module}, {"_id": 0})
    await db.modules.update_one({"module": module}, {"$set": {
        "module": module, "title": report["module_title"], "content_document_id": content_doc_id,
        "status": mod["status"] if mod and mod.get("status") == "active" else "inactive",
        "configured_at": now_iso(), "extraction_issues": report["issues"],
        "level_definitions_page": report["level_definitions_page"]}}, upsert=True)
    return report
