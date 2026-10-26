"""Regression tests for the authenticated client portal and owner login flow."""


def test_login_endpoint_rejects_unknown_user_with_generic_error(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "unknown-account", "password": "incorrect-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Неверный логин или пароль"


def test_client_portal_requires_an_authenticated_account(client):
    client.cookies.clear()
    response = client.get("/api/v1/portal/orders")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "http_error"


def test_login_sets_http_only_cookie_and_logout_revokes_session(client):
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "TEST-OWNER", "password": "test-owner-password-long"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "test-owner"
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert response.json()["permissions"]["*"] == "all"
    assert client.get("/api/v1/auth/me").status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/clients").status_code == 401


def test_one_time_owner_bootstrap_hashes_password_and_never_overwrites_existing_user():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    import secrets
    from app.auth import verify_password
    from app.bootstrap_owner import bootstrap_owner
    from app.database import Base
    from app.models import Role, User

    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=test_engine)
    try:
        with Session(test_engine, expire_on_commit=False) as db:
            temporary_password = secrets.token_urlsafe(18)
            owner = bootstrap_owner(db, "lshpek", temporary_password)
            assert owner.username == "lshpek"
            assert owner.is_owner is True
            assert owner.must_change_password is True
            assert owner.password_hash != temporary_password
            assert verify_password(owner.password_hash, temporary_password)
            assert any(role.slug == "owner" for role in owner.roles)
            first_hash = owner.password_hash
            try:
                bootstrap_owner(db, "lshpek", "attacker-chosen-password")
                assert False, "Second bootstrap must be rejected"
            except RuntimeError as exc:
                assert "уже существуют" in str(exc)
            stored = db.scalar(select(User).where(User.username == "lshpek"))
            assert stored.password_hash == first_hash
            assert db.scalar(select(Role.id).where(Role.slug == "owner")) is not None
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_temporary_password_forces_password_change_and_revokes_other_sessions(client):
    from fastapi.testclient import TestClient

    created = client.post(
        "/api/v1/admin/users",
        json={"username": "dev-one", "role_slugs": ["developer"]},
    )
    assert created.status_code == 201, created.text
    temporary_password = created.json()["temporary_password"]
    assert temporary_password

    staff = TestClient(client.app)
    login = staff.post("/api/v1/auth/login", json={"username": "dev-one", "password": temporary_password})
    assert login.status_code == 200, login.text
    assert login.json()["must_change_password"] is True
    assert staff.get("/api/v1/projects").status_code == 403

    change = staff.post(
        "/api/v1/auth/change-password",
        json={"current_password": temporary_password, "new_password": "New-strong-passphrase-2026"},
    )
    assert change.status_code == 200, change.text
    assert change.json()["must_change_password"] is False
    # Developer has project permission, but only within explicit assignments.
    assert staff.get("/api/v1/projects").status_code == 200

    assert client.post("/api/v1/auth/login", json={"username": "dev-one", "password": temporary_password}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "dev-one", "password": "New-strong-passphrase-2026"}).status_code == 200


