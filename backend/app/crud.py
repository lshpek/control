from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .access_scopes import ensure_related_scope, scope_query
from .auth import AccessContext, require_permission
from .database import get_db
from .models import ActivityEvent, Client, DeploymentRecord, LogEntry, Project, ProjectAssignment, Service, Task, TestRun, TestSuite, utcnow
from .schemas import (
    ClientCreate, ClientRead, ClientUpdate,
    DeploymentCreate, DeploymentRead, DeploymentUpdate,
    LogEntryCreate, LogEntryRead, LogEntryUpdate,
    ProjectCreate, ProjectRead, ProjectUpdate,
    ServiceCreate, ServiceRead, ServiceUpdate,
    TaskCreate, TaskRead, TaskUpdate,
    TestRunCreate, TestRunRead, TestSuiteCreate, TestSuiteRead, TestSuiteUpdate,
)


def audit(db: Session, entity_type: str, entity_id: int | None, action: str, summary: str, actor: str = "system") -> None:
    db.add(ActivityEvent(actor=actor[:80], entity_type=entity_type, entity_id=entity_id, action=action, summary=summary[:500]))


def _page(query, db: Session, limit: int, offset: int):
    return list(db.scalars(query.limit(limit).offset(offset)).all())


def _validate_relationships(model, data: dict, db: Session) -> None:
    checks = []
    if model is Project and "client_id" in data:
        checks.append((Client, data.get("client_id"), "Клиент не найден"))
    if model in (Task, Service, TestSuite, DeploymentRecord) and "project_id" in data:
        checks.append((Project, data.get("project_id"), "Проект не найден"))
    if model is LogEntry and "service_id" in data:
        checks.append((Service, data.get("service_id"), "Сервис не найден"))
    for target, foreign_id, message in checks:
        if foreign_id is not None and db.get(target, foreign_id) is None:
            raise HTTPException(422, message)


def _permission_resource(entity_type: str) -> str:
    return {
        "client": "clients",
        "project": "projects",
        "task": "tasks",
        "service": "services",
        "log_entry": "logs",
        "test_suite": "test_suites",
        "deployment": "deployments",
    }[entity_type]


def build_crud_router(path: str, entity_type: str, model, create_schema, update_schema, read_schema, display_field: str, searchable: tuple[str, ...] = ()):
    router = APIRouter(prefix=f"/{path}", tags=[entity_type])
    resource = _permission_resource(entity_type)

    @router.get("", response_model=list[read_schema])
    def list_items(
        q: str | None = Query(None, max_length=100),
        include_archived: bool = False,
        limit: int = Query(100, ge=1, le=250),
        offset: int = Query(0, ge=0, le=1000000),
        access: AccessContext = Depends(require_permission(f"{resource}:view")),
        db: Session = Depends(get_db),
    ):
        query = select(model)
        if hasattr(model, "is_archived") and not include_archived:
            query = query.where(model.is_archived.is_(False))
        if q and searchable:
            query = query.where(or_(*[getattr(model, col).ilike(f"%{q[:100]}%") for col in searchable]))
        query = scope_query(query, model, access, db)
        if hasattr(model, "created_at"):
            query = query.order_by(model.created_at.desc(), model.id.desc())
        return _page(query, db, limit, offset)

    @router.post("", response_model=read_schema, status_code=201)
    def create_item(
        payload: create_schema,
        access: AccessContext = Depends(require_permission(f"{resource}:create")),
        db: Session = Depends(get_db),
    ):
        data = payload.model_dump()
        _validate_relationships(model, data, db)
        ensure_related_scope(model, data, access, db)
        if model is Project and access.scope != "all" and not access.is_owner:
            raise HTTPException(status_code=403, detail="Создание проектов доступно только роли с полным доступом")
        obj = model(**data)
        if model is Task and data.get("status") == "done":
            obj.completed_at = utcnow()
        db.add(obj)
        db.flush()
        actor = access.user.username if access.user else "owner"
        audit(db, entity_type, obj.id, "created", f"Создано: {getattr(obj, display_field)}", actor)
        db.commit()
        db.refresh(obj)
        return obj

    @router.get("/{item_id}", response_model=read_schema)
    def get_item(
        item_id: int,
        access: AccessContext = Depends(require_permission(f"{resource}:view")),
        db: Session = Depends(get_db),
    ):
        query = scope_query(select(model), model, access, db).where(model.id == item_id)
        obj = db.scalar(query)
        if not obj:
            raise HTTPException(404, "Запись не найдена")
        return obj

    @router.patch("/{item_id}", response_model=read_schema)
    def update_item(
        item_id: int,
        payload: update_schema,
        access: AccessContext = Depends(require_permission(f"{resource}:edit")),
        db: Session = Depends(get_db),
    ):
        obj = db.scalar(scope_query(select(model), model, access, db).where(model.id == item_id))
        if not obj:
            raise HTTPException(404, "Запись не найдена")
        changes = payload.model_dump(exclude_unset=True)
        _validate_relationships(model, changes, db)
        scope_data = {**changes, "id": obj.id}
        if model in (Task, Service, TestSuite, DeploymentRecord) and "project_id" not in changes:
            scope_data["project_id"] = obj.project_id
        if model is LogEntry and "service_id" not in changes:
            scope_data["service_id"] = obj.service_id
        ensure_related_scope(model, scope_data, access, db)
        if model is Project and access.scope != "all" and "client_id" in changes:
            raise HTTPException(status_code=403, detail="Нельзя менять клиента проекта в рамках ограниченного доступа")
        for key, value in changes.items():
            setattr(obj, key, value)
        if model is Task and changes.get("status") == "done" and obj.completed_at is None:
            obj.completed_at = utcnow()
        elif model is Task and changes.get("status") and changes["status"] != "done":
            obj.completed_at = None
        actor = access.user.username if access.user else "owner"
        audit(db, entity_type, obj.id, "updated", f"Изменено: {getattr(obj, display_field)}", actor)
        db.commit()
        db.refresh(obj)
        return obj

    if hasattr(model, "is_archived"):
        @router.post("/{item_id}/archive", response_model=read_schema)
        def archive_item(
            item_id: int,
            access: AccessContext = Depends(require_permission(f"{resource}:archive")),
            db: Session = Depends(get_db),
        ):
            obj = db.scalar(scope_query(select(model), model, access, db).where(model.id == item_id))
            if not obj:
                raise HTTPException(404, "Запись не найдена")
            obj.is_archived = True
            actor = access.user.username if access.user else "owner"
            audit(db, entity_type, obj.id, "archived", f"Архивировано: {getattr(obj, display_field)}", actor)
            db.commit()
            db.refresh(obj)
            return obj

        @router.post("/{item_id}/restore", response_model=read_schema)
        def restore_item(
            item_id: int,
            access: AccessContext = Depends(require_permission(f"{resource}:restore")),
            db: Session = Depends(get_db),
        ):
            obj = db.scalar(scope_query(select(model), model, access, db).where(model.id == item_id))
            if not obj:
                raise HTTPException(404, "Запись не найдена")
            if not obj.is_archived:
                raise HTTPException(status_code=409, detail="Запись уже активна")
            obj.is_archived = False
            actor = access.user.username if access.user else "owner"
            audit(db, entity_type, obj.id, "restored", f"Восстановлено: {getattr(obj, display_field)}", actor)
            db.commit()
            db.refresh(obj)
            return obj
    return router


