"""
Maruti FAQ Chatbot - Backend (FastAPI)
----------------------------------------
Semantic FAQ matching using SentenceTransformers (all-MiniLM-L6-v2) for robust paraphrase handling.
"""

import json
import logging
import os
import io
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer, util
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
# Load semantic embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')

FAQ_PATH = Path(__file__).parent / "faqs.json"
with open(FAQ_PATH, "r", encoding="utf-8") as f:
    FAQS = json.load(f)

# Pre-compute embeddings for all FAQ questions
FAQ_QUESTIONS = [faq["question"] for faq in FAQS]
FAQ_EMBEDDINGS = model.encode(FAQ_QUESTIONS, convert_to_tensor=True)

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
    if not FAQ_QUESTIONS or FAQ_EMBEDDINGS is None:
        return None, 0.0
    query_embedding = model.encode(user_query, convert_to_tensor=True)
    similarities = util.cos_sim(query_embedding, FAQ_EMBEDDINGS)[0]
    best_idx = similarities.argmax().item()
    best_score = similarities[best_idx].item()
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
    FAQ_EMBEDDINGS = model.encode(FAQ_QUESTIONS, convert_to_tensor=True)

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
        FAQ_EMBEDDINGS = model.encode(FAQ_QUESTIONS, convert_to_tensor=True)
    else:
        FAQ_EMBEDDINGS = None

    return {"status": "success", "message": "FAQ pair deleted and embedded successfully."}


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
async def upload_pdf(file: UploadFile = File(...)):
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
            FAQ_EMBEDDINGS = model.encode(FAQ_QUESTIONS, convert_to_tensor=True)

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