def test_client_portal_is_scoped_and_never_returns_internal_notes_or_messages(client):
    from fastapi.testclient import TestClient

    client_a = client.post("/api/v1/clients", json={"name": "Customer Alpha", "status": "active"}).json()
    client_b = client.post("/api/v1/clients", json={"name": "Customer Beta", "status": "active"}).json()
    order_a = client.post("/api/v1/orders", json={
        "client_id": client_a["id"],
        "title": "Alpha bot",
        "scope": "Build a Telegram bot",
        "client_visible_summary": "Разработка бота Alpha",
        "internal_notes": "INTERNAL-ONLY-SECRET-NOTE",
        "amount": "1500.00",
        "amount_type": "fixed",
        "currency": "RUB",
    })
    assert order_a.status_code == 201, order_a.text
    order_a_id = order_a.json()["id"]
    order_b = client.post("/api/v1/orders", json={
        "client_id": client_b["id"], "title": "Beta bot", "scope": "Build a second bot",
        "client_visible_summary": "Разработка бота Beta", "internal_notes": "Beta internal note",
    })
    assert order_b.status_code == 201, order_b.text
    order_b_id = order_b.json()["id"]

    for status in ("awaiting_proposal_approval", "approved", "in_progress"):
        transition = client.post(f"/api/v1/orders/{order_a_id}/transition", json={"status": status, "message": f"Public stage {status}", "client_visible": True})
        assert transition.status_code == 200, transition.text
    for status in ("awaiting_proposal_approval", "approved"):
        transition = client.post(f"/api/v1/orders/{order_b_id}/transition", json={"status": status, "client_visible": True})
        assert transition.status_code == 200, transition.text

    public_message = client.post(f"/api/v1/orders/{order_a_id}/messages", json={"body": "Client-visible progress update", "is_internal": False})
    internal_message = client.post(f"/api/v1/orders/{order_a_id}/messages", json={"body": "INTERNAL-ONLY-MESSAGE", "is_internal": True})
    assert public_message.status_code == 201, public_message.text
    assert internal_message.status_code == 201, internal_message.text

    create_client_user = client.post("/api/v1/admin/users", json={
        "username": "alpha-client", "role_slugs": ["client"], "customer_id": client_a["id"],
    })
    assert create_client_user.status_code == 201, create_client_user.text
    temp = create_client_user.json()["temporary_password"]
    portal = TestClient(client.app)
    signed_in = portal.post("/api/v1/auth/login", json={"username": "alpha-client", "password": temp})
    assert signed_in.status_code == 200 and signed_in.json()["must_change_password"] is True
    assert portal.post("/api/v1/auth/change-password", json={"current_password": temp, "new_password": "Client-strong-passphrase-2026"}).status_code == 200

    listing = portal.get("/api/v1/portal/orders")
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == order_a_id
    detail = portal.get(f"/api/v1/portal/orders/{order_a_id}")
    assert detail.status_code == 200, detail.text
    assert "internal_notes" not in detail.json()
    assert "scope" not in detail.json()
    assert "INTERNAL-ONLY-SECRET-NOTE" not in detail.text
    assert portal.get(f"/api/v1/portal/orders/{order_b_id}").status_code == 404

    messages = portal.get(f"/api/v1/portal/orders/{order_a_id}/messages")
    assert messages.status_code == 200, messages.text
    assert [row["body"] for row in messages.json()] == ["Client-visible progress update"]
    assert "INTERNAL-ONLY-MESSAGE" not in messages.text
    assert portal.post(f"/api/v1/portal/orders/{order_a_id}/messages", json={"body": "I have a question"}).status_code == 201
    assert portal.post(f"/api/v1/portal/orders/{order_b_id}/messages", json={"body": "Try to reach another client"}).status_code == 404


def test_assigned_developer_cannot_read_an_unassigned_project_by_id(client):
    from fastapi.testclient import TestClient

    first_client = client.post("/api/v1/clients", json={"name": "Project Customer One"}).json()
    second_client = client.post("/api/v1/clients", json={"name": "Project Customer Two"}).json()
    project_a = client.post("/api/v1/projects", json={"name": "Assigned Project", "client_id": first_client["id"]}).json()
    project_b = client.post("/api/v1/projects", json={"name": "Private Project", "client_id": second_client["id"]}).json()
    task_a = client.post("/api/v1/tasks", json={"title": "Assigned task", "project_id": project_a["id"]}).json()
    task_b = client.post("/api/v1/tasks", json={"title": "Private task", "project_id": project_b["id"]}).json()
    new_user = client.post("/api/v1/admin/users", json={"username": "developer-scope", "role_slugs": ["developer"]})
    assert new_user.status_code == 201, new_user.text
    user_id = new_user.json()["user"]["id"]
    assert client.post(f"/api/v1/admin/projects/{project_a['id']}/members", json={"user_id": user_id}).status_code == 201

    dev = TestClient(client.app)
    temp = new_user.json()["temporary_password"]
    assert dev.post("/api/v1/auth/login", json={"username": "developer-scope", "password": temp}).status_code == 200
    assert dev.post("/api/v1/auth/change-password", json={"current_password": temp, "new_password": "Developer-strong-passphrase-2026"}).status_code == 200
    projects = dev.get("/api/v1/projects")
    assert projects.status_code == 200, projects.text
    assert [row["id"] for row in projects.json()] == [project_a["id"]]
    assert dev.get(f"/api/v1/projects/{project_b['id']}").status_code == 404
    tasks = dev.get("/api/v1/tasks")
    assert tasks.status_code == 200, tasks.text
    assert [row["id"] for row in tasks.json()] == [task_a["id"]]
    assert dev.get(f"/api/v1/tasks/{task_b['id']}").status_code == 404
    update_assigned = dev.patch(f"/api/v1/tasks/{task_a['id']}", json={"title": "Updated assigned task"})
    assert update_assigned.status_code == 200, update_assigned.text
    assert update_assigned.json()["title"] == "Updated assigned task"


