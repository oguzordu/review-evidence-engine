from fastapi.testclient import TestClient

from review_evidence.main import app, get_conn

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_reviews_returns_only_matching_product(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reviews (product_id, raw_text, clean_text)"
            " VALUES (%s, %s, %s)",
            ("p1", "Ürün güzel", "ürün güzel"),
        )
        cur.execute(
            "INSERT INTO reviews (product_id, raw_text, clean_text)"
            " VALUES (%s, %s, %s)",
            ("p2", "Kargo geç", "kargo geç"),
        )
    db_conn.commit()

    def override_get_conn():
        yield db_conn

    app.dependency_overrides[get_conn] = override_get_conn
    try:
        response = client.get("/products/p1/reviews")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["reviews"][0]["raw_text"] == "Ürün güzel"


def test_list_reviews_returns_empty_for_unknown_product(db_conn):
    def override_get_conn():
        yield db_conn

    app.dependency_overrides[get_conn] = override_get_conn
    try:
        response = client.get("/products/yok/reviews")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_ask_returns_503_without_gemini_key(db_conn, monkeypatch):
    import review_evidence.main as main_module

    monkeypatch.setattr(main_module, "_client", None)

    def override_get_conn():
        yield db_conn

    app.dependency_overrides[get_conn] = override_get_conn
    try:
        response = client.get("/products/p1/ask", params={"question": "pil nasil"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_ask_serves_precomputed_in_demo_mode(db_conn, monkeypatch):
    import review_evidence.main as m

    monkeypatch.setattr(m, "DEMO_MODE", True)
    monkeypatch.setattr(
        m, "_demo_qa", {"p1": {"ürün kaliteli mi": {"relevant_count": 7, "positive_count": 7}}}
    )
    monkeypatch.setattr(m, "_client", object())

    def boom(*a, **k):
        raise AssertionError("LLM cagrilmamaliydi")

    monkeypatch.setattr(m, "build_consensus", boom)

    def override():
        yield db_conn

    m.app.dependency_overrides[m.get_conn] = override
    try:
        r = client.get("/products/p1/ask", params={"question": "ÜRÜN kaliteli mi"})
    finally:
        m.app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "precomputed"
    assert body["relevant_count"] == 7


def test_ask_reports_budget_exhausted_in_demo_mode(db_conn, monkeypatch):
    import review_evidence.main as m

    monkeypatch.setattr(m, "DEMO_MODE", True)
    monkeypatch.setattr(m, "_demo_qa", {"p1": {"x": {"relevant_count": 1}}})
    monkeypatch.setattr(m, "_client", object())
    monkeypatch.setattr(m, "DAILY_LIVE_BUDGET", 0)

    def override():
        yield db_conn

    m.app.dependency_overrides[m.get_conn] = override
    try:
        r = client.get("/products/p1/ask", params={"question": "canli bir soru"})
    finally:
        m.app.dependency_overrides.clear()

    assert r.status_code == 200
    assert r.json()["source"] == "budget_exhausted"
