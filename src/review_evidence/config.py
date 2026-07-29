import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.environ.get("REVIEW_EVIDENCE_DB", DATA_DIR / "reviews.db"))