def test_order_list_is_paginated_and_returns_total(client):
    customer = client.post("/api/v1/clients", json={"name": "List Customer"}).json()
    ids = []
    for index in range(3):
        response = client.post("/api/v1/orders", json={
            "client_id": customer["id"], "title": f"Order {index}", "scope": "Test order list",
        })
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    page = client.get("/api/v1/orders?limit=2&offset=1")
    assert page.status_code == 200, page.text
    payload = page.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2 and payload["offset"] == 1
    assert len(payload["items"]) == 2
    assert len({row["id"] for row in payload["items"]}) == 2


def test_assigned_developer_cannot_create_unlinked_order(client):
    from fastapi.testclient import TestClient

    customer = client.post("/api/v1/clients", json={"name": "Order scope customer"}).json()
    project = client.post("/api/v1/projects", json={"name": "Assigned project for order", "client_id": customer["id"]}).json()
    created = client.post("/api/v1/admin/users", json={"username": "order-developer", "role_slugs": ["developer"]})
    assert created.status_code == 201, created.text
    assert client.post(f"/api/v1/admin/projects/{project['id']}/members", json={"user_id": created.json()['user']['id']}).status_code == 201
    dev = TestClient(client.app)
    password = created.json()["temporary_password"]
    assert dev.post("/api/v1/auth/login", json={"username": "order-developer", "password": password}).status_code == 200
    assert dev.post("/api/v1/auth/change-password", json={"current_password": password, "new_password": "A-strong-password-for-dev-2026"}).status_code == 200
    response = dev.post("/api/v1/orders", json={
        "client_id": customer["id"], "title": "Unlinked order", "scope": "Attempt without project",
    })
    assert response.status_code in (403, 404)


def test_log_access_does_not_allow_unassigned_service_id(client):
    from fastapi.testclient import TestClient

    customer = client.post("/api/v1/clients", json={"name": "Log scope customer"}).json()
    project = client.post("/api/v1/projects", json={"name": "Private service project", "client_id": customer["id"]}).json()
    service = client.post("/api/v1/services", json={"name": "Private service", "project_id": project["id"]}).json()
    user = client.post("/api/v1/admin/users", json={"username": "log-scope-dev", "role_slugs": ["developer"]}).json()
    assert client.post(f"/api/v1/admin/projects/{project['id']}/members", json={"user_id": user['user']['id']}).status_code == 201
    dev = TestClient(client.app)
    temp = user["temporary_password"]
    assert dev.post("/api/v1/auth/login", json={"username": "log-scope-dev", "password": temp}).status_code == 200
    assert dev.post("/api/v1/auth/change-password", json={"current_password": temp, "new_password": "Log-scope-developer-password-2026"}).status_code == 200
    assert dev.get(f"/api/v1/services/{service['id']}").status_code == 200
    other_project = client.post("/api/v1/projects", json={"name": "Other project", "client_id": customer['id']}).json()
    other_service = client.post("/api/v1/services", json={"name": "Unassigned service", "project_id": other_project['id']}).json()
    response = dev.post("/api/v1/log-entries", json={"service_id": other_service['id'], "message": "scope escape"})
    assert response.status_code in (403, 404)


