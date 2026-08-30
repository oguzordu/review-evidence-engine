"""Ortak test altyapisi.

Testler gercek PostgreSQL'e baglanir (docker compose ile ayaga kalkan 'db'
servisi). Her testten once tablo temizlenir, boylece testler birbirini
etkilemez.
"""

import pytest

from review_evidence.config import DATABASE_URL
from review_evidence.db import connect, init_schema


@pytest.fixture()
def db_conn():
    """Temiz bir reviews tablosuyla gercek bir PostgreSQL baglantisi verir."""
    conn = connect(DATABASE_URL)
    init_schema(conn)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE reviews RESTART IDENTITY")
    conn.commit()
    yield conn
    conn.close()
