import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://review_evidence:review_evidence@localhost:5432/review_evidence",
)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
