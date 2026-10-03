import re
import json
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from emergentintegrations.llm.chat import UserMessage, TextDelta, StreamDone
from core import db, PROFILE_ID, TUTOR_INSUFFICIENT_MSG, now_iso, new_id, make_chat
from ingestion import INDEX, tokenize
from routes_student import active_config, PUBLIC_Q

router = APIRouter(prefix="/api/tutor")

MODES = {
    "explain": "Explain the topic clearly and accurately, reorganising the source wording for learning.",
    "simplify": "Explain in simpler, everyday language, still strictly limited to what the source says.",
    "formula": "Show the formula(s) exactly as written in the source, define each symbol and unit as the source defines them.",
    "example": "Give a worked example. Use ONLY formulas, relationships and (where given) values from the source. If you choose numbers, use only formulas present in the source and show every step.",
    "mistake": "Explain why the student's chosen answer is wrong and why the correct answer is right, using only the source.",
}

SYSTEM = f"""You are the SOURCE-LOCKED AI Tutor of the EASA Part-66 AI Study Assistant.
You answer ONLY from the SOURCE EXCERPTS supplied in each message (provisioned course material).
- Never use general knowledge, memory or the internet to add facts, formulas, values or examples.
- You may reorganise or simplify wording, but must not introduce unsupported facts.
- Do not silently correct the source. If something in the source looks inconsistent or unusual, preserve it and add a line starting with "SOURCE FLAG:" describing the concern so the student can decide.
- Cite every factual sentence with the pdf page tag of its excerpt, e.g. [p.123].
- If the excerpts do not contain enough information, reply with exactly: "{TUTOR_INSUFFICIENT_MSG}" and nothing else.
Use concise markdown (short paragraphs, bullet lists, formulas in backticks)."""


class ChatIn(BaseModel):
    message: str = ""
    mode: str = "explain"
    module: int = 3
    submodule: Optional[str] = None
    attempt_id: Optional[str] = None


def sse(obj):
    return f"data: {json.dumps(obj)}\n\n"


