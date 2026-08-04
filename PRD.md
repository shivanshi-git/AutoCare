# 🚗 AutoCare: Product Requirement Document (PRD) & Code Workings Manual

This document provides a comprehensive description of **AutoCare** (AI-Powered Semantic FAQ Chatbot & Knowledge Management System), explaining the visual frontend features, backend logics, system architectures, and underlying file structures.

---

## 📐 1. System Architecture

AutoCare is designed as an offline-first, lightweight, enterprise-grade semantic search system. It utilizes standard Python libraries and lightweight embedding models to avoid heavy runtime dependencies.

```mermaid
graph TD
    %% Frontend Components
    subgraph Frontend [Client Web Interface]
        ChatUI["Customer Chat Portal (index.html/chat.js)"]
        AdminUI["Admin Dashboard (admin.html/admin.js)"]
    end

    %% Backend Components
    subgraph Backend [FastAPI Server (main.py)]
        API["FastAPI App & CORS Middleware"]
        AuthSvc["Session Auth & RBAC Security"]
        EmbedEngine["Embedding Engine (FastEmbed/Fallback)"]
        Matcher["NumPy Cosine Similarity Engine"]
        PDFParser["PDF Ingestion & Checklist Scorer"]
        DeptClassifier["Lexical Department Classifier"]
    end

    %% Storage Layer
    subgraph Storage [JSON Databases & Logs]
        FAQData[("faqs.json")]
        DocData[("documents.json")]
        UserData[("users.json")]
        EscalationData[("escalations.json")]
        SettingsData[("admin_settings.json")]
        ActivityLog[("dashboard_activity.json")]
        AuditLog[("audit_log.json")]
        GapLog[("unanswered_queries.log")]
    end

    %% Interconnections
    ChatUI -->|POST /chat or /chat/stream| API
    AdminUI -->|Manage Data & Approvals| API
    
    API --> AuthSvc
    API --> EmbedEngine
    API --> Matcher
    API --> PDFParser
    API --> DeptClassifier
    
    Matcher -->|Query Match| FAQData & DocData
    PDFParser -->|Ingest / Parse| DocData
    AuthSvc -->|Verify User| UserData
    API -->|Log Audit| AuditLog
    API -->|Log Unanswered Gaps| GapLog
    API -->|Log Activity| ActivityLog
```

---

## 🎨 2. Frontend Features & Working

The frontend is built using zero-dependency **Vanilla HTML, CSS, and Javascript** and supports both **Light** and **Dark** modes (toggled by the admin/user and stored in `localStorage` as `autocare_theme`).

### 2.1 Customer Chatbot Portal (`index.html` & `chat.js` / `script.js`)
Designed for Maruti customers to search for answers, browse documentation, and file escalations:

1. **Interactive Conversational UI**:
   - Styled message bubbles differentiating the user (blue bubble, right-aligned) and the assistant (grey/blue bubble, left-aligned).
   - Dynamic typing indicator (animated dot-blinking `...`) displayed while waiting for the backend response.
   - Profile card displaying user information (name, role, department) and a sign-out mechanism.

2. **Connected Department Selection**:
   - Before chatting, the customer connects to a specific department:
     - **Service & Maintenance**
     - **Insurance & Claims**
     - **Spare Parts**
     - **Roadside Assistance**
     - **QA New Model Development**
   - Selecting a department initializes a welcome message specific to that department and populates corresponding context chips.

3. **Contextual Q&A Suggestions (Chips)**:
   - Dynamic quick-action chips are loaded below the input bar.
   - If the database contains FAQs for the connected department, the top 10 relevant questions are shown as clickable chips.
   - If no FAQs are available, fallback suggestion chips (e.g., standard scheduling, towing assistance, parts ordering queries) are loaded.

4. **Multi-turn Chat & Local Rephrase**:
   - The chat interface tracks conversation history (capped at 6 turns).
   - If the user enters a short query (under 8 words) in a multi-turn conversation, the client-side/backend appends the previous turn's context to the query to ensure high embedding matching accuracy.

