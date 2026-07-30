from __future__ import annotations

"""
Maruti FAQ Chatbot - Backend (FastAPI)
----------------------------------------
Semantic FAQ matching using FastEmbed (all-MiniLM-L6-v2 ONNX) for ultra-lightweight, memory-efficient paraphrase handling.
"""

import json
import logging
import os
import io
import re
import time
import uuid
import base64
import hashlib
import hmac
import secrets
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import numpy as np
import pypdf
try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Load environment configuration from root .env
load_dotenv(Path(__file__).parent.parent / ".env")

SOURCE_DATA_DIR = Path(__file__).parent
DATA_DIR = SOURCE_DATA_DIR

# ---------------------------------------------------------------------------
# Logging & Analytics for Knowledge Base Gaps
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MSKA")

# Create a dedicated log file for unanswered queries
UNANSWERED_LOG_PATH = DATA_DIR / "unanswered_queries.log"
unanswered_handler = logging.FileHandler(UNANSWERED_LOG_PATH, encoding="utf-8")
unanswered_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
unanswered_handler.setFormatter(formatter)

unanswered_logger = logging.getLogger("unanswered")
unanswered_logger.addHandler(unanswered_handler)
unanswered_logger.propagate = False

# ---------------------------------------------------------------------------
# Authentication Setup
# ---------------------------------------------------------------------------
security = HTTPBearer()
API_KEY = os.getenv("API_KEY", "admin-secret-key")
AUTH_SECRET = os.getenv("AUTH_SECRET", API_KEY)
USERS_PATH = DATA_DIR / "users.json"
ADMIN_SETTINGS_PATH = DATA_DIR / "admin_settings.json"
AUDIT_LOG_PATH = DATA_DIR / "audit_log.json"

ROLE_PERMISSIONS = {
    "QA Admin": {"view", "upload", "admin", "approve", "configure"},
    "QA": {"view", "upload"},
    "Engineering": {"view", "upload"},
    "Production": {"view"},
    "Parts Quality": {"view"},
}


