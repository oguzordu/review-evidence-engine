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