clients_router = build_crud_router("clients", "client", Client, ClientCreate, ClientUpdate, ClientRead, "name", ("name", "contact_person", "contacts"))
projects_router = build_crud_router("projects", "project", Project, ProjectCreate, ProjectUpdate, ProjectRead, "name", ("name", "description"))
tasks_router = build_crud_router("tasks", "task", Task, TaskCreate, TaskUpdate, TaskRead, "title", ("title", "description"))
services_router = build_crud_router("services", "service", Service, ServiceCreate, ServiceUpdate, ServiceRead, "name", ("name", "type", "hosting"))
log_router = build_crud_router("log-entries", "log_entry", LogEntry, LogEntryCreate, LogEntryUpdate, LogEntryRead, "message", ("message", "level"))
deploy_router = build_crud_router("deployments", "deployment", DeploymentRecord, DeploymentCreate, DeploymentUpdate, DeploymentRead, "version", ("version", "environment", "status"))

suite_router = APIRouter(prefix="/test-suites", tags=["test_suites"])


@suite_router.get("", response_model=list[TestSuiteRead])
def list_suites(
    limit: int = Query(100, ge=1, le=250), offset: int = Query(0, ge=0, le=1000000),
    access: AccessContext = Depends(require_permission("test_suites:view")), db: Session = Depends(get_db),
):
    query = scope_query(select(TestSuite).order_by(TestSuite.created_at.desc(), TestSuite.id.desc()), TestSuite, access, db)
    return _page(query, db, limit, offset)


@suite_router.post("", response_model=TestSuiteRead, status_code=201)
def create_suite(payload: TestSuiteCreate, access: AccessContext = Depends(require_permission("test_suites:create")), db: Session = Depends(get_db)):
    data = payload.model_dump()
    _validate_relationships(TestSuite, data, db)
    ensure_related_scope(TestSuite, data, access, db)
    obj = TestSuite(**data)
    db.add(obj)
    db.flush()
    audit(db, "test_suite", obj.id, "created", f"Создан набор тестов: {obj.name}", access.user.username if access.user else "owner")
    db.commit()
    db.refresh(obj)
    return obj