5. **Citations UI**:
   - When answers are retrieved from PDF manuals or reference guides, they feature interactive **Citation Cards** indicating the source document name, page number, model, category, and matching confidence score. Hovering over a card shows an excerpt of the text.

6. **Feedback Action Buttons**:
   - Every assistant response includes **Thumbs Up (👍)** and **Thumbs Down (👎)** buttons.
   - Clicking a button locks the rating, changes its opacity, and submits a POST request to `/api/feedback`.
   - If a customer gives negative feedback (👎), the interface triggers a popup dialog offering to escalate the query to the QA department.

7. **Escalation Trigger**:
   - Automatically triggered when:
     - Consecutive low-confidence matches occur (3 consecutive failures).
     - The user clicks Thumbs Down and approves escalation.
   - A modal form captures the user's name, email, phone number, and reason, which logs an escalation ticket in the backend.

8. **Local Search Interface**:
   - Located on the "Search" tab, this allows users to type queries and perform instant local keyword filtering across the active knowledge base.

---

### 2.2 Admin Panel Dashboard (`admin.html` & `admin.js`)
Protected by credentials, the Admin Panel offers complete knowledge management and telemetry oversight:

1. **Login Gate & Auth Session**:
   - Fullscreen login overlay checking username/password.
   - Saves a JWT-like session token to `sessionStorage` (`autocare_portal_token`).
   - Restricts operations based on the logged-in user's role.

2. **Analytics Dashboard**:
   - Shows live counts of:
     - FAQs in the database.
     - Active PDF documents.
     - Unresolved Escalation Tickets.
     - Unanswered queries/gaps logged today.
     - Overdue escalation actions (tickets older than 48 hours).
   - Interactive trend chart tracking daily query volume and grounding success rates.
   - **Mizen Boushi Pipeline Tracking**: Visual progress bars representing document approval percentages per car model (e.g., Model 1, Model 2).

3. **Document Ingestion (PDF Uploader)**:
   - Supports drag-and-drop or standard file picker for PDF documents (up to 15MB).
   - Enables administrators to tag uploads by **Model**, **Engineering Team**, and **Category**.
   - Shows **Quality Check Checklist** results: checks for required sections ("Introduction", "Methodology", "Results", "Conclusion", "Safety Warning") and calculates a score out of 100.
   - Prevents submissions below a 60/100 pass mark.
   - Allows users to replace existing drafts or submit them to the QA approval queue.

4. **FAQ CRUD Manager**:
   - Complete grid interface showing all Q&A pairs.
   - Form fields to add a new Q&A pair with automatic department classification.
   - Delete button to instantly remove FAQs and rebuild the backend index.

5. **User and Role Management**:
   - QA Admins can manage user accounts.
   - Form to add new users with specified roles, departments, and password constraints.
   - Option to toggle user accounts active/inactive and reset passwords.

6. **QA Document Approval Queue**:
   - Lists pending engineering document uploads.
   - Permits QA Admins to "Approve", "Request Changes", or "Reject" documents.
   - Approved documents are immediately integrated into the active vector index.

7. **Audit Log & Configurations**:
   - Configuration tab to edit lists of car Models, Teams, and Document Categories.
   - Checkboxes to toggle policies: "Require QA approval for Engineering uploads", "Auto-approve QA uploads", "Retain superseded revisions".
   - Numerical input to set document retention periods (in days).
   - **Complete Audit Log Viewer** displaying timestamps, actions, actors, roles, and change details.

8. **Escalation Ticket tracker**:
   - Lists active customer tickets with status indicators ("New", "In Progress", "Resolved").
   - Action buttons to update ticket status or delete tickets.

9. **Knowledge Gap / Unanswered Query Reviewer**:
   - Displays queries that returned below the confidence threshold.
   - Administrators can review the closest matched questions and click "Resolve" to immediately add the query as a new FAQ.

---

## ⚙️ 3. Backend Logics & Architectures

