from datetime import datetime, timezone
from urllib.parse import urlencode
import hashlib, hmac, json
from app.security import validate_telegram_init_data

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"

def test_client_crud_archive_and_audit(client):
    created = client.post("/api/v1/clients", json={"name": "Acme", "status": "active"})
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    assert client.get("/api/v1/clients").json()[0]["name"] == "Acme"
    assert client.patch(f"/api/v1/clients/{item_id}", json={"name": "Acme Ltd"}).status_code == 200
    archived = client.post(f"/api/v1/clients/{item_id}/archive")
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    assert client.get("/api/v1/clients").json() == []
    assert len(client.get("/api/v1/activity").json()) >= 3

def test_validation_has_standard_error_shape(client):
    response = client.post("/api/v1/clients", json={"name": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

def test_missing_record_returns_404(client):
    response = client.get("/api/v1/clients/987654")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"

def test_project_task_relationship_and_dashboard(client):
    c = client.post("/api/v1/clients", json={"name": "Client A"})
    p = client.post("/api/v1/projects", json={"name": "Website", "client_id": c.json()["id"], "status": "active"})
    assert p.status_code == 201, p.text
    t = client.post("/api/v1/tasks", json={"title": "Fix login", "project_id": p.json()["id"], "priority": "high"})
    assert t.status_code == 201, t.text
    dash = client.get("/api/v1/dashboard").json()
    assert dash["metrics"] == {"clients": 1, "projects": 1, "open_tasks": 1, "services": 0}

def test_service_status_never_implies_automatic_check(client):
    response = client.post("/api/v1/services", json={"name": "Demo bot", "status": "unknown", "status_source": "unknown"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "unknown"
    assert response.json()["last_checked_at"] is None

def test_service_rejects_non_http_url(client):
    response = client.post("/api/v1/services", json={"name": "Bad", "url": "file:///etc/passwd"})
    assert response.status_code == 422

def test_manual_test_run_and_deployment(client):
    suite = client.post("/api/v1/test-suites", json={"name": "API smoke"})
    assert suite.status_code == 201, suite.text
    run = client.post(f"/api/v1/test-suites/{suite.json()['id']}/runs", json={"status": "passed", "duration_ms": 123, "note": "Записано оператором"})
    assert run.status_code == 201, run.text
    assert run.json()["source"] == "manual"
    deploy = client.post("/api/v1/deployments", json={"version": "0.1.0", "environment": "local", "status": "recorded"})
    assert deploy.status_code == 201, deploy.text
    assert deploy.json()["source"] == "manual"

def test_telegram_init_data_signature_and_expiration():
    token = "123456:fake-test-token"
    now = int(datetime.now(timezone.utc).timestamp())
    values = {"auth_date": str(now), "user": json.dumps({"id": 42, "first_name": "Test"}, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(values.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    signed = urlencode({**values, "hash": digest})
    assert validate_telegram_init_data(signed, token, 300, now=now)["user_id"] == "42"
    try:
        validate_telegram_init_data(signed, "wrong-token", 300, now=now)
        assert False, "Invalid token must fail"
    except ValueError:
        pass
    old = {"auth_date": str(now - 1000), "user": values["user"]}
    old_check = "\n".join(f"{k}={v}" for k, v in sorted(old.items()))
    old_hash = hmac.new(hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest(), old_check.encode(), hashlib.sha256).hexdigest()
    try:
        validate_telegram_init_data(urlencode({**old, "hash": old_hash}), token, 300, now=now)
        assert False, "Expired data must fail"
    except ValueError:
        pass

def test_related_object_ids_are_validated(client):
    bad_project = client.post("/api/v1/projects", json={"name": "Orphan", "client_id": 99999})
    assert bad_project.status_code == 422
    bad_task = client.post("/api/v1/tasks", json={"title": "Orphan task", "project_id": 99999})
    assert bad_task.status_code == 422

def test_local_mode_configuration_is_loopback_only(monkeypatch):
    from app.config import settings
    old = (settings.local_dev_mode, settings.debug, settings.bind_host)
    try:
        settings.local_dev_mode = True
        settings.debug = True
        settings.bind_host = "0.0.0.0"
        try:
            settings.validate()
            assert False, "Dev bypass must reject a non-loopback bind"
        except RuntimeError:
            pass
    finally:
        settings.local_dev_mode, settings.debug, settings.bind_host = old


def _signed_init_data(token: str, user_id: int, auth_date: int) -> str:
    values = {
        "auth_date": str(auth_date),
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**values, "hash": digest})


def test_telegram_login_requires_an_explicit_local_account_link(client, monkeypatch):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import User

    token = "123456:fake-test-token"
    monkeypatch.setattr(settings, "telegram_bot_token", token)
    client.cookies.clear()
    now = int(datetime.now(timezone.utc).timestamp())

    assert client.get("/api/v1/clients").status_code == 401
    assert client.get("/api/v1/clients", headers={"X-Telegram-Init-Data": "not-valid"}).status_code == 401
    outsider = _signed_init_data(token, 43, now)
    assert client.post("/api/v1/auth/telegram", headers={"X-Telegram-Init-Data": outsider}).status_code == 403

    owner = _signed_init_data(token, 42, now)
    assert client.post("/api/v1/auth/telegram", headers={"X-Telegram-Init-Data": owner}).status_code == 403
    with SessionLocal() as session:
        user = session.query(User).filter_by(username="test-owner").one()
        user.telegram_user_id = "42"
        session.commit()
    auth_response = client.post("/api/v1/auth/telegram", headers={"X-Telegram-Init-Data": owner})
    assert auth_response.status_code == 200
    # initData is exchanged for a server-side session; it is not treated as a bearer credential on every API call.
    assert client.get("/api/v1/clients").status_code == 200


def test_telegram_init_data_rejects_duplicate_parameters_and_future_dates():
    token = "123456:fake-test-token"
    now = int(datetime.now(timezone.utc).timestamp())
    valid = _signed_init_data(token, 42, now)
    try:
        validate_telegram_init_data(valid + "&auth_date=" + str(now), token, 300, now=now)
        assert False, "Duplicate parameters must fail"
    except ValueError:
        pass

    future = _signed_init_data(token, 42, now + 61)
    try:
        validate_telegram_init_data(future, token, 300, now=now)
        assert False, "Unexpected future auth_date must fail"
    except ValueError:
        pass


def test_get_settings_returns_defaults_without_mutating_database(client):
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import AppSetting

    response = client.get("/api/v1/settings")
    assert response.status_code == 200, response.text
    rows = {item["key"]: item for item in response.json()}
    assert rows["display_name"]["value"] == "BOTVEX Control Center"
    assert rows["timezone"]["value"] == "Europe/Moscow"

    # GET must not persist defaults or otherwise mutate the database.
    with SessionLocal() as session:
        assert session.scalars(select(AppSetting)).all() == []

    assert rows["display_name"]["updated_at"] is None


def test_archived_client_can_be_restored_through_explicit_endpoint(client):
    created = client.post("/api/v1/clients", json={"name": "Restore customer"})
    assert created.status_code == 201, created.text
    client_id = created.json()["id"]
    archived = client.post(f"/api/v1/clients/{client_id}/archive")
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    restored = client.post(f"/api/v1/clients/{client_id}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["is_archived"] is False
    assert client.get("/api/v1/clients").json()[0]["id"] == client_id
    activity = client.get("/api/v1/activity?entity_type=client").json()
    assert any(row["action"] == "restored" and row["entity_id"] == client_id for row in activity)



def test_ssrf_guard_rejects_loopback_and_private_ips_on_service_probe(client):
    for forbidden_url in [
        "http://127.0.0.1:8000/health",
        "http://10.0.0.1/health",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.1/status",
    ]:
        svc = client.post("/api/v1/services", json={"name": f"SSRF test {forbidden_url}", "health_endpoint": forbidden_url})
        assert svc.status_code == 201, svc.text
        probe = client.post(f"/api/v1/services/{svc.json()['id']}/probe")
        assert probe.status_code == 422, f"Expected 422 SSRF rejection for {forbidden_url}, got {probe.status_code}"


def test_hot_sqlite_backup_creates_verified_copy_and_logs_activity(tmp_path):
    import sqlite3
    from app.backup_db import backup_sqlite_database

    src_db = tmp_path / "source.db"
    dst_db = tmp_path / "backup" / "snapshot.db"
    with sqlite3.connect(str(src_db)) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO sample (name) VALUES ('botvex')")
        conn.commit()

    result = backup_sqlite_database(dst_db, database_url=f"sqlite:///{src_db}")
    assert result == dst_db.resolve()
    assert dst_db.exists()
    with sqlite3.connect(str(dst_db)) as verify_conn:
        assert verify_conn.execute("SELECT name FROM sample").fetchone()[0] == "botvex"