@suite_router.patch("/{suite_id}", response_model=TestSuiteRead)
def update_suite(suite_id: int, payload: TestSuiteUpdate, access: AccessContext = Depends(require_permission("test_suites:edit")), db: Session = Depends(get_db)):
    obj = db.scalar(scope_query(select(TestSuite), TestSuite, access, db).where(TestSuite.id == suite_id))
    if not obj:
        raise HTTPException(404, "Набор тестов не найден")
    changes = payload.model_dump(exclude_unset=True)
    _validate_relationships(TestSuite, changes, db)
    ensure_related_scope(TestSuite, {**changes, "id": obj.id}, access, db)
    for key, value in changes.items():
        setattr(obj, key, value)
    audit(db, "test_suite", obj.id, "updated", f"Изменён набор тестов: {obj.name}", access.user.username if access.user else "owner")
    db.commit()
    db.refresh(obj)
    return obj


@suite_router.get("/{suite_id}/runs", response_model=list[TestRunRead])
def list_runs(suite_id: int, access: AccessContext = Depends(require_permission("test_suites:view")), db: Session = Depends(get_db)):
    suite = db.scalar(scope_query(select(TestSuite), TestSuite, access, db).where(TestSuite.id == suite_id))
    if not suite:
        raise HTTPException(404, "Набор тестов не найден")
    return list(db.scalars(select(TestRun).where(TestRun.suite_id == suite_id).order_by(TestRun.created_at.desc(), TestRun.id.desc())).all())


@suite_router.post("/{suite_id}/runs", response_model=TestRunRead, status_code=201)
def record_run(suite_id: int, payload: TestRunCreate, access: AccessContext = Depends(require_permission("test_suites:create")), db: Session = Depends(get_db)):
    suite = db.scalar(scope_query(select(TestSuite), TestSuite, access, db).where(TestSuite.id == suite_id))
    if not suite:
        raise HTTPException(404, "Набор тестов не найден")
    data = payload.model_dump()
    data["source"] = "manual"
    run = TestRun(suite_id=suite_id, **data)
    suite.last_status = payload.status
    db.add(run)
    db.flush()
    audit(db, "test_run", run.id, "recorded", f"Результат тестов «{suite.name}»: {payload.status} (введён вручную)", access.user.username if access.user else "owner")
    db.commit()
    db.refresh(run)
    return run


import ipaddress
import socket
from urllib.parse import urlsplit
import httpx


def validate_public_probe_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Разрешены только абсолютные URL http/https без учётных данных")
    hostname = parsed.hostname.strip()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        literal_ip = ipaddress.ip_address(hostname)
        resolved_ips = [literal_ip]
    except ValueError:
        try:
            infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise HTTPException(status_code=422, detail="Не удалось разрешить DNS-имя проверяемого узла") from exc
        resolved_ips = []
        for info in infos:
            sockaddr = info[4]
            if sockaddr and sockaddr[0]:
                try:
                    resolved_ips.append(ipaddress.ip_address(sockaddr[0]))
                except ValueError:
                    continue
    if not resolved_ips:
        raise HTTPException(status_code=422, detail="Не удалось определить IP-адрес узла")
    for ip in resolved_ips:
        if (
            not ip.is_global
            or ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise HTTPException(
                status_code=422,
                detail="Проверка внутренних, локальных и зарезервированных сетевых адресов запрещена политикой безопасности (SSRF guard)",
            )
    return url.strip()


@services_router.post("/{service_id}/probe", response_model=ServiceRead)
def probe_service_health(
    service_id: int,
    access: AccessContext = Depends(require_permission("services:edit")),
    db: Session = Depends(get_db),
):
    service = db.scalar(scope_query(select(Service), Service, access, db).where(Service.id == service_id))
    if service is None or service.is_archived:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    target = (service.health_endpoint or service.url or "").strip()
    if not target:
        raise HTTPException(status_code=422, detail="Для сервиса не задан health_endpoint или URL")
    safe_url = validate_public_probe_url(target)
    try:
        response = httpx.get(
            safe_url,
            timeout=3.0,
            follow_redirects=False,
            headers={"User-Agent": "BOTVEX-Control-Center-Probe/0.1"},
        )
        if 200 <= response.status_code < 400:
            service.status = "healthy"
        elif 400 <= response.status_code < 500:
            service.status = "degraded"
        else:
            service.status = "down"
        summary_detail = f"HTTP {response.status_code}"
    except httpx.HTTPError:
        service.status = "down"
        summary_detail = "ошибка соединения / таймаут"
    service.status_source = "probe"
    service.last_checked_at = utcnow()
    actor = access.user.username if access.user else "owner"
    audit(db, "service", service.id, "probed", f"Проверка узла «{service.name}»: {service.status} ({summary_detail})", actor)
    db.commit()
    db.refresh(service)
    return service