The backend is built with **FastAPI** (`backend/main.py`), utilizing **FastEmbed** and **NumPy** for vector operations, and **PyPDF** for document extraction.

### 3.1 Text Embedding Engine
AutoCare utilizes a two-tier embedding system:

1. **Semantic Model Embedding (Default)**:
   - Uses `fastembed.TextEmbedding` running the `sentence-transformers/all-MiniLM-L6-v2` ONNX pipeline.
   - Generates a **384-dimensional** dense float vector for any text.
   - ONNX Runtime optimizes execution speed and requires only ~100MB of RAM compared to PyTorch models.

2. **Deterministic Lexical Embedding (Fallback)**:
   - If FastEmbed fails to load (or is disabled), the system falls back to a custom deterministic lexical hashing function:
     ```python
     def lightweight_embedding(text: str) -> np.ndarray:
         vector = np.zeros(384, dtype=np.float32)
         tokens = re.findall(r"[a-z0-9]+", text.lower())
         # Generate unigrams and bigrams
         for token in tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]:
             digest = hashlib.sha256(token.encode()).digest()
             index = int.from_bytes(digest[:2], "big") % vector.size
             # Add term importance signals
             vector[index] += 1.0 if digest[2] % 2 else -1.0
         norm = np.linalg.norm(vector)
         return vector / norm if norm else vector
     ```
   - This ensures similarity math continues to function without ML runtime dependencies.

---

### 3.2 NumPy Cosine Similarity Vector Ops
Mathematical matching is performed entirely in memory using NumPy. When the backend starts, it pre-computes embeddings for all FAQs, documents, and reference files:

```python
def cos_sim_vector(query_vec: np.ndarray, doc_matrix: np.ndarray) -> np.ndarray:
    if doc_matrix.size == 0:
        return np.array([], dtype=np.float32)
    dot = np.dot(doc_matrix, query_vec)
    norms = np.linalg.norm(doc_matrix, axis=1) * np.linalg.norm(query_vec)
    return dot / (norms + 1e-9)
```

- When a query is received, it is encoded into a 384-dim vector.
- `cos_sim_vector` computes similarity scores against the entire matrix in one dot-product operation.
- The highest similarity score is identified using `np.argmax(similarities)`.
- If the highest score is $\ge 0.45$ (confidence threshold), it returns the matched FAQ answer. If it is lower, it triggers a fallback response and logs the query into the unanswered log.

---

### 3.3 Hybrid Multi-Source Knowledge Retrieval
When RAG (Retrieval-Augmented Generation) or Streaming is requested, the system performs parallel searches across three internal indices:

1. **FAQ Database (`faqs.json`)**: Matches query vector against the FAQ question embedding matrix.
2. **Approved Document Library (`documents.json`)**: Computes cosine similarity against the search text of page chunks. Identifies the specific page matching the query using a term-frequency heuristic:
   ```python
   best_page = max(
       pages,
       key=lambda page: len(query_terms & set(re.findall(r"[a-z0-9]+", page.get("text", "").lower())))
   )
   ```
3. **Industry References (`autocare_process.json`)**: Vector matches the query against broad Japanese quality control (Mizen Boushi / Toyota) rules.

---

### 3.4 OpenAI RAG Grounding & Stream Generation
If an `OPENAI_API_KEY` is present in the environment:

1. **Retrieval Grounding**:
   - Gathers the top 5 highest-scoring items from the FAQ, Document, and Reference indices.
   - Construct a strict instructions prompt containing the user conversation, approved knowledge evidence, and the user's current question.
   - Forces OpenAI to answer **only** from the supplied evidence.

2. **NDJSON Stream Generator**:
   - The `/chat/stream` endpoint yields an `application/x-ndjson` stream.
   - Emits a `context` block detailing metadata, confidence scores, and citations.
   - Emits `delta` blocks containing text tokens as they stream from the OpenAI API.
   - Emits a final `done` block containing the full answer text.

---

### 3.5 PDF Document Ingestor & Parser Pipeline
When a PDF is uploaded via `/api/documents/upload`:

