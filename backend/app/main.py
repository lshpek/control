from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import models
from .auth import AccessContext, require_permission
from .auth_routes import admin_router, router as auth_router
from .config import settings
from .crud import (
    audit, clients_router, deploy_router, log_router, projects_router,
    services_router, suite_router, tasks_router,
)
from .database import get_db
from .errors import install_error_handlers
from .orders import orders_router, portal_router
from .schemas import ActivityRead, SettingRead, SettingsUpdate


import logging

logger = logging.getLogger("botvex.core")


def get_startup_banner() -> str:
    mode = "local_dev" if settings.local_dev_mode else "prod"
    return f"[BOTVEX-CORE] CONTROL CENTER INITIALIZED | MODE={mode} | DB=SQLITE_WAL | RBAC=STRICT_SCOPE | ORIGIN_GUARD=ACTIVE"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    logger.info(get_startup_banner())
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="BOTVEX operations platform with account-based authentication and scoped client access",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data"],
)
install_error_handlers(app)


@app.middleware("http")
async def same_site_mutation_guard(request: Request, call_next):
    """Reject browser mutations from untrusted origins before they reach route handlers."""
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        origin = request.headers.get("origin")
        # In production, every browser-style mutation must carry an allowed Origin.
        # Local development permits origin-less CLI/test requests, but still rejects
        # an explicitly supplied untrusted Origin. CORS alone is not a CSRF defense.
        missing_or_untrusted_origin = origin not in settings.cors_origins
        if (not settings.local_dev_mode and missing_or_untrusted_origin) or (origin is not None and missing_or_untrusted_origin):
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "origin_forbidden", "message": "Источник запроса не разрешён", "details": []}},
            )
    return await call_next(request)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "database": db_status,
        "auth_mode": "account_session" if settings.telegram_bot_token else "account_session_only",
        "startup_banner": get_startup_banner(),
    }


api = APIRouter(prefix="/api/v1")
for router in [clients_router, projects_router, tasks_router, services_router, log_router, suite_router, deploy_router]:
    api.include_router(router)


@api.get("/health")
def api_health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": settings.app_version, "database": "ok", "auth_mode": "account_session" if settings.telegram_bot_token else "account_session_only"}


@api.get("/dashboard")
def dashboard(access: AccessContext = Depends(require_permission("dashboard:view")), db: Session = Depends(get_db)):
    if access.scope != "all" and not access.is_owner:
        raise HTTPException(status_code=403, detail="Панель обзора доступна только с областью доступа ко всему рабочему пространству")
    client_count = db.scalar(select(func.count(models.Client.id)).where(models.Client.is_archived.is_(False))) or 0
    project_count = db.scalar(select(func.count(models.Project.id)).where(models.Project.is_archived.is_(False))) or 0
    open_tasks = db.scalar(select(func.count(models.Task.id)).where(models.Task.is_archived.is_(False), models.Task.status != "done")) or 0
    service_count = db.scalar(select(func.count(models.Service.id)).where(models.Service.is_archived.is_(False))) or 0
    next_tasks = list(db.scalars(
        select(models.Task)
        .where(models.Task.is_archived.is_(False), models.Task.status != "done")
        .order_by(models.Task.due_date.asc().nullslast(), models.Task.created_at.desc(), models.Task.id.desc())
        .limit(6)
    ).all())
    recent = list(db.scalars(select(models.ActivityEvent).order_by(models.ActivityEvent.created_at.desc(), models.ActivityEvent.id.desc()).limit(8)).all())
    service_summary = [{
        "id": s.id, "name": s.name, "status": s.status,
        "status_source": s.status_source, "last_checked_at": s.last_checked_at,
    } for s in db.scalars(
        select(models.Service).where(models.Service.is_archived.is_(False)).order_by(models.Service.updated_at.desc(), models.Service.id.desc()).limit(6)
    ).all()]
    return {
        "metrics": {"clients": client_count, "projects": project_count, "open_tasks": open_tasks, "services": service_count},
        "next_tasks": [{"id": t.id, "title": t.title, "status": t.status, "priority": t.priority, "due_date": t.due_date, "project_id": t.project_id} for t in next_tasks],
        "recent_activity": [{"id": e.id, "actor": e.actor, "entity_type": e.entity_type, "entity_id": e.entity_id, "action": e.action, "summary": e.summary, "created_at": e.created_at} for e in recent],
        "service_summary": service_summary,
    }


@api.get("/activity", response_model=list[ActivityRead])
def activity(
    entity_type: str | None = Query(None, max_length=40),
    limit: int = Query(100, ge=1, le=250),
    offset: int = Query(0, ge=0, le=1000000),
    access: AccessContext = Depends(require_permission("activity:view")),
    db: Session = Depends(get_db),
):
    if access.scope != "all" and not access.is_owner:
        raise HTTPException(status_code=403, detail="Для просмотра общей истории требуется полный scope")
    query = select(models.ActivityEvent)
    if entity_type:
        query = query.where(models.ActivityEvent.entity_type == entity_type)
    return list(db.scalars(query.order_by(models.ActivityEvent.created_at.desc(), models.ActivityEvent.id.desc()).limit(limit).offset(offset)).all())


@api.get("/settings", response_model=list[SettingRead])
def get_settings(_access: AccessContext = Depends(require_permission("settings:view")), db: Session = Depends(get_db)):
    # Defaults are virtual; a GET request never creates persistent settings or commits a transaction.
    defaults = {"display_name": "BOTVEX Control Center", "timezone": "Europe/Moscow"}
    rows = {row.key: row for row in db.scalars(select(models.AppSetting)).all()}
    result = []
    for key, value in defaults.items():
        row = rows.pop(key, None)
        if row is not None:
            result.append({"key": key, "value": row.value, "updated_at": row.updated_at})
        else:
            result.append({"key": key, "value": value, "updated_at": None})
    result.extend({"key": row.key, "value": row.value, "updated_at": row.updated_at} for row in rows.values())
    return sorted(result, key=lambda item: item["key"])


@api.patch("/settings", response_model=list[SettingRead])
def update_settings(payload: SettingsUpdate, _access: AccessContext = Depends(require_permission("settings:edit")), db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is None:
            continue
        if key == "timezone":
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise HTTPException(422, "Неизвестная временная зона") from exc
        row = db.get(models.AppSetting, key)
        if row:
            row.value = value
        else:
            db.add(models.AppSetting(key=key, value=value))
    if data:
        audit(db, "settings", None, "updated", "Обновлены настройки приложения", _access.user.username if _access.user else "owner")
        db.commit()
    rows = db.scalars(select(models.AppSetting).order_by(models.AppSetting.key)).all()
    result_by_key = {row.key: {"key": row.key, "value": row.value, "updated_at": row.updated_at} for row in rows}
    defaults = {"display_name": "BOTVEX Control Center", "timezone": "Europe/Moscow"}
    for key, value in defaults.items():
        result_by_key.setdefault(key, {"key": key, "value": value, "updated_at": None})
    return sorted(result_by_key.values(), key=lambda item: item["key"])


app.include_router(api)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(orders_router)
app.include_router(portal_router)
