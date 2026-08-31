"""Ortak test altyapisi.

Testler gercek PostgreSQL'e baglanir (docker compose ile ayaga kalkan 'db'
servisi) ama ayri bir veritabanina (TEST_DATABASE_URL) -- boylece pytest
calisan uygulamanin verisini silmez. Test veritabani yoksa otomatik olusturulur.
Her testten once reviews tablosu temizlenir, boylece testler birbirini etkilemez.
"""

import psycopg
import pytest

from review_evidence.config import DATABASE_URL, TEST_DATABASE_URL
from review_evidence.db import connect, init_schema


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_database():
    """TEST_DATABASE_URL'deki veritabanini (yoksa) olusturur."""
    test_db_name = TEST_DATABASE_URL.rsplit("/", 1)[-1]
    admin = psycopg.connect(DATABASE_URL, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (test_db_name,)
            )
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{test_db_name}"')
    finally:
        admin.close()


@pytest.fixture()
def db_conn():
    """Temiz bir reviews tablosuyla test veritabanina baglanti verir."""
    conn = connect(TEST_DATABASE_URL)
    init_schema(conn)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE reviews, usage_log RESTART IDENTITY")
    conn.commit()
    yield conn
    conn.close()
