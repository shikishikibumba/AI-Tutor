from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

import os  # noqa: E402
import re  # noqa: E402
import json  # noqa: E402
import uuid  # noqa: E402
import bcrypt  # noqa: E402
import jwt  # noqa: E402
from datetime import datetime, timezone, timedelta  # noqa: E402
from fastapi import Request, HTTPException  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: E402

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

SOURCES_DIR = ROOT / "sources"
LLM_PROVIDER = "anthropic"
LLM_MODEL = "claude-sonnet-4-5-20250929"
INSUFFICIENT_MSG = "Insufficient information in the provisioned course material to answer this confidently."
TUTOR_INSUFFICIENT_MSG = "The provisioned course material does not provide enough information to answer this."
PROFILE_ID = "local"
NO_ID = {"_id": 0}

MISTAKE_TYPES = [
    "Concept misunderstanding", "Formula error", "Calculation error", "Unit conversion",
    "Sign error", "Misinterpretation", "Recall error", "Series/parallel confusion", "Other",
]
QUESTION_TYPES = ["Conceptual", "Terminology", "Numerical calculation", "Schematic/diagram interpretation", "Practical/procedural"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def make_chat(system, session_id=None):
    return LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=session_id or new_id("s"),
        system_message=system,
    ).with_model(LLM_PROVIDER, LLM_MODEL)


def parse_json(text):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    s = m.group(1) if m else text
    starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
    start = min(starts) if starts else 0
    end = max(s.rfind("}"), s.rfind("]"))
    return json.loads(s[start:end + 1])


async def llm_json(system, prompt):
    text = await make_chat(system).send_message(UserMessage(text=prompt))
    return parse_json(text)


# ---------------- Admin auth ----------------
JWT_ALG = "HS256"


def hash_password(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p, h):
    return bcrypt.checkpw(p.encode(), h.encode())


def create_access_token(uid, email):
    payload = {"sub": uid, "email": email, "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=12)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALG)


async def require_admin(request: Request):
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return user


async def seed_admin():
    email = os.environ["ADMIN_EMAIL"].lower()
    pwd = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if not existing:
        await db.users.insert_one({"id": new_id("usr"), "email": email, "password_hash": hash_password(pwd),
                                   "name": "Administrator", "role": "admin", "created_at": now_iso()})
    elif not verify_password(pwd, existing["password_hash"]):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(pwd)}})