def test_custom_role_permission_catalog_and_record_scope_are_enforced(client):
    from fastapi.testclient import TestClient

    catalog = client.get("/api/v1/admin/permissions")
    assert catalog.status_code == 200, catalog.text
    assert {row["key"] for row in catalog.json()} >= {"projects:view", "admin:users:create", "orders:view"}

    role = client.post("/api/v1/admin/roles", json={
        "slug": "project-reader",
        "name": "Project reader",
        "description": "Only explicitly assigned projects",
        "permissions": {"projects:view": "assigned"},
    })
    assert role.status_code == 201, role.text
    assert role.json()["permissions"] == {"projects:view": "assigned"}

    customer = client.post("/api/v1/clients", json={"name": "RBAC customer"}).json()
    project_a = client.post("/api/v1/projects", json={"name": "Scope A", "client_id": customer["id"]}).json()
    project_b = client.post("/api/v1/projects", json={"name": "Scope B", "client_id": customer["id"]}).json()
    account = client.post("/api/v1/admin/users", json={"username": "project-reader-1", "role_slugs": ["project-reader"]})
    assert account.status_code == 201, account.text
    user_id = account.json()["user"]["id"]
    assert client.post(f"/api/v1/admin/projects/{project_a['id']}/members", json={"user_id": user_id}).status_code == 201

    scoped = TestClient(client.app)
    password = account.json()["temporary_password"]
    assert scoped.post("/api/v1/auth/login", json={"username": "project-reader-1", "password": password}).status_code == 200
    assert scoped.post("/api/v1/auth/change-password", json={"current_password": password, "new_password": "Project-reader-password-2026"}).status_code == 200
    assert [p["id"] for p in scoped.get("/api/v1/projects").json()] == [project_a["id"]]
    assert scoped.get(f"/api/v1/projects/{project_b['id']}").status_code == 404

    # Permission changes are evaluated on subsequent requests, without a re-login.
    changed = client.patch(f"/api/v1/admin/roles/{role.json()['id']}", json={"permissions": {}})
    assert changed.status_code == 200, changed.text
    assert scoped.get("/api/v1/projects").status_code == 403


