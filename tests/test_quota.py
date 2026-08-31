from review_evidence.quota import check_live_quota


def _count(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM usage_log")
        return cur.fetchone()["n"]


def test_first_call_is_ok_and_records(db_conn):
    v = check_live_quota(db_conn, "1.1.1.1", daily_budget=15, per_ip_limit=2)
    assert v == "ok"
    assert _count(db_conn) == 1


def test_ip_limit_blocks_third_call_from_same_ip(db_conn):
    for _ in range(2):
        check_live_quota(db_conn, "1.1.1.1", daily_budget=15, per_ip_limit=2)
    v = check_live_quota(db_conn, "1.1.1.1", daily_budget=15, per_ip_limit=2)
    assert v == "ip_limit"
    assert _count(db_conn) == 2


def test_daily_budget_blocks_when_total_reached(db_conn):
    for i in range(3):
        check_live_quota(db_conn, f"9.9.9.{i}", daily_budget=3, per_ip_limit=5)
    v = check_live_quota(db_conn, "9.9.9.99", daily_budget=3, per_ip_limit=5)
    assert v == "budget_exhausted"


def test_old_day_rows_do_not_count(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO usage_log (day, ip) VALUES (CURRENT_DATE - 1, %s)",
            ("1.1.1.1",),
        )
    db_conn.commit()
    v = check_live_quota(db_conn, "1.1.1.1", daily_budget=15, per_ip_limit=2)
    assert v == "ok"