async def history(module, limit=6):
    msgs = await db.tutor_messages.find({"profile_id": PROFILE_ID, "module": module}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return list(reversed(msgs))


def excerpt_block(chunks):
    return "\n\n".join(f"[p.{c['page_number']}] (submodule {c['submodule']}, section: {c.get('section') or c.get('heading') or '-'})\n{c['text'][:3500]}" for c in chunks)


@router.get("/history")
async def get_history(module: int = 3):
    return await db.tutor_messages.find({"profile_id": PROFILE_ID, "module": module}, {"_id": 0}).sort("created_at", 1).to_list(500)


@router.delete("/history")
async def clear_history(module: int = 3):
    await db.tutor_messages.delete_many({"profile_id": PROFILE_ID, "module": module})
    return {"ok": True}


@router.get("/test-me")
async def test_me(module: int = 3, submodule: Optional[str] = None):
    _, cfg = await active_config(module)
    filt = {"config_id": cfg["config_id"], "status": "validated"}
    if submodule:
        filt["submodule"] = submodule
    pipeline = [{"$match": filt}, {"$sample": {"size": 1}}, {"$project": PUBLIC_Q}]
    res = await db.questions.aggregate(pipeline).to_list(1)
    if not res:
        raise HTTPException(404, "No validated questions are available for this selection yet")
    return res[0]


async def store(module, role, content, mode, sources=None, confident=None, extra=None):
    await db.tutor_messages.insert_one({"message_id": new_id("msg"), "profile_id": PROFILE_ID, "module": module, "role": role,
                                        "content": content, "mode": mode, "sources": sources or [], "source_confident": confident,
                                        "created_at": now_iso(), **(extra or {})})


def source_card(c, doc_titles):
    return {"chunk_id": c["chunk_id"], "document_id": c["document_id"], "document_title": doc_titles.get(c["document_id"]),
            "page": c["page_number"], "page_label": c.get("page_label"), "module": c["module"], "submodule": c["submodule"],
            "section": c.get("section") or c.get("heading")}


@router.post("/chat")
async def chat(body: ChatIn):
    await active_config(body.module)
    mode = body.mode if body.mode in MODES else "explain"
    prior = await history(body.module)
    context_q = ""
    chunks = []
    if mode == "mistake":
        att = await db.attempts.find_one({"attempt_id": body.attempt_id, "profile_id": PROFILE_ID}, {"_id": 0}) if body.attempt_id else None
        if not att:
            raise HTTPException(400, "Select a mistake to explain")
        q = await db.questions.find_one({"question_id": att["question_id"]}, {"_id": 0})
        context_q = (f"QUESTION: {q['question_text']}\nA. {q['option_a']}\nB. {q['option_b']}\nC. {q['option_c']}\n"
                     f"Student chose: {att['selected']} | Correct answer (validated key): {q['correct_answer']}\n"
                     f"Validated explanation: {q.get('explanation')}")
        page = q.get("source_page") or 0
        chunks = await db.chunks.find({"document_id": q["source_document_id"], "page_number": {"$in": [page - 1, page, page + 1]},
                                       "source_type": "module_content"}, {"_id": 0}).sort("page_number", 1).to_list(5)
        user_text = body.message or f"Explain my mistake on: {q['question_text']}"
    else:
        user_text = body.message.strip()
        if not user_text:
            raise HTTPException(400, "Message is required")
        query = user_text
        if len(tokenize(user_text)) < 3:
            last_user = next((m["content"] for m in reversed(prior) if m["role"] == "user"), "")
            query = f"{user_text} {last_user}"
        results, qtok = INDEX.search(query, module=body.module, submodule=body.submodule, k=5)
        good = [r for r in results if r["coverage"] >= 0.5] if qtok else []
        chunks = [r["chunk"] for r in (good or [])[:4]]
    await store(body.module, "user", user_text, mode)
    docs = await db.documents.find({}, {"_id": 0, "document_id": 1, "title": 1}).to_list(100)
    titles = {d["document_id"]: d["title"] for d in docs}

    async def gen():
        if not chunks:
            yield sse({"type": "delta", "content": TUTOR_INSUFFICIENT_MSG})
            await store(body.module, "assistant", TUTOR_INSUFFICIENT_MSG, mode, [], False, {"insufficient": True})
            yield sse({"type": "done", "sources": [], "source_confident": False, "insufficient": True})
            return
        convo = "\n".join(f"{m['role'].upper()}: {m['content'][:1200]}" for m in prior[-4:])
        prompt = (f"MODE: {mode} - {MODES[mode]}\n\nRECENT CONVERSATION (for context only, not a source):\n{convo or '-'}\n\n"
                  f"{context_q}\n\nSOURCE EXCERPTS (the ONLY permitted source):\n{excerpt_block(chunks)}\n\nSTUDENT: {user_text}")
        full = ""
        try:
            async for ev in make_chat(SYSTEM).stream_message(UserMessage(text=prompt)):
                if isinstance(ev, TextDelta):
                    full += ev.content
                    yield sse({"type": "delta", "content": ev.content})
                elif isinstance(ev, StreamDone):
                    break
        except Exception as e:
            yield sse({"type": "error", "message": f"Tutor unavailable: {e}"})
            return
        insufficient = TUTOR_INSUFFICIENT_MSG.lower()[:60] in full.lower()
        cited = {int(p) for p in re.findall(r"\[p\.?\s*(\d+)\]", full)}
        srcs = [source_card(c, titles) for c in chunks if c["page_number"] in cited]
        confident = bool(srcs) and not insufficient
        flags = re.findall(r"SOURCE FLAG:\s*(.+)", full)
        for f in flags:
            await db.flags.insert_one({"flag_id": new_id("flag"), "question_id": None, "module": body.module,
                                       "submodule": chunks[0]["submodule"], "document_id": chunks[0]["document_id"],
                                       "page": chunks[0]["page_number"], "issue": f"Tutor: {f.strip()}", "status": "open", "created_at": now_iso()})
        await store(body.module, "assistant", full, mode, srcs, confident, {"insufficient": insufficient, "source_flags": flags})
        yield sse({"type": "done", "sources": srcs, "source_confident": confident, "insufficient": insufficient, "source_flags": flags})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