def password_hash(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000)
    return f"{salt}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt, expected = encoded.split("$", 1)
        candidate = password_hash(password, salt).split("$", 1)[1]
        return hmac.compare_digest(candidate, expected)
    except ValueError:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def issue_session(user: dict) -> str:
    payload = {
        "sub": user["id"],
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "department": user["department"],
        "exp": int(time.time()) + 8 * 60 * 60,
    }
    encoded = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(AUTH_SECRET.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def decode_session(token: str) -> dict:
    try:
        encoded, signature = token.split(".", 1)
        expected = _b64(hmac.new(AUTH_SECRET.encode(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError
        return payload
    except (ValueError, json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired session.")


def load_users() -> list[dict]:
    if USERS_PATH.exists():
        with open(USERS_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    defaults = [
        ("qa_admin", "QA Administrator", "QA Admin", "QA", os.getenv("DEFAULT_QA_ADMIN_PASSWORD", "QAAdmin123!")),
        ("qa_user", "QA Team Member", "QA", "QA", os.getenv("DEFAULT_QA_PASSWORD", "QAUpload123!")),
        ("engineering_user", "Engineering Contributor", "Engineering", "Engineering", os.getenv("DEFAULT_ENGINEERING_PASSWORD", "Engineering123!")),
        ("production_user", "Production Reviewer", "Production", "Production", os.getenv("DEFAULT_PRODUCTION_PASSWORD", "Production123!")),
        ("parts_quality_user", "Parts Quality Reviewer", "Parts Quality", "Parts Quality", os.getenv("DEFAULT_PARTS_QUALITY_PASSWORD", "PartsQuality123!")),
    ]
    users = [
        {
            "id": f"usr_{uuid.uuid4().hex[:12]}",
            "username": username,
            "name": name,
            "role": role,
            "department": department,
            "password_hash": password_hash(password),
            "active": True,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        for username, name, role, department, password in defaults
    ]
    with open(USERS_PATH, "w", encoding="utf-8") as file:
        json.dump(users, file, indent=2)
    return users


def save_users(users: list[dict]) -> None:
    with open(USERS_PATH, "w", encoding="utf-8") as file:
        json.dump(users, file, indent=2)


def audit(action: str, principal: dict, target: str = "", details: Optional[dict] = None) -> None:
    records = []
    if AUDIT_LOG_PATH.exists():
        try:
            records = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            records = []
    records.append({
        "id": f"audit_{uuid.uuid4().hex[:12]}",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "actor": principal.get("name") or principal.get("username", "System"),
        "role": principal.get("role", "Unknown"),
        "action": action,
        "target": target,
        "details": details or {},
    })
    AUDIT_LOG_PATH.write_text(json.dumps(records[-1000:], indent=2, ensure_ascii=False), encoding="utf-8")

def authenticate(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token == API_KEY:
        return {"id": "api_admin", "username": "api_admin", "name": "QA Administrator", "role": "QA Admin", "department": "QA"}
    payload = decode_session(token)
    user = next((item for item in load_users() if item["id"] == payload.get("sub") and item.get("active", True)), None)
    if not user:
        raise HTTPException(status_code=401, detail="User is inactive or unavailable.")
    return {key: user[key] for key in ("id", "username", "name", "role", "department")}


def require_permission(permission: str):
    def dependency(principal: dict = Depends(authenticate)):
        if permission not in ROLE_PERMISSIONS.get(principal.get("role"), set()):
            raise HTTPException(status_code=403, detail=f"{principal.get('role', 'This role')} does not have permission to {permission}.")
        return principal
    return dependency

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Maruti FAQ Chatbot API")

# Allow the frontend (served from file:// or any localhost port) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Load Model & FAQ data at startup
# ---------------------------------------------------------------------------
# Load lightweight ONNX-based semantic embedding model (FastEmbed - ~100MB RAM vs PyTorch 500MB+)
try:
    if TextEmbedding and not os.getenv("DISABLE_FASTEMBED"):
        embedding_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    else:
        embedding_model = None
except Exception as err:
    logger.warning("Failed to initialize FastEmbed model, using lightweight embedding fallback: %s", err)
    embedding_model = None


def lightweight_embedding(text: str) -> np.ndarray:
    """Deterministic lexical embedding for memory-constrained serverless runs."""
    vector = np.zeros(384, dtype=np.float32)
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for token in tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]:
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:2], "big") % vector.size
        vector[index] += 1.0 if digest[2] % 2 else -1.0
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def encode_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 384), dtype=np.float32)
    if embedding_model:
        return np.array(list(embedding_model.embed(texts)), dtype=np.float32)
    return np.array([lightweight_embedding(text) for text in texts], dtype=np.float32)


def encode_query(query: str) -> np.ndarray:
    if embedding_model:
        return list(embedding_model.embed([query]))[0]
    return lightweight_embedding(query)


def cos_sim_vector(query_vec: np.ndarray, doc_matrix: np.ndarray) -> np.ndarray:
    if doc_matrix.size == 0:
        return np.array([], dtype=np.float32)
    dot = np.dot(doc_matrix, query_vec)
    norms = np.linalg.norm(doc_matrix, axis=1) * np.linalg.norm(query_vec)
    return dot / (norms + 1e-9)


FAQ_PATH = DATA_DIR / "faqs.json"
ESCALATIONS_PATH = DATA_DIR / "escalations.json"
DOCUMENTS_PATH = DATA_DIR / "documents.json"
DASHBOARD_ACTIVITY_PATH = DATA_DIR / "dashboard_activity.json"
PROCESS_KNOWLEDGE_PATH = DATA_DIR / "autocare_process.json"
UPLOADS_PATH = DATA_DIR / "uploads"
UPLOADS_PATH.mkdir(exist_ok=True)
with open(FAQ_PATH, "r", encoding="utf-8") as f:
    FAQS = json.load(f)
if DOCUMENTS_PATH.exists():
    with open(DOCUMENTS_PATH, "r", encoding="utf-8") as f:
        DOCUMENTS = json.load(f)
else:
    DOCUMENTS = []
with open(PROCESS_KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
    PROCESS_KNOWLEDGE = json.load(f)

# Pre-compute embeddings for all FAQ questions
FAQ_QUESTIONS = [faq["question"] for faq in FAQS]
FAQ_EMBEDDINGS = encode_texts(FAQ_QUESTIONS)
DOCUMENT_SEARCH_TEXTS = [
    " ".join([
        doc.get("name", ""),
        doc.get("model", ""),
        doc.get("team", ""),
        doc.get("category", ""),
        doc.get("content", ""),
    ])
    for doc in DOCUMENTS
]
DOCUMENT_EMBEDDINGS = encode_texts(DOCUMENT_SEARCH_TEXTS)
PROCESS_SEARCH_TEXTS = [
    " ".join([
        item.get("topic", ""),
        item.get("question", ""),
        item.get("content", ""),
    ])
    for item in PROCESS_KNOWLEDGE
]
PROCESS_EMBEDDINGS = encode_texts(PROCESS_SEARCH_TEXTS)


def load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def record_chat_activity(query: str, evidence: list[dict]) -> None:
    activity = load_json_list(DASHBOARD_ACTIVITY_PATH)
    activity.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "query": query,
        "document_grounded": any(item.get("document_id") for item in evidence),
    })
    cutoff = datetime.now() - timedelta(days=30)
    activity = [
        item for item in activity
        if datetime.fromisoformat(item.get("timestamp", "1970-01-01T00:00:00")) >= cutoff
    ]
    try:
        with open(DASHBOARD_ACTIVITY_PATH, "w", encoding="utf-8") as file:
            json.dump(activity, file, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.warning("Unable to persist dashboard activity: %s", exc)

CONFIDENCE_THRESHOLD = 0.45  # below this -> fallback response
FALLBACK_ANSWER = (
    "I couldn't find a confident answer in the AutoCare QA knowledge base. "
    "Please rephrase the question or raise it with the QA team for review."
)


def classify_department(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ["drawing", "design", "engineering", "specification", "system"]):
        return "Engineering"
    if any(k in q for k in ["production", "line", "process", "manufacturing"]):
        return "Production"
    if any(k in q for k in ["part", "inspection", "defect", "approval", "quality"]):
        return "Parts Quality"
    if any(k in q for k in ["new model", "drbfm", "mizen", "autocare", "gd3", "concern point", "design review"]):
        return "QA New Model Development"
    return "QA"


def find_best_match(user_query: str):
    query_embedding = encode_query(user_query)
    candidates = []

    if FAQ_QUESTIONS and FAQ_EMBEDDINGS is not None and len(FAQ_EMBEDDINGS):
        similarities = cos_sim_vector(query_embedding, FAQ_EMBEDDINGS)
        best_idx = int(np.argmax(similarities))
        candidates.append((FAQS[best_idx], float(similarities[best_idx])))

    if DOCUMENT_SEARCH_TEXTS and DOCUMENT_EMBEDDINGS is not None and len(DOCUMENT_EMBEDDINGS):
        similarities = cos_sim_vector(query_embedding, DOCUMENT_EMBEDDINGS)
        best_idx = int(np.argmax(similarities))
        doc = DOCUMENTS[best_idx]
        content = doc.get("content", "").strip()
        answer = content[:900] if content else (
            f"The relevant file is {doc['name']} under {doc['model']} → "
            f"{doc['team']} → {doc['category']}."
        )
        candidates.append(({
            "question": doc["name"],
            "answer": answer,
            "department": "QA",
        }, float(similarities[best_idx])))

    return max(candidates, key=lambda item: item[1]) if candidates else (None, 0.0)


def _best_page_for_query(doc: dict, user_query: str) -> tuple[int, str]:
    pages = doc.get("pages") or []
    if not pages:
        return 1, doc.get("content", "")[:360]
    query_terms = set(re.findall(r"[a-z0-9]+", user_query.lower()))
    best_page = max(
        pages,
        key=lambda page: len(query_terms & set(re.findall(r"[a-z0-9]+", page.get("text", "").lower()))),
    )
    return int(best_page.get("page", 1)), best_page.get("text", "")[:360]


def retrieve_knowledge(
    user_query: str,
    limit: int = 5,
    model: Optional[str] = None,
    document_id: Optional[str] = None,
):
    """Return the strongest FAQ and document evidence for grounded answering."""
    query_embedding = encode_query(user_query)
    results = []

    if not document_id and FAQ_QUESTIONS and FAQ_EMBEDDINGS is not None and len(FAQ_EMBEDDINGS):
        scores = cos_sim_vector(query_embedding, FAQ_EMBEDDINGS)
        for index in np.argsort(scores)[::-1][:min(limit, len(scores))]:
            faq = FAQS[int(index)]
            if model and model != "all" and faq.get("model") not in {None, "", "All Models", model}:
                continue
            results.append({
                "source": faq["question"],
                "content": faq["answer"],
                "kind": "FAQ",
                "score": float(scores[int(index)]),
            })

    if DOCUMENT_SEARCH_TEXTS and DOCUMENT_EMBEDDINGS is not None and len(DOCUMENT_EMBEDDINGS):
        scores = cos_sim_vector(query_embedding, DOCUMENT_EMBEDDINGS)
        for index in np.argsort(scores)[::-1]:
            doc = DOCUMENTS[int(index)]
            if doc.get("approval_state", "Approved") != "Approved":
                continue
            if model and model != "all" and doc.get("model") != model:
                continue
            if document_id and document_id != "all" and doc.get("id") != document_id:
                continue
            page_number, excerpt = _best_page_for_query(doc, user_query)
            results.append({
                "source": doc["name"],
                "content": doc.get("content", ""),
                "kind": "Document",
                "score": float(scores[int(index)]),
                "location": f"{doc['model']} → {doc['team']} → {doc['category']}",
                "document_id": doc["id"],
                "model": doc.get("model"),
                "team": doc.get("team"),
                "category": doc.get("category"),
                "page": page_number,
                "excerpt": excerpt,
            })
            if len([item for item in results if item["kind"] == "Document"]) >= limit:
                break

    if PROCESS_SEARCH_TEXTS and PROCESS_EMBEDDINGS is not None and len(PROCESS_EMBEDDINGS):
        scores = cos_sim_vector(query_embedding, PROCESS_EMBEDDINGS)
        for index in np.argsort(scores)[::-1][:min(limit, len(scores))]:
            item = PROCESS_KNOWLEDGE[int(index)]
            results.append({
                "source": item["source"],
                "content": item["content"],
                "kind": "Industry Reference",
                "score": max(0.0, float(scores[int(index)]) - 0.03),
                "location": item.get("topic", "Mizen Boushi process guidance"),
                "url": item.get("url"),
                "excerpt": item["content"][:360],
            })

    return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]


def answer_with_openai(query: str, history: list, evidence: list) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None or not evidence:
        return None
    evidence_text = "\n\n".join(
        f"[{item['kind']}: {item['source']}]\n"
        f"Location: {item.get('location', 'QA FAQ knowledge base')}\n"
        f"Content: {item['content'][:3500]}"
        for item in evidence
    )
    conversation = "\n".join(
        f"{item.get('role', 'user').upper()}: {item.get('content', '')[:1200]}"
        for item in history[-6:]
        if item.get("content")
    )
    prompt = (
        f"Recent conversation:\n{conversation or 'No previous turns.'}\n\n"
        f"Approved knowledge evidence:\n{evidence_text}\n\n"
        f"Current question:\n{query}"
    )
    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.6-sol"),
            reasoning={"effort": os.getenv("OPENAI_REASONING_EFFORT", "low")},
            instructions=(
                "You are the Mizen Boushi QA Assistant. Answer only from the supplied evidence. "
                "Treat company Document evidence as authoritative for organization-specific procedures. "
                "Use Industry Reference evidence for broader Toyota and Japanese preventive-quality practice, "
                "and label it as general guidance when no company document confirms it. "
                "Never invent a company rule, approval, owner, form, or deadline. "
                "Be direct, practical, and concise. Return clean plain text without Markdown symbols."
            ),
            input=prompt,
            max_output_tokens=600,
            store=False,
        )
        return response.output_text.strip() if response.output_text else None
    except Exception as exc:
        logger.warning("OpenAI response failed; using local retrieval fallback: %s", exc)
        return None


def citation_payload(evidence: list) -> list[dict]:
    citations = []
    for item in evidence:
        if item.get("kind") == "Document":
            citations.append({
                "kind": "Document",
                "document_id": item.get("document_id"),
                "name": item.get("source"),
                "page": item.get("page", 1),
                "model": item.get("model"),
                "team": item.get("team"),
                "category": item.get("category"),
                "excerpt": item.get("excerpt", ""),
                "score": round(float(item.get("score", 0)), 2),
            })
        elif item.get("kind") == "Industry Reference":
            citations.append({
                "kind": "Industry Reference",
                "name": item.get("source"),
                "topic": item.get("location"),
                "url": item.get("url"),
                "excerpt": item.get("excerpt", ""),
                "score": round(float(item.get("score", 0)), 2),
            })
    return citations[:3]


def stream_openai_answer(query: str, history: list, evidence: list):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None or not evidence:
        return None

    evidence_text = "\n\n".join(
        f"[{index}: {item['kind']} — {item['source']}, page {item.get('page', 1)}]\n"
        f"Location: {item.get('location', 'QA FAQ knowledge base')}\n"
        f"Content: {item['content'][:3500]}"
        for index, item in enumerate(evidence, 1)
    )
    conversation = "\n".join(
        f"{item.get('role', 'user').upper()}: {item.get('content', '')[:1200]}"
        for item in history[-6:]
        if item.get("content")
    )
    prompt = (
        f"Recent conversation:\n{conversation or 'No previous turns.'}\n\n"
        f"Approved knowledge evidence:\n{evidence_text}\n\n"
        f"Current question:\n{query}"
    )
    try:
        client = OpenAI(api_key=api_key)
        return client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.6-sol"),
            reasoning={"effort": os.getenv("OPENAI_REASONING_EFFORT", "low")},
            instructions=(
                "You are the Mizen Boushi QA Assistant. Answer only from the supplied evidence. "
                "Treat company Document evidence as authoritative for organization-specific procedures. "
                "Use Industry Reference evidence for broader Toyota and Japanese preventive-quality practice, "
                "and label it as general guidance when no company document confirms it. "
                "Do not invent specifications, approvals, dates, owners, forms, or results. "
                "The interface displays citations separately, so do not fabricate citation numbers. "
                "Return clean plain text without Markdown symbols."
            ),
            input=prompt,
            max_output_tokens=600,
            store=False,
            stream=True,
        )
    except Exception as exc:
        logger.warning("OpenAI stream failed; using local retrieval fallback: %s", exc)
        return None