```
Uploaded PDF -> Extract pages with PyPDF -> Clean Whitespace -> Join Full Text
                                                                   |
  [Quality Scorer Check] <- Verify presence of: Intro, Methodology, Results, Conclusion, Safety
            |
      Score >= 60 -> Classify Metadata (Model/Team/Category) -> Save to Uploads folder
            |
            -> Compute dense embedding matrices -> Rebuild document search indices
```

1. **Page Extraction**: Loop through PDF pages using `pypdf.PdfReader`, cleaning up whitespace.
2. **Checker Checklist**: Computes document checklist compliance score based on structural sections:
   - `Introduction`, `Methodology`, `Results`, `Conclusion`, `Safety Warning`.
   - Score = $\frac{\text{Found Pointers}}{\text{Required Pointers}} \times 100$.
3. **Metadata Classification Heuristics**: Automatically scans text using regular expressions to suggest properties if unspecified:
   - **Model**: `\bModel\s*([1-4])\b`
   - **Team**: `\bEngineering\s*Team\s*(\d+)\b`
   - **Category**: Classifies as "Design Review of New Parts" if "design review" is present, "Approval of Part Details" if "approval" is present, or defaults to "New Parts Details".
4. **Approval Flow Matrix**:
   - If uploaded by QA: auto-approved and searchable.
   - If uploaded by Engineering: marked as `Draft` or `Pending QA Approval`. Stays invisible to view-only departments (Production, Parts Quality) until approved by a QA Admin.

---

### 3.6 Automated Department Classification
To route queries to the correct dashboard without asking the user, the backend uses a lexical rule classifier:

```python
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
```

---

### 3.7 Session Auth, Security & RBAC
1. **PBKDF2 Password Protection**:
   - Passwords are encrypted with salt using standard hashing (`pbkdf2_hmac` with SHA256 and 180,000 iterations).
2. **HMAC Tokens**:
   - Upon successful login, the system creates a base64-encoded JSON payload containing user ID, username, name, role, department, and an expiration timestamp (8 hours).
   - Generates an HMAC SHA256 signature signed using a secret key, appended as `payload.signature`.
3. **Role-Based Access Permissions**:
   - Security dependencies enforce endpoints access:
     - `view`: Available to all roles.
     - `upload`: QA Admin, QA, Engineering.
     - `approve` / `configure`: QA Admin.
     - `admin`: QA Admin.

---

### 3.8 Telemetry Logger & Gap Analytics
1. **Knowledge Gap Logger**:
   - Queries with matching confidence below $0.45$ are written to `unanswered_queries.log` using a standard Python FileHandler:
     ```
     2026-08-04 15:30:12 - Unanswered Query: 'Why is the zero-dep rate high?' | Closest Match: 'What is zero-dep?' | Confidence: 0.32
     ```
2. **Audit Logger**:
   - Every administrative action is tracked in `audit_log.json` indicating the actor, role, action taken, and targets (e.g., `user.created`, `faq.created`, `settings.updated`).

---

## 🗃️ 4. Storage Schemas & Database Structure

All databases are structured in clean, flat JSON formatting for easy manual reading, migration, and lightweight loading.

### 4.1 `faqs.json`
Stores the active knowledge base Q&A pairs:
```json
[
  {
    "id": "faq_405f7b517ad0",
    "question": "What must QA verify before approving a new part?",
    "answer": "QA must verify the latest drawing and specification, dimensional and material results...",
    "department": "QA",
    "model": "All Models",
    "team": "QA",
    "category": "General AutoCare",
    "status": "published",
    "helpful": 2,
    "unhelpful": 1,
    "supporting_document_id": null,
    "source": "manual",
    "created_at": "2026-07-24T21:41:50",
    "reviewed_at": "2026-07-24T21:50:06"
  }
]
```

