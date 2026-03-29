# LinkDrop 🔗

A lightweight, self-hosted link-in-bio page builder. Share one URL with everyone.

## Stack
- FastAPI + Uvicorn
- SQLite + SQLAlchemy
- Jinja2 templates + TailwindCSS CDN
- Nginx + DuckDNS + Let's Encrypt

## Setup
1. Clone the repo
2. Create venv: `python -m venv venv`
3. Activate: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Linux)
4. Install: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and fill in your values
6. Run: `uvicorn main:app --reload`
