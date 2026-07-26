# AutoCare

FastAPI & FastEmbed FAQ matching chatbot and admin portal for Maruti Suzuki.

## Features

- **Semantic FAQ Matching**: Vector similarity search using FastEmbed (`all-MiniLM-L6-v2`).
- **Department Routing**: Classifies queries into Service, Insurance, Parts, etc.
- **Admin Dashboard**: Manage FAQs, review unanswered questions, and upload PDF documents.
- **PDF Ingestion**: Parses PDF files to extract Q&A pairs.
- **Analytics & Escalation**: Logs unanswered queries to `escalations.json` and `unanswered_queries.log`.

## Live Demo

- **Customer App**: [https://autocare-frontend.onrender.com/](https://autocare-frontend.onrender.com/)
- **Admin App**: [https://autocare-frontend.onrender.com/admin.html](https://autocare-frontend.onrender.com/admin.html)

## Directory Structure

```
AutoCare/
├── backend/
│   ├── main.py
│   ├── faqs.json
│   ├── escalations.json
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── admin.html
    ├── script.js
    └── style.css
```

## Setup & Running

### Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```
Runs on `http://127.0.0.1:8000` (API docs at `http://127.0.0.1:8000/docs`).

### Frontend

```bash
cd frontend
python -m http.server 3000
```
- Customer App: `http://127.0.0.1:3000/index.html`
- Admin App: `http://127.0.0.1:3000/admin.html`

### Admin API Key

Default development key: `admin-secret-key`

## API Endpoints

- `POST /api/chat` - Query matching
- `GET /api/qa` - Get all FAQs
- `POST /api/qa` - Add FAQ (Auth required)
- `DELETE /api/qa/{id}` - Delete FAQ (Auth required)
- `POST /api/upload-pdf` - Ingest PDF FAQs (Auth required)
- `GET /api/escalations` - View unanswered queries (Auth required)