def rebuild_document_index():
    global DOCUMENT_SEARCH_TEXTS, DOCUMENT_EMBEDDINGS
    DOCUMENT_SEARCH_TEXTS = [
        " ".join([
            doc.get("name", ""),
            doc.get("model", ""),
            doc.get("team", ""),
            doc.get("category", ""),
            doc.get("content", ""),
        ])
        for doc in DOCUMENTS
    ]
    DOCUMENT_EMBEDDINGS = encode_texts(DOCUMENT_SEARCH_TEXTS)


def persist_documents():
    with open(DOCUMENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(DOCUMENTS, f, indent=2, ensure_ascii=False)


def public_document(doc: dict, include_content: bool = False) -> dict:
    uploaded_at = doc.get("uploaded_at") or ""
    pages = doc.get("pages") or []
    page_previews = pages or [{"page": 1, "text": doc.get("content", "")}]
    result = {
        key: value
        for key, value in doc.items()
        if key not in {"stored_name", "content", "pages"}
    }
    result.update({
        "revision": doc.get("revision", "R1"),
        "approval_state": doc.get("approval_state", "Approved"),
        "owner": doc.get("owner") or doc.get("team") or "QA Team",
        "last_reviewed": doc.get("last_reviewed") or uploaded_at,
        "page_count": max(1, len(page_previews)),
        "page_previews": [
            {
                "page": int(page.get("page", index)),
                "text": str(page.get("text", ""))[:420],
            }
            for index, page in enumerate(page_previews, 1)
        ],
    })
    if include_content:
        result["content"] = doc.get("content", "")
    return result


def ensure_document_visible(doc: dict, principal: dict) -> None:
    if doc.get("approval_state", "Approved") != "Approved" and "upload" not in ROLE_PERMISSIONS.get(principal["role"], set()):
        raise HTTPException(status_code=403, detail="This document is awaiting QA approval.")


def infer_document_metadata(filename: str, text: str):
    sample = f"{filename} {text[:5000]}"
    model_match = re.search(r"\bModel\s*([1-4])\b", sample, re.IGNORECASE)
    team_match = re.search(r"\bEngineering\s*Team\s*(\d+)\b", sample, re.IGNORECASE)
    lower = sample.lower()
    if "design review" in lower:
        category = "Design Review of New Parts"
    elif "approval" in lower:
        category = "Approval of Part Details"
    else:
        category = "New Parts Details"
    return {
        "model": f"Model {model_match.group(1)}" if model_match else "Model 1",
        "team": f"Engineering Team {team_match.group(1)}" if team_match else "Engineering Team 1",
        "category": category,
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ChatHistoryItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    query: str
    history: list[ChatHistoryItem] = Field(default_factory=list)
    model: Optional[str] = None
    document_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    matched_question: Optional[str] = None
    confidence: float
    sources: list[str] = Field(default_factory=list)
    mode: str = "local"
    citations: list[dict] = Field(default_factory=list)


class QAPairRequest(BaseModel):
    question: str
    answer: str
    department: Optional[str] = None


class QADeleteRequest(BaseModel):
    question: str


class FeedbackRequest(BaseModel):
    query: str
    matched_question: Optional[str] = None
    answer: str
    rating: str


class EscalationRequest(BaseModel):
    name: str
    email: str
    phone: str
    query: str
    department: str
    reason: str = None


class EscalationStatusRequest(BaseModel):
    ticket_id: str
    status: str


class RemoveGapRequest(BaseModel):
    query: str
    timestamp: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    name: str
    role: str
    department: str
    password: str = Field(min_length=8)


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8)
    active: Optional[bool] = None


class AdminSettingsRequest(BaseModel):
    models: list[str]
    teams: list[str]
    categories: list[str]
    engineering_upload_requires_qa_approval: bool = True
    qa_upload_auto_approves: bool = True
    retention_days: int = Field(default=730, ge=30, le=3650)
    retain_superseded_revisions: bool = True


class DocumentApprovalRequest(BaseModel):
    approval_state: str
    comment: str = ""


def default_admin_settings() -> dict:
    return {
        "models": ["Model 1", "Model 2", "Model 3", "Model 4"],
        "active_autocare_models": ["Model 1", "Model 2", "Model 3"],
        "upcoming_autocare_models": [
            {"model": "Model 4", "planned_start": "Q4 2026", "status": "Preparation"}
        ],
        "teams": ["Engineering Team 1", "Engineering Team 2", "Engineering Team 3", "Engineering Team 4"],
        "categories": ["New Parts Details", "Approval of Part Details", "Design Review of New Parts"],
        "engineering_upload_requires_qa_approval": True,
        "qa_upload_auto_approves": True,
        "retention_days": 730,
        "retain_superseded_revisions": True,
    }


def load_admin_settings() -> dict:
    if not ADMIN_SETTINGS_PATH.exists():
        settings = default_admin_settings()
        ADMIN_SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        return settings
    try:
        return {**default_admin_settings(), **json.loads(ADMIN_SETTINGS_PATH.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        return default_admin_settings()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/api/auth/login")
def login(req: LoginRequest):
    username = req.username.strip().lower()
    user = next((item for item in load_users() if item["username"].lower() == username), None)
    if not user or not user.get("active", True) or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    principal = {key: user[key] for key in ("id", "username", "name", "role", "department")}
    audit("user.login", principal, user["id"])
    return {"token": issue_session(user), "user": {**principal, "permissions": sorted(ROLE_PERMISSIONS[user["role"]])}}


@app.get("/api/auth/me")
def current_user(principal: dict = Depends(authenticate)):
    return {"user": {**principal, "permissions": sorted(ROLE_PERMISSIONS.get(principal["role"], set()))}}


@app.get("/api/config")
def portal_config(principal: dict = Depends(require_permission("view"))):
    settings = load_admin_settings()
    return {
        "models": settings["models"],
        "teams": settings["teams"],
        "categories": settings["categories"],
        "engineering_upload_requires_qa_approval": settings["engineering_upload_requires_qa_approval"],
    }


@app.get("/api/admin/users")
def admin_users(principal: dict = Depends(require_permission("admin"))):
    return {
        "users": [
            {key: value for key, value in user.items() if key != "password_hash"}
            for user in load_users()
        ],
        "roles": list(ROLE_PERMISSIONS),
    }


@app.post("/api/admin/users", status_code=201)
def create_user(req: UserCreateRequest, principal: dict = Depends(require_permission("admin"))):
    users = load_users()
    username = req.username.strip().lower()
    if any(user["username"].lower() == username for user in users):
        raise HTTPException(status_code=400, detail="Username already exists.")
    if req.role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="Unknown role.")
    user = {
        "id": f"usr_{uuid.uuid4().hex[:12]}",
        "username": username,
        "name": req.name.strip(),
        "role": req.role,
        "department": req.department,
        "reason": req.reason.strip(),
        "password_hash": password_hash(req.password),
        "active": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    users.append(user)
    save_users(users)
    audit("user.created", principal, user["id"], {"username": username, "role": req.role})
    return {"user": {key: value for key, value in user.items() if key != "password_hash"}}


@app.put("/api/admin/users/{user_id}")
def update_user(user_id: str, req: UserUpdateRequest, principal: dict = Depends(require_permission("admin"))):
    users = load_users()
    user = next((item for item in users if item["id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    updates = req.model_dump(exclude_none=True)
    if "role" in updates and updates["role"] not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="Unknown role.")
    password = updates.pop("password", None)
    if password:
        user["password_hash"] = password_hash(password)
    user.update(updates)
    save_users(users)
    audit("user.updated", principal, user_id, {key: value for key, value in updates.items() if key != "password"})
    return {"user": {key: value for key, value in user.items() if key != "password_hash"}}


@app.get("/api/admin/settings")
def get_admin_settings(principal: dict = Depends(require_permission("admin"))):
    return {"settings": load_admin_settings()}


@app.put("/api/admin/settings")
def update_admin_settings(req: AdminSettingsRequest, principal: dict = Depends(require_permission("configure"))):
    settings = req.model_dump()
    ADMIN_SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    audit("settings.updated", principal, "admin_settings", settings)
    return {"settings": settings}


@app.get("/api/admin/audit")
def get_audit_log(principal: dict = Depends(require_permission("admin")), limit: int = 200):
    records = []
    if AUDIT_LOG_PATH.exists():
        try:
            records = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            records = []
    return {"audit": list(reversed(records[-max(1, min(limit, 500)):]))}


@app.put("/api/admin/documents/{document_id}/approval")
def update_document_approval(document_id: str, req: DocumentApprovalRequest, principal: dict = Depends(require_permission("approve"))):
    allowed = {"Approved", "Rejected", "Changes Requested", "Pending QA Approval"}
    if req.approval_state not in allowed:
        raise HTTPException(status_code=400, detail="Unknown approval state.")
    document = next((item for item in DOCUMENTS if item["id"] == document_id), None)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    document["approval_state"] = req.approval_state
    document["approval_comment"] = req.comment.strip()
    document["approved_by"] = principal["name"]
    document["last_reviewed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    persist_documents()
    rebuild_document_index()
    audit("document.approval_updated", principal, document_id, {"state": req.approval_state, "comment": req.comment.strip()})
    return {"document": public_document(document)}


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "AutoCare QA Assistant API is running.",
        "openai_enabled": bool(os.getenv("OPENAI_API_KEY", "").strip() and OpenAI is not None),
    }


@app.get("/faqs")
def list_faqs(principal: dict = Depends(require_permission("view"))):
    """Return all FAQ questions - useful for showing suggested chips on the frontend."""
    return {"faqs": [faq["question"] for faq in FAQS]}


@app.get("/api/dashboard")
def dashboard_summary(principal: dict = Depends(require_permission("view"))):
    """Return live QA dashboard metrics, trends, approvals, and overdue work."""
    now = datetime.now()
    settings = load_admin_settings()
    activity = load_json_list(DASHBOARD_ACTIVITY_PATH)
    escalations = load_json_list(ESCALATIONS_PATH)
    today = now.date()
    today_activity = [
        item for item in activity
        if datetime.fromisoformat(item["timestamp"]).date() == today
    ]
    open_tickets = [
        ticket for ticket in escalations
        if str(ticket.get("status", "")).lower() != "resolved"
    ]
    pending_approvals = [
        {
            "id": faq.get("id"),
            "title": faq.get("question", "Untitled FAQ"),
            "model": faq.get("model", "All Models"),
            "team": faq.get("team") or faq.get("department", "QA"),
            "created_at": faq.get("created_at"),
        }
        for faq in FAQS
        if str(faq.get("status", "published")).lower() in {"pending", "draft", "review"}
    ]
    overdue_actions = []
    for ticket in open_tickets:
        try:
            opened_at = datetime.fromisoformat(str(ticket.get("timestamp", "")).replace(" ", "T"))
        except ValueError:
            continue
        age_hours = int((now - opened_at).total_seconds() // 3600)
        if age_hours >= 48:
            overdue_actions.append({
                "id": ticket.get("id"),
                "title": ticket.get("query", "QA ticket"),
                "department": ticket.get("department", "QA"),
                "status": ticket.get("status", "New"),
                "age_hours": age_hours,
            })
    trend = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        day_activity = [
            item for item in activity
            if datetime.fromisoformat(item["timestamp"]).date() == day
        ]
        trend.append({
            "date": day.isoformat(),
            "label": day.strftime("%a"),
            "queries": len(day_activity),
            "document_grounded": sum(bool(item.get("document_grounded")) for item in day_activity),
        })
    can_view_qa_documents = "upload" in ROLE_PERMISSIONS.get(principal["role"], set())
    documents_under_qa = [
        {
            "id": document.get("id"),
            "name": document.get("name", "Untitled document"),
            "model": document.get("model", "Unassigned"),
            "team": document.get("team", "Engineering"),
            "category": document.get("category", "Uncategorized"),
            "revision": document.get("revision", "R1"),
            "submitted_at": document.get("uploaded_at"),
        }
        for document in DOCUMENTS
        if str(document.get("approval_state", "Approved")).lower()
        in {"pending", "pending qa approval", "qa review", "under review"}
    ]
    active_models = []
    for model in settings.get("active_autocare_models", []):
        model_documents = [document for document in DOCUMENTS if document.get("model") == model]
        approved_count = sum(
            str(document.get("approval_state", "Approved")).lower() == "approved"
            for document in model_documents
        )
        active_models.append({
            "model": model,
            "documents": len(model_documents),
            "approved": approved_count,
            "under_qa": len(model_documents) - approved_count,
            "progress": round((approved_count / len(model_documents)) * 100) if model_documents else 0,
        })
    # Categorize models by Mizen Boushi process status
    completed_models = [m for m in active_models if m["documents"] > 0 and m["progress"] == 100]
    in_process_models = [m for m in active_models if m["documents"] > 0 and m["progress"] < 100]
    not_started_models = [
        {"model": m.get("model", "Unknown"), "planned_start": m.get("planned_start", "TBD"), "status": m.get("status", "Planned")}
        for m in settings.get("upcoming_autocare_models", [])
    ]
    # Also include active models with zero documents as not started
    for m in active_models:
        if m["documents"] == 0:
            not_started_models.insert(0, {"model": m["model"], "planned_start": "Pending documents", "status": "Awaiting uploads"})
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "metrics": {
            "queries_today": len(today_activity),
            "document_grounded_today": sum(bool(item.get("document_grounded")) for item in today_activity),
            "open_tickets": len(open_tickets),
            "documents": len(DOCUMENTS),
            "pending_approvals": len(pending_approvals),
            "overdue_actions": len(overdue_actions),
        },
        "trend": trend,
        "pending_approvals": pending_approvals[:6],
        "overdue_actions": sorted(overdue_actions, key=lambda item: item["age_hours"], reverse=True)[:6],
        "autocare_pipeline": {
            "documents_under_qa": documents_under_qa[:8] if can_view_qa_documents else [],
            "documents_under_qa_count": len(documents_under_qa),
            "can_view_qa_documents": can_view_qa_documents,
            "active_models": active_models,
            "upcoming_models": settings.get("upcoming_autocare_models", []),
            "completed_models": completed_models,
            "in_process_models": in_process_models,
            "not_started_models": not_started_models,
        },
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, principal: dict = Depends(require_permission("view"))):
    query = req.query.strip()
    if not query:
        return ChatResponse(answer="Please type a question.", confidence=0.0)

    history = [
        {"role": item.role, "content": item.content}
        for item in req.history[-6:]
        if item.role in {"user", "assistant"}
    ]
    retrieval_query = query
    if history and len(query.split()) < 8:
        last_user_turn = next(
            (item["content"] for item in reversed(history) if item["role"] == "user"),
            "",
        )
        if last_user_turn and last_user_turn.strip().lower() != query.lower():
            retrieval_query = f"{last_user_turn} {query}"

    evidence = retrieve_knowledge(retrieval_query, model=req.model, document_id=req.document_id)
    record_chat_activity(query, evidence)
    best_score = evidence[0]["score"] if evidence else 0.0
    best_source = evidence[0]["source"] if evidence else None
    openai_answer = answer_with_openai(query, history, evidence)

    if openai_answer:
        return ChatResponse(
            answer=openai_answer,
            matched_question=best_source,
            confidence=round(best_score, 2),
            sources=list(dict.fromkeys(item["source"] for item in evidence[:3])),
            mode="openai",
            citations=citation_payload(evidence),
        )

    if not evidence or best_score < CONFIDENCE_THRESHOLD:
        # Log unanswered query details to identify knowledge base gaps
        best_match_q = best_source or "None"
        unanswered_logger.info(
            f"Unanswered Query: '{query}' | Closest Match: '{best_match_q}' | Confidence: {best_score:.2f}"
        )
        return ChatResponse(
            answer=FALLBACK_ANSWER,
            confidence=round(best_score, 2),
            sources=[item["source"] for item in evidence[:2]],
            citations=citation_payload(evidence),
        )

    return ChatResponse(
        answer=evidence[0]["content"],
        matched_question=best_source,
        confidence=round(best_score, 2),
        sources=list(dict.fromkeys(item["source"] for item in evidence[:3])),
        citations=citation_payload(evidence),
    )


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, principal: dict = Depends(require_permission("view"))):
    query = req.query.strip()

    def emit(event_type: str, **payload):
        return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"

    def generate():
        if not query:
            yield emit("error", message="Please type a question.")
            return

        history = [
            {"role": item.role, "content": item.content}
            for item in req.history[-6:]
            if item.role in {"user", "assistant"}
        ]
        retrieval_query = query
        if history and len(query.split()) < 8:
            last_user_turn = next(
                (item["content"] for item in reversed(history) if item["role"] == "user"),
                "",
            )
            if last_user_turn and last_user_turn.strip().lower() != query.lower():
                retrieval_query = f"{last_user_turn} {query}"

        evidence = retrieve_knowledge(
            retrieval_query,
            model=req.model,
            document_id=req.document_id,
        )
        record_chat_activity(query, evidence)
        best_score = float(evidence[0]["score"]) if evidence else 0.0
        best_source = evidence[0]["source"] if evidence else None
        citations = citation_payload(evidence)
        yield emit(
            "context",
            matched_question=best_source,
            confidence=round(best_score, 2),
            citations=citations,
            scope={"model": req.model or "all", "document_id": req.document_id or "all"},
        )

        if not evidence:
            unanswered_logger.info(
                f"Unanswered Query: '{query}' | Closest Match: '{best_source or 'None'}' | Confidence: {best_score:.2f}"
            )
            answer = FALLBACK_ANSWER
            mode = "local"
            for chunk in re.findall(r"\S+\s*", answer):
                yield emit("delta", text=chunk)
                time.sleep(0.018)
            yield emit("done", answer=answer, mode=mode)
            return

        answer_parts = []
        stream = stream_openai_answer(query, history, evidence)
        if stream is not None:
            try:
                for event in stream:
                    if getattr(event, "type", "") == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            answer_parts.append(delta)
                            yield emit("delta", text=delta)
                answer = "".join(answer_parts).strip()
                if answer:
                    yield emit("done", answer=answer, mode="openai")
                    return
            except Exception as exc:
                logger.warning("OpenAI streaming interrupted; using local fallback: %s", exc)

        if best_score < CONFIDENCE_THRESHOLD:
            unanswered_logger.info(
                f"Unanswered Query: '{query}' | Closest Match: '{best_source or 'None'}' | Confidence: {best_score:.2f}"
            )
            answer = FALLBACK_ANSWER
        else:
            answer = evidence[0].get("content", "").strip() or FALLBACK_ANSWER
        for chunk in re.findall(r"\S+\s*", answer):
            yield emit("delta", text=chunk)
            time.sleep(0.018)
        yield emit("done", answer=answer, mode="local")

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/qa", status_code=status.HTTP_201_CREATED)
def add_qa_pair(req: QAPairRequest, principal: dict = Depends(require_permission("admin"))):
    """Protected endpoint to append new QA pairs and dynamically reload the search index."""
    global FAQS, FAQ_QUESTIONS, FAQ_EMBEDDINGS

    question = req.question.strip()
    answer = req.answer.strip()

    if not question or not answer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question and answer cannot be empty."
        )

    # Check for duplicates
    for faq in FAQS:
        if faq["question"].lower() == question.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This question already exists in the FAQ database."
            )

    dept = req.department.strip() if req.department else ""
    if not dept:
        dept = classify_department(question)

    new_pair = {"question": question, "answer": answer, "department": dept}
    FAQS.append(new_pair)

    # Persist the update to faqs.json
    try:
        with open(FAQ_PATH, "w", encoding="utf-8") as f:
            json.dump(FAQS, f, indent=2, ensure_ascii=False)
    except Exception as e:
        FAQS.pop()  # Rollback memory
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist FAQ pair: {str(e)}"
        )

    # Re-calculate embeddings dynamically so they are instantly searchable
    FAQ_QUESTIONS = [faq["question"] for faq in FAQS]
    FAQ_EMBEDDINGS = encode_texts(FAQ_QUESTIONS)

    audit("faq.created", principal, new_pair.get("id", question), {"question": question, "department": dept})
    return {"status": "success", "message": "FAQ pair added and embedded successfully."}


@app.get("/api/qa")
def list_qa_pairs(principal: dict = Depends(require_permission("view"))):
    """Return all FAQ questions and answers."""
    return {"faqs": FAQS}


@app.get("/api/documents")
def list_documents(principal: dict = Depends(require_permission("view"))):
    """Return the searchable AutoCare document library metadata."""
    return {
        "documents": [
            public_document(doc)
            for doc in DOCUMENTS
            if doc.get("approval_state", "Approved") == "Approved" or "upload" in ROLE_PERMISSIONS.get(principal["role"], set())
        ]
    }


@app.get("/api/documents/{document_id}/download")
def download_document(document_id: str, principal: dict = Depends(require_permission("view"))):
    doc = next((item for item in DOCUMENTS if item["id"] == document_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    ensure_document_visible(doc, principal)
    stored_name = doc.get("stored_name")
    if not stored_name:
        raise HTTPException(
            status_code=404,
            detail="This is a sample library record. Upload the source PDF to enable download."
        )
    file_path = (UPLOADS_PATH / stored_name).resolve()
    if UPLOADS_PATH.resolve() not in file_path.parents or not file_path.exists():
        raise HTTPException(status_code=404, detail="Stored file is unavailable.")
    return FileResponse(file_path, filename=doc["name"], media_type="application/pdf")


@app.get("/api/documents/{document_id}/preview")
def preview_document(document_id: str, principal: dict = Depends(require_permission("view"))):
    """Display an uploaded PDF inline for the user-facing preview panel."""
    doc = next((item for item in DOCUMENTS if item["id"] == document_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    ensure_document_visible(doc, principal)
    stored_name = doc.get("stored_name")
    if not stored_name:
        raise HTTPException(status_code=404, detail="No source PDF is attached to this indexed record.")
    file_path = (UPLOADS_PATH / stored_name).resolve()
    if UPLOADS_PATH.resolve() not in file_path.parents or not file_path.exists():
        raise HTTPException(status_code=404, detail="Stored file is unavailable.")
    safe_name = re.sub(r'["\r\n]', "_", doc["name"])
    return FileResponse(
        file_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@app.get("/api/documents/{document_id}")
def get_document(document_id: str, principal: dict = Depends(require_permission("view"))):
    """Return safe document details and indexed text for the preview panel."""
    doc = next((item for item in DOCUMENTS if item["id"] == document_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    ensure_document_visible(doc, principal)
    return {
        "document": public_document(doc, include_content=True),
        "has_file": bool(doc.get("stored_name")),
    }


REQUIRED_POINTERS = ["Introduction", "Methodology", "Results", "Conclusion", "Safety Warning"]

@app.post("/api/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    model: str = Form(""),
    team: str = Form(""),
    category: str = Form(""),
    replace_document_id: str = Form(""),
    principal: dict = Depends(require_permission("upload")),
):
    """Store, classify, index, and publish a QA document."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    contents = await file.read()
    if len(contents) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF files must be 15MB or smaller.")

    try:
        reader = pypdf.PdfReader(io.BytesIO(contents))
        page_records = [
            {"page": index, "text": re.sub(r"\s+", " ", page.extract_text() or "").strip()}
            for index, page in enumerate(reader.pages, 1)
        ]
        full_text = "\n".join(page["text"] for page in page_records if page["text"]).strip()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read this PDF: {exc}")

    if not full_text:
        raise HTTPException(status_code=400, detail="No readable text was found in this PDF.")

    lower_text = full_text.lower()
    found_pointers = [p for p in REQUIRED_POINTERS if p.lower() in lower_text]
    missing_pointers = [p for p in REQUIRED_POINTERS if p.lower() not in lower_text]
    score = int((len(found_pointers) / len(REQUIRED_POINTERS)) * 100)

    inferred = infer_document_metadata(file.filename, full_text)
    settings = load_admin_settings()
    resolved_model = model.strip() or inferred["model"]
    resolved_team = team.strip() or inferred["team"]
    resolved_category = category.strip() or inferred["category"]
    if resolved_model not in settings["models"]:
        raise HTTPException(status_code=400, detail="The selected model is not enabled by the administrator.")
    if resolved_team not in settings["teams"]:
        raise HTTPException(status_code=400, detail="The selected engineering team is not enabled by the administrator.")
    if resolved_category not in settings["categories"]:
        raise HTTPException(status_code=400, detail="The selected document category is not enabled by the administrator.")
    approval_state = "Draft"
    
    safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename).name)
    stored_name = f"{uuid.uuid4().hex}_{safe_filename}"
    file_path = UPLOADS_PATH / stored_name

    existing_doc = None
    if replace_document_id:
        existing_doc = next((doc for doc in DOCUMENTS if doc["id"] == replace_document_id), None)
        if existing_doc and existing_doc["uploaded_by"] != principal["id"] and principal["role"] not in ("QA Admin", "Admin"):
            raise HTTPException(status_code=403, detail="You can only replace your own drafts.")
            
    if existing_doc:
        old_stored_name = existing_doc.get("stored_name")
        document = existing_doc
        document.update({
            "name": Path(file.filename).name,
            "model": resolved_model,
            "team": resolved_team,
            "category": resolved_category,
            "content": re.sub(r"\s+", " ", full_text)[:12000],
            "pages": page_records,
            "approval_state": approval_state,
            "last_reviewed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "size": len(contents),
            "stored_name": stored_name,
            "score": score,
            "missing_pointers": missing_pointers,
        })
    else:
        document = {
            "id": f"doc_{uuid.uuid4().hex}",
            "name": Path(file.filename).name,
            "model": resolved_model,
            "team": resolved_team,
            "category": resolved_category,
            "content": re.sub(r"\s+", " ", full_text)[:12000],
            "pages": page_records,
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "revision": "R1",
            "approval_state": approval_state,
            "owner": principal["department"],
            "uploaded_by": principal["id"],
            "uploaded_by_name": principal["name"],
            "last_reviewed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "size": len(contents),
            "stored_name": stored_name,
            "score": score,
            "missing_pointers": missing_pointers,
        }

    try:
        file_path.write_bytes(contents)
        if not existing_doc:
            DOCUMENTS.append(document)
        else:
            if old_stored_name:
                old_file_path = UPLOADS_PATH / old_stored_name
                if old_file_path.exists() and old_file_path != file_path:
                    old_file_path.unlink(missing_ok=True)
        persist_documents()
        rebuild_document_index()
        audit("document.uploaded", principal, document["id"], {
            "name": document["name"],
            "approval_state": approval_state,
            "score": score,
            "model": resolved_model,
            "team": resolved_team,
            "category": resolved_category,
            "replaced": bool(existing_doc)
        })
    except Exception as exc:
        if not existing_doc and DOCUMENTS and DOCUMENTS[-1].get("id") == document["id"]:
            DOCUMENTS.pop()
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to store document: {exc}")

    return {
        "status": "success",
        "message": "Document saved as draft.",
        "document": {key: value for key, value in document.items() if key != "content"},
        "classification": {
            "model": document["model"],
            "team": document["team"],
            "category": document["category"],
        },
        "score": score,
        "found_pointers": [p for p in REQUIRED_POINTERS if p.lower() in full_text.lower()],
        "missing_pointers": missing_pointers,
        "approval_state": approval_state,
        "replaced": bool(existing_doc)
    }


@app.put("/api/documents/{document_id}/submit")
def submit_document_for_approval(
    document_id: str,
    principal: dict = Depends(require_permission("upload")),
):
    """Transition a draft document to Pending QA Approval if score >= 60."""
    document = next((doc for doc in DOCUMENTS if doc["id"] == document_id), None)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document.get("uploaded_by") != principal["id"] and principal["role"] not in ("QA Admin", "Admin"):
        raise HTTPException(status_code=403, detail="You can only submit your own documents.")
    if document.get("approval_state") != "Draft":
        raise HTTPException(status_code=400, detail="Only draft documents can be submitted for approval.")
    score = document.get("score", 0)
    if score < 60:
        raise HTTPException(
            status_code=400,
            detail=f"Document score is {score}/100. Minimum 60/100 required to submit for approval."
        )
    settings = load_admin_settings()
    if principal["role"] == "QA Admin" and settings.get("qa_upload_auto_approves", False):
        document["approval_state"] = "Approved"
    else:
        document["approval_state"] = "Pending QA Approval"
    document["last_reviewed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    persist_documents()
    rebuild_document_index()
    audit("document.submitted", principal, document_id, {
        "name": document.get("name"),
        "score": score,
        "approval_state": document["approval_state"],
    })
    return {
        "status": "success",
        "message": f"Document submitted. Status: {document['approval_state']}.",
        "document": {key: value for key, value in document.items() if key != "content"},
        "approval_state": document["approval_state"],
    }


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str, principal: dict = Depends(require_permission("admin"))):
    index = next((i for i, item in enumerate(DOCUMENTS) if item["id"] == document_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    document = DOCUMENTS.pop(index)
    try:
        persist_documents()
        rebuild_document_index()
        stored_name = document.get("stored_name")
        if stored_name:
            (UPLOADS_PATH / stored_name).unlink(missing_ok=True)
        audit("document.deleted", principal, document_id, {"name": document.get("name")})
    except Exception as exc:
        DOCUMENTS.insert(index, document)
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {exc}")
    return {"status": "success", "message": "Document removed."}


@app.delete("/api/qa", status_code=status.HTTP_200_OK)
def delete_qa_pair(req: QADeleteRequest, principal: dict = Depends(require_permission("admin"))):
    """Protected endpoint to delete an FAQ pair and dynamically reload the search index."""
    global FAQS, FAQ_QUESTIONS, FAQ_EMBEDDINGS

    question = req.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )

    # Find and remove
    found = False
    new_faqs = []
    for faq in FAQS:
        if faq["question"].lower() == question.lower():
            found = True
        else:
            new_faqs.append(faq)

    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="FAQ pair not found."
        )

    FAQS = new_faqs

    # Persist the update to faqs.json
    try:
        with open(FAQ_PATH, "w", encoding="utf-8") as f:
            json.dump(FAQS, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete FAQ pair: {str(e)}"
        )

    # Re-calculate embeddings dynamically so they are instantly searchable
    FAQ_QUESTIONS = [faq["question"] for faq in FAQS]
    if FAQ_QUESTIONS:
        FAQ_EMBEDDINGS = encode_texts(FAQ_QUESTIONS)
    else:
        FAQ_EMBEDDINGS = None

    audit("faq.deleted", principal, question, {"question": question})
    return {"status": "success", "message": "FAQ pair deleted and embedded successfully."}


@app.get("/api/verify")
def verify_token(principal: dict = Depends(require_permission("admin"))):
    """Protected endpoint to verify admin API key validity."""
    return {"status": "success", "message": "API key is valid."}


@app.get("/api/unanswered")
def get_unanswered_queries(principal: dict = Depends(require_permission("admin")), limit: int = 50):
    """Protected endpoint to retrieve and parse unresolved query gaps and negative feedback from log file."""
    if not UNANSWERED_LOG_PATH.exists():
        return {"queries": []}

    queries = []
    try:
        with open(UNANSWERED_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Parse from newest to oldest
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue

            parts = line.split(" - ", 1)
            if len(parts) < 2:
                continue
            timestamp, msg = parts[0], parts[1]

            if msg.startswith("Unanswered Query:"):
                # Parse: Unanswered Query: '{query}' | Closest Match: '{closest}' | Confidence: {score}
                q_match = re.search(
                    r"Unanswered Query: '(.*?)' \| Closest Match: '(.*?)' \| Confidence: ([\d\.]+)",
                    msg
                )
                if q_match:
                    queries.append({
                        "type": "unanswered",
                        "timestamp": timestamp,
                        "query": q_match.group(1),
                        "closest_match": q_match.group(2),
                        "confidence": float(q_match.group(3))
                    })
            elif msg.startswith("Negative Feedback"):
                # Parse: Negative Feedback | Query: '{query}' | Matched Q: '{matched}' | Answer: '{answer}'
                f_match = re.search(
                    r"Negative Feedback \| Query: '(.*?)' \| Matched Q: '(.*?)' \| Answer: '(.*?)'",
                    msg
                )
                if f_match:
                    queries.append({
                        "type": "negative_feedback",
                        "timestamp": timestamp,
                        "query": f_match.group(1),
                        "matched_question": f_match.group(2),
                        "answer": f_match.group(3)
                    })

            if len(queries) >= limit:
                break
    except Exception as e:
        logger.error(f"Error reading unanswered queries log: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read unanswered queries log: {str(e)}"
        )
    return {"queries": queries}


@app.post("/api/unanswered/remove")
def remove_unanswered_query(req: RemoveGapRequest, principal: dict = Depends(require_permission("admin"))):
    """Remove a parsed gap log entry from the unanswered queries log file."""
    if not UNANSWERED_LOG_PATH.exists():
         raise HTTPException(status_code=404, detail="Log file not found")
         
    try:
        with open(UNANSWERED_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        new_lines = []
        found = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split(" - ", 1)
            if len(parts) >= 2:
                timestamp, msg = parts[0], parts[1]
                if timestamp.strip() == req.timestamp.strip() and f"'{req.query}'" in msg:
                    found = True
                    continue
            new_lines.append(line)
            
        with open(UNANSWERED_LOG_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        return {"status": "success", "removed": found}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update unanswered queries log: {str(e)}"
        )


@app.post("/api/escalation", status_code=status.HTTP_201_CREATED)
def submit_escalation(req: EscalationRequest):
    """Save user escalation contact details and queries to escalations.json."""
    escalations = []
    if ESCALATIONS_PATH.exists():
        try:
            with open(ESCALATIONS_PATH, "r", encoding="utf-8") as f:
                escalations = json.load(f)
        except Exception as e:
            logger.error(f"Error loading escalations: {e}")
            escalations = []

    # Add new ticket
    new_ticket = {
        "id": f"tkt_{int(time.time() * 1000)}",
        "name": req.name.strip(),
        "email": req.email.strip(),
        "phone": req.phone.strip(),
        "query": req.query.strip(),
        "department": req.department,
        "reason": req.reason.strip(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "New"
    }
    escalations.append(new_ticket)

    try:
        with open(ESCALATIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(escalations, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist escalation ticket: {str(e)}"
        )

    return {"status": "success", "ticket": new_ticket}


@app.get("/api/escalation")
def list_escalations(principal: dict = Depends(require_permission("admin"))):
    """List all user escalation support tickets (admin protected)."""
    if not ESCALATIONS_PATH.exists():
        return {"escalations": []}
    try:
        with open(ESCALATIONS_PATH, "r", encoding="utf-8") as f:
            escalations = json.load(f)
        return {"escalations": escalations}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read escalations database: {str(e)}"
        )


@app.put("/api/escalation")
def update_escalation_status(req: EscalationStatusRequest, principal: dict = Depends(require_permission("admin"))):
    """Update status of a support ticket (admin protected)."""
    if not ESCALATIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="No tickets found")
    try:
        # --- DB LAYER (swap here for Supabase) ---
        with open(ESCALATIONS_PATH, "r", encoding="utf-8") as f:
            tickets = json.load(f)

        found = False
        for t in tickets:
            if t["id"] == req.ticket_id:
                t["status"] = req.status
                found = True
                break

        if not found:
            raise HTTPException(status_code=404, detail="Ticket not found")

        with open(ESCALATIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(tickets, f, indent=2, ensure_ascii=False)
        # --- END DB LAYER ---

        audit("ticket.status_updated", principal, req.ticket_id, {"status": req.status})
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update ticket: {str(e)}"
        )


@app.delete("/api/escalation/{ticket_id}", status_code=status.HTTP_200_OK)
def delete_escalation(ticket_id: str, principal: dict = Depends(require_permission("admin"))):
    """Permanently delete a support ticket by ID (admin protected)."""
    if not ESCALATIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="No tickets found")
    try:
        # --- DB LAYER (swap here for Supabase) ---
        with open(ESCALATIONS_PATH, "r", encoding="utf-8") as f:
            tickets = json.load(f)

        original_len = len(tickets)
        tickets = [t for t in tickets if t["id"] != ticket_id]

        if len(tickets) == original_len:
            raise HTTPException(status_code=404, detail="Ticket not found")

        with open(ESCALATIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(tickets, f, indent=2, ensure_ascii=False)
        # --- END DB LAYER ---

        audit("ticket.deleted", principal, ticket_id)
        return {"status": "success", "message": f"Ticket {ticket_id} permanently deleted."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete ticket: {str(e)}"
        )


@app.post("/api/feedback", status_code=status.HTTP_200_OK)
def submit_feedback(req: FeedbackRequest):
    """Log thumbs up/down user feedback into the gaps/analytics log."""
    if req.rating == "down":
        unanswered_logger.info(
            f"Negative Feedback | Query: '{req.query}' | Matched Q: '{req.matched_question or 'None'}' | Answer: '{req.answer}'"
        )
    else:
        logger.info(
            f"Positive Feedback | Query: '{req.query}' | Matched Q: '{req.matched_question or 'None'}'"
        )
    return {"status": "success", "message": "Feedback recorded successfully."}


@app.post("/api/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), principal: dict = Depends(require_permission("admin"))):
    """Extract Q&A pairs from an uploaded PDF and dynamically update the FAQ database."""
    global FAQS, FAQ_QUESTIONS, FAQ_EMBEDDINGS

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported."
        )

    try:
        contents = await file.read()
        pdf_file = io.BytesIO(contents)
        
        # Read pages
        reader = pypdf.PdfReader(pdf_file)
        full_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

        extracted_pairs = []
        
        # 1. Look for Question/Answer or Q/A tags
        qa_pattern = re.compile(
            r'(?:Q|Question):\s*(.*?)\s*(?:A|Answer):\s*(.*?)(?=\s*(?:Q|Question):|$)', 
            re.IGNORECASE | re.DOTALL
        )
        matches = qa_pattern.findall(full_text)
        
        for q, a in matches:
            q_clean = re.sub(r'\s+', ' ', q).strip()
            a_clean = re.sub(r'\s+', ' ', a).strip()
            if q_clean and a_clean:
                extracted_pairs.append({"question": q_clean, "answer": a_clean})
                
        # 2. Heuristic: Split by sentence structures ending in a question mark
        if not extracted_pairs:
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]
            i = 0
            while i < len(lines):
                line = lines[i]
                if line.endswith("?") and len(line) > 10:
                    q_text = line
                    a_lines = []
                    j = i + 1
                    while j < len(lines) and not lines[j].endswith("?") and len(a_lines) < 3:
                        a_lines.append(lines[j])
                        j += 1
                    if a_lines:
                        a_text = " ".join(a_lines)
                        extracted_pairs.append({"question": q_text, "answer": a_text})
                        i = j - 1
                i += 1
                
        # 3. Fallback: Parse single general query if we extracted text but no question tags
        if not extracted_pairs:
            clean_text = re.sub(r'\s+', ' ', full_text).strip()
            if len(clean_text) > 30:
                extracted_pairs.append({
                    "question": f"What are the contents of the document '{file.filename}'?",
                    "answer": clean_text[:400] + "..."
                })
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No readable text or structured Q&A pairs could be extracted from this PDF."
                )

        # Update database with new non-duplicate questions
        added_count = 0
        for pair in extracted_pairs:
            if not any(f["question"].lower() == pair["question"].lower() for f in FAQS):
                dept = classify_department(pair["question"])
                pair_with_dept = {
                    "question": pair["question"],
                    "answer": pair["answer"],
                    "department": dept
                }
                FAQS.append(pair_with_dept)
                added_count += 1

        if added_count > 0:
            # Persist update
            try:
                with open(FAQ_PATH, "w", encoding="utf-8") as f:
                    json.dump(FAQS, f, indent=2, ensure_ascii=False)
            except Exception as e:
                # Rollback
                for _ in range(added_count):
                    FAQS.pop()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to persist FAQs to database: {str(e)}"
                )

            # Re-index embeddings dynamically
            FAQ_QUESTIONS = [faq["question"] for faq in FAQS]
            FAQ_EMBEDDINGS = encode_texts(FAQ_QUESTIONS)

        return {
            "success": True,
            "filename": file.filename,
            "extracted": len(extracted_pairs),
            "added": added_count,
            "pairs": extracted_pairs
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error processing PDF upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error parsing PDF file: {str(e)}"
        )


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

@app.get("/")
def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "AutoCare API is running"}


@app.get("/admin")
def serve_admin():
    admin_path = FRONTEND_DIR / "admin.html"
    if admin_path.exists():
        return FileResponse(admin_path)
    return {"message": "Admin portal"}


@app.get("/{filename:path}")
def serve_static_root(filename: str):
    if filename in ("docs", "redoc", "openapi.json") or filename.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    file_path = FRONTEND_DIR / filename
    if file_path.is_file():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Resource not found")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)