def test_mutation_from_untrusted_browser_origin_is_rejected(client):
    response = client.post(
        "/api/v1/clients",
        json={"name": "must not be created"},
        headers={"Origin": "https://attacker.invalid"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_forbidden"
    assert client.get("/api/v1/clients?q=must%20not%20be%20created").json() == []


def test_order_archive_cannot_be_changed_through_generic_update(client):
    customer = client.post("/api/v1/clients", json={"name": "Archive control customer"}).json()
    order = client.post("/api/v1/orders", json={
        "client_id": customer["id"], "title": "Archive control order", "scope": "Archive should require its own permission",
    })
    assert order.status_code == 201, order.text
    response = client.patch(f"/api/v1/orders/{order.json()['id']}", json={"is_archived": True})
    assert response.status_code == 422, response.text
    assert client.get(f"/api/v1/orders/{order.json()['id']}").json()["is_archived"] is False


def test_approved_order_commercial_scope_cannot_be_silently_changed(client):
    customer = client.post("/api/v1/clients", json={"name": "Approved order customer"}).json()
    order = client.post("/api/v1/orders", json={
        "client_id": customer["id"], "title": "Approved order", "scope": "Original agreed scope",
        "amount": "100.00", "amount_type": "fixed",
    })
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    assert client.post(f"/api/v1/orders/{order_id}/transition", json={"status": "awaiting_proposal_approval"}).status_code == 200
    assert client.post(f"/api/v1/orders/{order_id}/transition", json={"status": "approved"}).status_code == 200
    response = client.patch(f"/api/v1/orders/{order_id}", json={"scope": "Changed scope", "amount": "250.00"})
    assert response.status_code == 409, response.text
    persisted = client.get(f"/api/v1/orders/{order_id}").json()
    assert persisted["scope"] == "Original agreed scope"
    assert persisted["amount"] == "100.00"


def test_assigned_scoped_log_permission_checks_linked_service(client):
    from fastapi.testclient import TestClient

    role = client.post("/api/v1/admin/roles", json={
        "slug": "assigned-log-writer", "name": "Assigned log writer",
        "permissions": {"logs:create": "assigned", "services:view": "assigned"},
    })
    assert role.status_code == 201, role.text
    customer = client.post("/api/v1/clients", json={"name": "Scoped log customer"}).json()
    assigned_project = client.post("/api/v1/projects", json={"name": "Assigned log project", "client_id": customer["id"]}).json()
    other_project = client.post("/api/v1/projects", json={"name": "Other log project", "client_id": customer["id"]}).json()
    assigned_service = client.post("/api/v1/services", json={"name": "Assigned service", "project_id": assigned_project["id"]}).json()
    other_service = client.post("/api/v1/services", json={"name": "Other service", "project_id": other_project["id"]}).json()
    account = client.post("/api/v1/admin/users", json={"username": "log-writer-1", "role_slugs": ["assigned-log-writer"]})
    assert account.status_code == 201, account.text
    user_id = account.json()["user"]["id"]
    assert client.post(f"/api/v1/admin/projects/{assigned_project['id']}/members", json={"user_id": user_id}).status_code == 201
    scoped = TestClient(client.app)
    temp = account.json()["temporary_password"]
    assert scoped.post("/api/v1/auth/login", json={"username": "log-writer-1", "password": temp}).status_code == 200
    assert scoped.post("/api/v1/auth/change-password", json={"current_password": temp, "new_password": "Log-writer-strong-passphrase-2026"}).status_code == 200
    allowed = scoped.post("/api/v1/log-entries", json={"service_id": assigned_service["id"], "message": "allowed scoped record"})
    assert allowed.status_code == 201, allowed.text
    denied = scoped.post("/api/v1/log-entries", json={"service_id": other_service["id"], "message": "must not link unrelated service"})
    assert denied.status_code in (403, 404), denied.text


def test_order_archive_and_restore_are_explicit_and_audited(client):
    customer = client.post("/api/v1/clients", json={"name": "Order archive customer"}).json()
    order = client.post("/api/v1/orders", json={
        "client_id": customer["id"], "title": "Archivable order", "scope": "Keep history when archived",
    })
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    assert "orders:archive" in client.get("/api/v1/admin/permissions").text
    archived = client.post(f"/api/v1/orders/{order_id}/archive")
    assert archived.status_code == 200, archived.text
    assert archived.json()["is_archived"] is True
    assert client.get(f"/api/v1/orders/{order_id}").status_code == 404
    assert client.get("/api/v1/orders?include_archived=true").json()["total"] == 1
    restored = client.post(f"/api/v1/orders/{order_id}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["is_archived"] is False
    events = client.get(f"/api/v1/orders/{order_id}/events").json()
    assert {row["event_type"] for row in events} >= {"created", "archived", "restored"}


def test_authorization_seed_is_idempotent_and_fills_missing_system_grants():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.bootstrap_owner import seed_authorization
    from app.database import Base
    from app.models import Role

    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=test_engine)
    try:
        with Session(test_engine, expire_on_commit=False) as db:
            seed_authorization(db)
            manager = db.scalar(select(Role).where(Role.slug == "manager"))
            assert manager is not None
            existing_grant = next(grant for grant in manager.grants if grant.permission.key == "clients:view")
            existing_grant.scope = "assigned"
            missing_grant = next(grant for grant in manager.grants if grant.permission.key == "orders:archive")
            manager.grants.remove(missing_grant)
            db.flush()

            seed_authorization(db)

            db.refresh(manager)
            grants = {grant.permission.key: grant.scope for grant in manager.grants}
            assert grants["clients:view"] == "assigned", "Reseeding must preserve deliberately customized existing scopes"
            assert grants["orders:archive"] == "all", "Reseeding must add a missing default system-role permission"
            assert len(grants) == len(set(grants)), "Reseeding must not create duplicate grants"
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_administrator_cannot_grant_owner_only_permissions_or_rebind_owner(client):
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import User

    privileged_role = client.post("/api/v1/admin/roles", json={
        "slug": "settings-privileged",
        "name": "Restricted settings role",
        "permissions": {"settings:edit": "all", "admin:users:reset_password": "all"},
    })
    assert privileged_role.status_code == 201, privileged_role.text

    admin_creation = client.post("/api/v1/admin/users", json={
        "username": "ops-administrator", "role_slugs": ["administrator"],
    })
    assert admin_creation.status_code == 201, admin_creation.text
    admin = TestClient(client.app)
    password = admin_creation.json()["temporary_password"]
    assert admin.post("/api/v1/auth/login", json={"username": "ops-administrator", "password": password}).status_code == 200
    assert admin.post("/api/v1/auth/change-password", json={
        "current_password": password, "new_password": "Administrator-strong-password-2026",
    }).status_code == 200

    attempted_assignment = admin.post("/api/v1/admin/users", json={
        "username": "privileged-assignment", "role_slugs": ["settings-privileged"],
    })
    assert attempted_assignment.status_code == 403, attempted_assignment.text

    attempted_role_escalation = admin.post("/api/v1/admin/roles", json={
        "slug": "administrator-settings-escalation",
        "name": "Should be denied",
        "permissions": {"settings:edit": "all"},
    })
    assert attempted_role_escalation.status_code == 403, attempted_role_escalation.text

    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.username == "test-owner"))
        assert owner is not None
        owner_id = owner.id
    attempted_owner_rebind = admin.patch(f"/api/v1/admin/users/{owner_id}", json={"telegram_user_id": "999999999"})
    assert attempted_owner_rebind.status_code == 403, attempted_owner_rebind.text


