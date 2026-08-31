"""Onceden hesaplanmis soru-cevaplar (prod demo modu).

data/demo_qa.json'daki cevaplar, DEMO_MODE acikken /ask tarafindan LLM
cagrisi yapmadan servis edilir. Bu modul HTTP ve veritabani bilmez.
"""

import json
from pathlib import Path

from review_evidence.text import normalize


def load_demo_qa(path: "str | Path" = "data/demo_qa.json") -> dict:
    """JSON'u {product_id: {normalize(question): answer}} yapisina indexler.
    Dosya yoksa bos sozluk doner."""
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    out: dict = {}
    for item in data.get("items", []):
        out.setdefault(item["product_id"], {})[normalize(item["question"])] = item["answer"]
    return out


def lookup(demo_qa: dict, product_id: str, question: str) -> "dict | None":
    return demo_qa.get(product_id, {}).get(normalize(question))


def any_for_product(demo_qa: dict, product_id: str) -> "dict | None":
    answers = demo_qa.get(product_id)
    if not answers:
        return None
    return next(iter(answers.values()))
