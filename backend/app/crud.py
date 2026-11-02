from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .access_scopes import ensure_related_scope, scope_query
from .auth import AccessContext, require_permission
from .database import get_db
from .models import ActivityEvent, Client, DeploymentRecord, LogEntry, Project, ProjectAssignment, Service, Task, TestRun, TestSuite
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
            obj.completed_at = datetime.utcnow()
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
            obj.completed_at = datetime.utcnow()
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