def test_owner_can_inspect_and_revoke_sessions_without_exposing_session_tokens(client):
    from fastapi.testclient import TestClient
    created = client.post("/api/v1/admin/users", json={"username": "session-review", "role_slugs": ["developer"]})
    assert created.status_code == 201, created.text
    temporary = created.json()["temporary_password"]
    staff = TestClient(client.app)
    assert staff.post("/api/v1/auth/login", json={"username": "session-review", "password": temporary}).status_code == 200
    user_id = created.json()["user"]["id"]

    sessions = client.get(f"/api/v1/admin/users/{user_id}/sessions")
    assert sessions.status_code == 200, sessions.text
    payload = sessions.json()
    rows = payload["items"]
    assert payload["total"] == 1
    assert len(rows) == 1
    session_id = rows[0]["id"]
    assert rows[0]["is_active"] is True
    assert "token" not in rows[0] and "token_hash" not in rows[0]

    revoke = client.post(f"/api/v1/admin/users/{user_id}/sessions/{session_id}/revoke")
    assert revoke.status_code == 200, revoke.text
    assert staff.get("/api/v1/auth/me").status_code == 401
    refreshed = client.get(f"/api/v1/admin/users/{user_id}/sessions")
    assert refreshed.status_code == 200
    assert refreshed.json()["items"][0]["is_active"] is False


def test_owner_recovery_resets_only_existing_owner_and_revokes_sessions():
    from datetime import timedelta
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.auth import hash_password, token_digest, verify_password
    from app.database import Base
    from app.models import ActivityEvent, AuthSession, Role, User, utcnow
    from app.bootstrap_owner import seed_authorization
    from app.recover_owner import recover_owner_password

    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=test_engine)
    try:
        with Session(test_engine, expire_on_commit=False) as db:
            seed_authorization(db)
            owner_role = db.scalar(select(Role).where(Role.slug == "owner"))
            owner = User(username="lshpek", password_hash=hash_password("Old-owner-password-2026"), is_owner=True,
                         must_change_password=False, roles=[owner_role])
            db.add(owner)
            db.flush()
            old_token = "existing-session-token"
            session_row = AuthSession(user_id=owner.id, token_hash=token_digest(old_token), created_at=utcnow(),
                                      expires_at=utcnow() + timedelta(hours=8))
            db.add(session_row)
            db.commit()

            assert recover_owner_password(db, "lshpek", "Temporary-recovery-passphrase-2026") is True
            db.refresh(owner)
            db.refresh(session_row)
            assert owner.must_change_password is True
            assert verify_password(owner.password_hash, "Temporary-recovery-passphrase-2026")
            assert session_row.revoked_at is not None
            assert db.scalar(select(ActivityEvent.id).where(ActivityEvent.action == "owner_password_recovered")) is not None
            try:
                recover_owner_password(db, "missing-owner", "Another-recovery-password-2026")
                assert False, "Recovery must never create a new owner account"
            except RuntimeError as exc:
                assert "не найден" in str(exc).lower()
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_client_role_cannot_be_combined_with_staff_role(client):
    customer = client.post("/api/v1/clients", json={"name": "Exclusive client role"}).json()
    created = client.post("/api/v1/admin/users", json={
        "username": "mixed-client-staff", "role_slugs": ["client", "manager"], "customer_id": customer["id"],
    })
    assert created.status_code == 422, created.text


