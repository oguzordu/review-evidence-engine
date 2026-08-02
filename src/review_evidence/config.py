import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.environ.get("REVIEW_EVIDENCE_DB", DATA_DIR / "reviews.db"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
