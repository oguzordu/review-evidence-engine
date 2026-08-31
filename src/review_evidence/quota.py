"""Canli /ask cagrilari icin gunluk paylasilan butce + IP basina limit.

Prod'da (DEMO_MODE) Gemini'nin ~20/gun ucretsiz kotasini korur. Bu modul
HTTP katmanini bilmez; sadece usage_log tablosuyla calisir.
"""

import psycopg


def check_live_quota(
    conn: psycopg.Connection,
    ip: str,
    *,
    daily_budget: int,
    per_ip_limit: int,
) -> str:
    """Bugunku kullanim butceyi asmiyorsa kayit atar ve 'ok' doner. Asiyorsa
    'budget_exhausted' veya 'ip_limit' doner, kayit atmaz."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM usage_log WHERE day = CURRENT_DATE")
        if cur.fetchone()["n"] >= daily_budget:
            return "budget_exhausted"

        cur.execute(
            "SELECT count(*) AS n FROM usage_log WHERE day = CURRENT_DATE AND ip = %s",
            (ip,),
        )
        if cur.fetchone()["n"] >= per_ip_limit:
            return "ip_limit"

        cur.execute("INSERT INTO usage_log (ip) VALUES (%s)", (ip,))
    conn.commit()
    return "ok"