def test_client_portal_user_cannot_reach_staff_endpoints_even_if_roles_are_misconfigured(client):
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import Role, User

    customer = client.post("/api/v1/clients", json={"name": "Client isolation customer"}).json()
    order = client.post("/api/v1/orders", json={"client_id": customer["id"], "title": "Client only order", "scope": "Private scope"})
    assert order.status_code == 201, order.text
    assert client.post(f"/api/v1/orders/{order.json()['id']}/transition", json={"status": "awaiting_proposal_approval"}).status_code == 200
    created = client.post("/api/v1/admin/users", json={"username": "portal-isolation", "role_slugs": ["client"], "customer_id": customer["id"]})
    assert created.status_code == 201, created.text
    portal = TestClient(client.app)
    temporary = created.json()["temporary_password"]
    assert portal.post("/api/v1/auth/login", json={"username": "portal-isolation", "password": temporary}).status_code == 200
    assert portal.post("/api/v1/auth/change-password", json={"current_password": temporary, "new_password": "Portal-isolation-passphrase-2026"}).status_code == 200

    with SessionLocal() as db:
        account = db.scalar(select(User).where(User.username == "portal-isolation"))
        manager = db.scalar(select(Role).where(Role.slug == "manager"))
        assert account is not None and manager is not None
        account.roles.append(manager)
        db.commit()

    assert portal.get("/api/v1/portal/orders").status_code == 200
    assert portal.get("/api/v1/orders").status_code == 403
    assert portal.get("/api/v1/clients").status_code == 403
    assert portal.get("/api/v1/admin/users").status_code == 403


