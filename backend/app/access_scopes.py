"""SQL-level record scoping for role permissions."""
from sqlalchemy import false, select

from .models import (
    Client, DeploymentRecord, LogEntry, Order, Project, ProjectAssignment,
    Service, Task, TestSuite,
)
from .auth import AccessContext


def scope_query(query, model, access: AccessContext, db):
    if access.scope == "all" or access.is_owner:
        return query
    user = access.user
    if user is None:
        return query.where(false())
    assigned_project_ids = select(ProjectAssignment.project_id).where(ProjectAssignment.user_id == user.id)
    customer_project_ids = select(Project.id).where(Project.client_id == user.customer_id) if user.customer_id is not None else None

    if access.scope == "assigned":
        if model is Project:
            return query.where(Project.id.in_(assigned_project_ids))
        if model is Client:
            return query.where(Client.id.in_(select(Project.client_id).where(Project.id.in_(assigned_project_ids), Project.client_id.is_not(None))))
        if model is Task:
            return query.where(Task.project_id.in_(assigned_project_ids))
        if model is Service:
            return query.where(Service.project_id.in_(assigned_project_ids))
        if model is LogEntry:
            assigned_service_ids = select(Service.id).where(Service.project_id.in_(assigned_project_ids))
            return query.where(LogEntry.service_id.in_(assigned_service_ids))
        if model is TestSuite:
            return query.where(TestSuite.project_id.in_(assigned_project_ids))
        if model is DeploymentRecord:
            return query.where(DeploymentRecord.project_id.in_(assigned_project_ids))
        if model is Order:
            return query.where(Order.project_id.in_(assigned_project_ids))
        return query.where(false())

    if access.scope == "own_customer":
        if user.customer_id is None:
            return query.where(false())
        if model is Client:
            return query.where(Client.id == user.customer_id)
        if model is Project:
            return query.where(Project.client_id == user.customer_id)
        if model is Task:
            return query.where(Task.project_id.in_(customer_project_ids))
        if model is Service:
            return query.where(Service.project_id.in_(customer_project_ids))
        if model is LogEntry:
            customer_service_ids = select(Service.id).where(Service.project_id.in_(customer_project_ids))
            return query.where(LogEntry.service_id.in_(customer_service_ids))
        if model is TestSuite:
            return query.where(TestSuite.project_id.in_(customer_project_ids))
        if model is DeploymentRecord:
            return query.where(DeploymentRecord.project_id.in_(customer_project_ids))
        if model is Order:
            return query.where(Order.client_id == user.customer_id)
        return query.where(false())

    return query.where(false())


def ensure_related_scope(model, data: dict, access: AccessContext, db) -> None:
    """Reject writes that link records outside the caller's effective scope."""
    if access.scope == "all" or access.is_owner:
        return
    user = access.user
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Недостаточно прав для этой записи")
    from fastapi import HTTPException
    if model is Project:
        if access.scope == "own_customer" and data.get("client_id") not in (None, user.customer_id):
            raise HTTPException(status_code=404, detail="Связанная запись не найдена")
        # Assigned-scope users may edit their assigned projects but may not create new ones.
        if not data.get("id"):
            raise HTTPException(status_code=403, detail="Нельзя создавать проекты за пределами назначенного доступа")
    related_project_id = data.get("project_id")
    if model in (Task, Service, TestSuite, DeploymentRecord, Order) and related_project_id is not None:
        project_query = scope_query(select(Project), Project, access, db).where(Project.id == related_project_id)
        if db.scalar(project_query) is None:
            raise HTTPException(status_code=404, detail="Связанный проект не найден")
    if model in (Task, Service, TestSuite, DeploymentRecord) and related_project_id is None:
        raise HTTPException(status_code=403, detail="В этой роли запись должна быть связана с доступным проектом")
    if model is LogEntry and data.get("service_id") is not None:
        service_query = scope_query(select(Service), Service, access, db).where(Service.id == data["service_id"])
        if db.scalar(service_query) is None:
            raise HTTPException(status_code=404, detail="Связанный сервис не найден")
    if model is Order:
        client_id = data.get("client_id")
        if access.scope == "own_customer" and client_id != user.customer_id:
            raise HTTPException(status_code=404, detail="Связанный клиент не найден")
        if access.scope == "assigned" and related_project_id is None:
            raise HTTPException(status_code=403, detail="Заказ должен быть связан с назначенным проектом")