### 4.2 `documents.json`
Stores metadata and parsed text content from ingested PDFs:
```json
[
  {
    "id": "doc_67b36f7e812d",
    "name": "Model1_WiperSpecs.pdf",
    "model": "Model 1",
    "team": "Engineering Team 1",
    "category": "New Parts Details",
    "content": "Full extracted clean text of the PDF document...",
    "pages": [
      {
        "page": 1,
        "text": "Extracted text content of page 1..."
      }
    ],
    "uploaded_at": "2026-08-04 12:00:00",
    "revision": "R1",
    "approval_state": "Approved",
    "owner": "Engineering",
    "uploaded_by": "usr_78ab61e892ef",
    "uploaded_by_name": "Shivam Sharma",
    "last_reviewed": "2026-08-04 12:10:00",
    "size": 1048576,
    "stored_name": "67b36f7e812d_Model1_WiperSpecs.pdf",
    "score": 80,
    "missing_pointers": ["Conclusion"]
  }
]
```

### 4.3 `escalations.json`
Stores customer support escalations:
```json
[
  {
    "id": "tkt_1785361425891",
    "name": "Anil Mehta",
    "email": "anil@gmail.com",
    "phone": "0999999999",
    "query": "Periodic maintenance schedule details...",
    "department": "Service & Maintenance",
    "timestamp": "2026-08-04 15:45:00",
    "status": "New"
  }
]
```

### 4.4 `users.json`
Stores user registry and pbkdf2 hashed credentials:
```json
[
  {
    "id": "usr_905f7b517ad0",
    "username": "qa_admin",
    "name": "QA Administrator",
    "role": "QA Admin",
    "department": "QA",
    "password_hash": "salt_hex$pbkdf2_sha256_hash_value",
    "active": true,
    "created_at": "2026-07-24T21:41:50"
  }
]
```

### 4.5 `admin_settings.json`
Stores configuration options editable via the Admin UI:
```json
{
  "models": ["Model 1", "Model 2", "Model 3", "Model 4"],
  "active_autocare_models": ["Model 1", "Model 2", "Model 3"],
  "upcoming_autocare_models": [
    {"model": "Model 4", "planned_start": "Q4 2026", "status": "Preparation"}
  ],
  "teams": ["Engineering Team 1", "Engineering Team 2", "Engineering Team 3", "Engineering Team 4"],
  "categories": ["New Parts Details", "Approval of Part Details", "Design Review of New Parts"],
  "engineering_upload_requires_qa_approval": true,
  "qa_upload_auto_approves": true,
  "retention_days": 730,
  "retain_superseded_revisions": true
}
```

### 4.6 `dashboard_activity.json`
Logs daily hits to compute grounded response telemetry:
```json
[
  {
    "timestamp": "2026-08-04T15:20:00",
    "query": "What is the warranty period?",
    "document_grounded": true
  }
]
```

### 4.7 `audit_log.json`
Logs administrative actions:
```json
[
  {
    "id": "audit_405f7b517ad",
    "timestamp": "2026-08-04T15:21:00",
    "actor": "QA Administrator",
    "role": "QA Admin",
    "action": "faq.created",
    "target": "faq_182dd3303195",
    "details": {
      "question": "What is the warranty period?",
      "department": "QA"
    }
  }
]
```

---

## 🚀 5. Quick Deployment & Execution

Both the backend and frontend run using simple, independent command structures.

### Running Backend
The backend requires python-dotenv, fastapi, uvicorn, numpy, pypdf, and fastembed.
```bash
cd backend
pip install -r requirements.txt
python main.py
```
This runs the API server on `http://127.0.0.1:8000` (or `http://127.0.0.1:8005` as secondary fallback configuration).

### Running Frontend
The frontend can be hosted using any basic HTTP web server.
```bash
cd frontend
python -m http.server 3000
```
Open `http://127.0.0.1:3000` in the browser to view the customer chatbot. Access `http://127.0.0.1:3000/admin.html` to log into the Admin panel.
- Default Admin Username: `qa_admin`
- Default Admin Password: `QAAdmin123!`
- Default API Key: `admin-secret-key`