def test_production_mutations_require_an_allowed_origin_even_when_origin_is_missing(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "local_dev_mode", False)
    response = client.post("/api/v1/clients", json={"name": "CSRF guard test"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_forbidden"
    assert client.get("/api/v1/clients").json() == []


def test_production_mutations_accept_only_configured_origins(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "local_dev_mode", False)
    denied = client.post(
        "/api/v1/clients",
        json={"name": "Untrusted origin"},
        headers={"Origin": "https://attacker.example"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "origin_forbidden"

    allowed = client.post(
        "/api/v1/clients",
        json={"name": "Trusted origin"},
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert allowed.status_code == 201, allowed.text


def test_login_rate_limits_use_configured_settings(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "login_max_per_identity", 1)
    monkeypatch.setattr(settings, "login_max_per_ip", 100)
    username = "rate-limit-config-check"
    first = client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
    second = client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
    assert first.status_code == 401
    assert second.status_code == 429



def test_administrator_cannot_toggle_is_active_without_suspend_permission(client):
    from fastapi.testclient import TestClient

    admin_created = client.post("/api/v1/admin/users", json={"username": "ops-admin", "role_slugs": ["administrator"]})
    assert admin_created.status_code == 201, admin_created.text
    target_created = client.post("/api/v1/admin/users", json={"username": "target-dev", "role_slugs": ["developer"]})
    assert target_created.status_code == 201, target_created.text
    target_id = target_created.json()["user"]["id"]

    admin_client = TestClient(client.app)
    temp_pw = admin_created.json()["temporary_password"]
    assert admin_client.post("/api/v1/auth/login", json={"username": "ops-admin", "password": temp_pw}).status_code == 200
    assert admin_client.post("/api/v1/auth/change-password", json={
        "current_password": temp_pw,
        "new_password": "Ops-admin-strong-password-2026",
    }).status_code == 200

    # Administrator has admin:users:edit, but NOT admin:users:suspend
    suspend_attempt = admin_client.patch(f"/api/v1/admin/users/{target_id}", json={"is_active": False})
    assert suspend_attempt.status_code == 403, suspend_attempt.text

    # Owner can suspend the account
    owner_suspend = client.patch(f"/api/v1/admin/users/{target_id}", json={"is_active": False})
    assert owner_suspend.status_code == 200 and owner_suspend.json()["is_active"] is False


def test_client_portal_self_service_decisions_and_change_requests(client):
    from fastapi.testclient import TestClient

    customer = client.post("/api/v1/clients", json={"name": "Portal Decision Corp", "status": "active"}).json()
    other_customer = client.post("/api/v1/clients", json={"name": "Other Corp", "status": "active"}).json()

    order = client.post("/api/v1/orders", json={
        "client_id": customer["id"],
        "title": "Enterprise Bot System",
        "scope": "Initial scope v1",
        "amount": "100000.00",
        "amount_type": "fixed",
        "currency": "RUB",
        "target_delivery_date": "2026-11-15",
    }).json()
    other_order = client.post("/api/v1/orders", json={
        "client_id": other_customer["id"],
        "title": "Other Order",
        "scope": "Other scope",
    }).json()
    assert client.post(f"/api/v1/orders/{other_order['id']}/transition", json={"status": "awaiting_proposal_approval"}).status_code == 200

    assert client.post(f"/api/v1/orders/{order['id']}/transition", json={"status": "awaiting_proposal_approval"}).status_code == 200

    created_user = client.post("/api/v1/admin/users", json={
        "username": "portal-decision-client",
        "role_slugs": ["client"],
        "customer_id": customer["id"],
    }).json()
    portal = TestClient(client.app)
    temp_pw = created_user["temporary_password"]
    assert portal.post("/api/v1/auth/login", json={"username": "portal-decision-client", "password": temp_pw}).status_code == 200
    assert portal.post("/api/v1/auth/change-password", json={
        "current_password": temp_pw,
        "new_password": "Client-decision-strong-pass-2026",
    }).status_code == 200

    # Cross-customer decision must return 404
    assert portal.post(f"/api/v1/portal/orders/{other_order['id']}/decision", json={"action": "approve_proposal"}).status_code == 404

    # Client approves proposal
    approved = portal.post(f"/api/v1/portal/orders/{order['id']}/decision", json={
        "action": "approve_proposal",
        "comment": "Условия КП согласованы",
    })
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    # Staff creates a Change Request (+25000 RUB, new delivery date)
    cr = client.post(f"/api/v1/orders/{order['id']}/change-requests", json={
        "title": "Add ERP webhook module",
        "scope_delta": "Webhook integration with retry queue",
        "amount_delta": "25000.00",
        "new_delivery_date": "2026-11-30",
    })
    assert cr.status_code == 201, cr.text
    cr_id = cr.json()["id"]

    # Client approves Change Request in portal -> updates order amount & delivery date
    cr_decided = portal.post(f"/api/v1/portal/orders/{order['id']}/change-requests/{cr_id}/decision", json={
        "status": "approved",
        "decision_note": "Согласовано",
    })
    assert cr_decided.status_code == 200 and cr_decided.json()["status"] == "approved"
    updated_order = portal.get(f"/api/v1/portal/orders/{order['id']}").json()
    assert updated_order["amount"] == "125000.00"
    assert updated_order["target_delivery_date"] == "2026-11-30"

    # Payments ledger: add client payment and internal studio expense
    pay1 = client.post(f"/api/v1/orders/{order['id']}/payments", json={
        "kind": "payment",
        "amount": "50000.00",
        "currency": "RUB",
        "status": "paid",
        "note": "Аванс",
    })
    assert pay1.status_code == 201
    exp1 = client.post(f"/api/v1/orders/{order['id']}/payments", json={
        "kind": "expense",
        "amount": "10000.00",
        "currency": "RUB",
        "status": "paid",
        "note": "Субподряд",
    })
    assert exp1.status_code == 201

    admin_ledger = client.get(f"/api/v1/orders/{order['id']}/payments").json()
    assert admin_ledger["paid_amount"] == "50000.00"
    assert admin_ledger["expenses_amount"] == "10000.00"
    assert admin_ledger["balance_due"] == "75000.00"

    portal_ledger = portal.get(f"/api/v1/portal/orders/{order['id']}/payments").json()
    assert portal_ledger["paid_amount"] == "50000.00"
    assert portal_ledger["balance_due"] == "75000.00"
    assert "expenses_amount" not in portal_ledger
    assert all(item["kind"] == "payment" for item in portal_ledger["items"])
