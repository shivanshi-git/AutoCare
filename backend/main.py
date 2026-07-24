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
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
# pyrefly: ignore [missing-import]
from fastembed import TextEmbedding
import numpy as np
import pypdf

# Load environment configuration from root .env
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Logging & Analytics for Knowledge Base Gaps
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MSKA")

# Create a dedicated log file for unanswered queries
UNANSWERED_LOG_PATH = Path(__file__).parent / "unanswered_queries.log"
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

def authenticate(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

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
embedding_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")


def encode_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 384), dtype=np.float32)
    return np.array(list(embedding_model.embed(texts)), dtype=np.float32)


def encode_query(query: str) -> np.ndarray:
    return list(embedding_model.embed([query]))[0]


def cos_sim_vector(query_vec: np.ndarray, doc_matrix: np.ndarray) -> np.ndarray:
    if doc_matrix.size == 0:
        return np.array([], dtype=np.float32)
    dot = np.dot(doc_matrix, query_vec)
    norms = np.linalg.norm(doc_matrix, axis=1) * np.linalg.norm(query_vec)
    return dot / (norms + 1e-9)


FAQ_PATH = Path(__file__).parent / "faqs.json"
ESCALATIONS_PATH = Path(__file__).parent / "escalations.json"
with open(FAQ_PATH, "r", encoding="utf-8") as f:
    FAQS = json.load(f)

# Pre-compute embeddings for all FAQ questions
FAQ_QUESTIONS = [faq["question"] for faq in FAQS]
FAQ_EMBEDDINGS = encode_texts(FAQ_QUESTIONS)

CONFIDENCE_THRESHOLD = 0.45  # below this -> fallback response
FALLBACK_ANSWER = (
    "Sorry, I couldn't find a confident match for that. "
    "Please rephrase your question or contact Maruti Suzuki customer care at 1800-102-1800."
)


def classify_department(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ["warranty", "service", "maintenance", "book", "appointment", "oil", "coolant", "brake", "plug", "filter", "battery", "alignment"]) or re.search(r'\bac\b', q):
        return "Service & Maintenance"
    elif any(k in q for k in ["insurance", "claim", "renew"]):
        return "Insurance & Claims"
    elif any(k in q for k in ["parts", "accessory", "accessories", "spare"]):
        return "Spare Parts"
    elif any(k in q for k in ["roadside", "assistance", "breakdown", "towing"]):
        return "Roadside Assistance"
    return "General"


def find_best_match(user_query: str):
    if not FAQ_QUESTIONS or FAQ_EMBEDDINGS is None or len(FAQ_EMBEDDINGS) == 0:
        return None, 0.0
    query_embedding = encode_query(user_query)
    similarities = cos_sim_vector(query_embedding, FAQ_EMBEDDINGS)
    best_idx = int(np.argmax(similarities))
    best_score = float(similarities[best_idx])
    return FAQS[best_idx], best_score


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    answer: str
    matched_question: str | None = None
    confidence: float


class QAPairRequest(BaseModel):
    question: str
    answer: str
    department: str | None = None


class QADeleteRequest(BaseModel):
    question: str


class FeedbackRequest(BaseModel):
    query: str
    matched_question: str | None = None
    answer: str
    rating: str


class EscalationRequest(BaseModel):
    name: str
    email: str
    phone: str
    query: str
    department: str


class EscalationStatusRequest(BaseModel):
    ticket_id: str
    status: str


class RemoveGapRequest(BaseModel):
    query: str
    timestamp: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {"status": "ok", "message": "Maruti FAQ Chatbot API is running."}


@app.get("/faqs")
def list_faqs():
    """Return all FAQ questions - useful for showing suggested chips on the frontend."""
    return {"faqs": [faq["question"] for faq in FAQS]}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    query = req.query.strip()
    if not query:
        return ChatResponse(answer="Please type a question.", confidence=0.0)

    best_faq, best_score = find_best_match(query)

    if best_faq is None or best_score < CONFIDENCE_THRESHOLD:
        # Log unanswered query details to identify knowledge base gaps
        best_match_q = best_faq["question"] if best_faq else "None"
        unanswered_logger.info(
            f"Unanswered Query: '{query}' | Closest Match: '{best_match_q}' | Confidence: {best_score:.2f}"
        )
        return ChatResponse(answer=FALLBACK_ANSWER, confidence=round(best_score, 2))

    return ChatResponse(
        answer=best_faq["answer"],
        matched_question=best_faq["question"],
        confidence=round(best_score, 2),
    )


@app.post("/api/qa", status_code=status.HTTP_201_CREATED)
def add_qa_pair(req: QAPairRequest, token: str = Depends(authenticate)):
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

    return {"status": "success", "message": "FAQ pair added and embedded successfully."}


@app.get("/api/qa")
def list_qa_pairs():
    """Return all FAQ questions and answers."""
    return {"faqs": FAQS}


@app.delete("/api/qa", status_code=status.HTTP_200_OK)
def delete_qa_pair(req: QADeleteRequest, token: str = Depends(authenticate)):
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

    return {"status": "success", "message": "FAQ pair deleted and embedded successfully."}


@app.get("/api/verify")
def verify_token(token: str = Depends(authenticate)):
    """Protected endpoint to verify admin API key validity."""
    return {"status": "success", "message": "API key is valid."}


@app.get("/api/unanswered")
def get_unanswered_queries(token: str = Depends(authenticate), limit: int = 50):
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
def remove_unanswered_query(req: RemoveGapRequest, token: str = Depends(authenticate)):
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
        "department": req.department.strip(),
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
def list_escalations(token: str = Depends(authenticate)):
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
def update_escalation_status(req: EscalationStatusRequest, token: str = Depends(authenticate)):
    """Update status of a support ticket (admin protected)."""
    if not ESCALATIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="No tickets found")
    try:
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

        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update ticket: {str(e)}"
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
async def upload_pdf(file: UploadFile = File(...), token: str = Depends(authenticate)):
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)


