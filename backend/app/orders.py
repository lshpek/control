from __future__ import annotations

import secrets
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .access_scopes import ensure_related_scope, scope_query
from .auth import AccessContext, get_current_user, require_client_portal_user, require_permission
from .database import get_db
from .models import ActivityEvent, Client, Order, OrderEvent, OrderMessage, Project, RolePermissionGrant, User, utcnow
from .schemas import (
    ClientOrderMessageCreate, OrderAdminRead, OrderCreate, OrderEventRead, OrderListRead,
    OrderMessageCreate, OrderMessageRead, OrderPortalListRead, OrderPortalRead,
    OrderTransition, OrderUpdate, PortalMessageRead,
)

orders_router = APIRouter(prefix="/api/v1/orders", tags=["orders"])
portal_router = APIRouter(prefix="/api/v1/portal", tags=["client portal"])

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"awaiting_proposal_approval", "cancelled"},
    "awaiting_proposal_approval": {"awaiting_customer_information", "approved", "on_hold", "cancelled"},
    "awaiting_customer_information": {"awaiting_proposal_approval", "approved", "on_hold", "cancelled"},
    "approved": {"in_progress", "on_hold", "cancelled"},
    "in_progress": {"internal_review", "on_hold"},
    "internal_review": {"in_progress", "awaiting_customer_review"},
    "awaiting_customer_review": {"changes_requested", "ready_for_delivery"},
    "changes_requested": {"in_progress", "awaiting_customer_review"},
    "ready_for_delivery": {"delivered", "changes_requested"},
    "delivered": {"completed", "changes_requested"},
    "on_hold": {"approved", "in_progress", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _permission_granted(user: User | None, permission_key: str) -> bool:
    if user is None:
        return False
    if user.is_owner:
        return True
    return any(
        role.is_active and grant.permission.key == permission_key
        for role in user.roles
        for grant in role.grants
    )


def _order_admin(order: Order, include_internal: bool) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "client_id": order.client_id,
        "project_id": order.project_id,
        "client_name": order.client.name if order.client else "—",
        "title": order.title,
        "scope": order.scope,
        "status": order.status,
        "client_visible_summary": order.client_visible_summary,
        "internal_notes": order.internal_notes if include_internal else None,
        "amount": format(order.amount, "f") if order.amount is not None else None,
        "amount_type": order.amount_type,
        "currency": order.currency,
        "target_delivery_date": order.target_delivery_date,
        "is_archived": order.is_archived,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _order_portal(order: Order) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "title": order.title,
        "status": order.status,
        "client_visible_summary": order.client_visible_summary,
        "amount": format(order.amount, "f") if order.amount is not None else None,
        "amount_type": order.amount_type,
        "currency": order.currency,
        "target_delivery_date": order.target_delivery_date,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _order_query_for_access(access: AccessContext, db: Session):
    return scope_query(select(Order).options(selectinload(Order.client)), Order, access, db)


def _visible_order(order_id: int, access: AccessContext, db: Session) -> Order:
    order = db.scalar(_order_query_for_access(access, db).where(Order.id == order_id))
    if order is None or order.is_archived:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order


def _portal_order(order_id: int, user: User, db: Session) -> Order:
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.client))
        .where(
            Order.id == order_id,
            Order.client_id == user.customer_id,
            Order.is_archived.is_(False),
            Order.status != "draft",
        )
    )
    if order is None:
        # The same response is used for missing and other-customer identifiers to prevent IDOR probing.
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order


def _message_read(message: OrderMessage) -> dict:
    return {
        "id": message.id,
        "author_username": message.author.username if message.author else None,
        "body": message.body,
        "is_internal": message.is_internal,
        "created_at": message.created_at,
    }


def _portal_message_read(message: OrderMessage) -> dict:
    return {
        "id": message.id,
        "author_username": message.author.username if message.author else None,
        "body": message.body,
        "created_at": message.created_at,
    }


def _actor(access: AccessContext) -> tuple[int | None, str]:
    return (access.user.id, access.user.username) if access.user else (None, "owner")


@orders_router.get("", response_model=OrderListRead)
def list_orders(
    q: str | None = Query(None, max_length=100),
    status: str | None = Query(None, max_length=40),
    include_archived: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    access: AccessContext = Depends(require_permission("orders:view")),
    db: Session = Depends(get_db),
):
    query = _order_query_for_access(access, db)
    if not include_archived:
        query = query.where(Order.is_archived.is_(False))
    if status:
        query = query.where(Order.status == status)
    if q and q.strip():
        term = f"%{q.strip()[:100]}%"
        query = query.where(Order.title.ilike(term) | Order.order_number.ilike(term))
    count = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.scalars(query.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit).offset(offset)).all())
    include_internal = _permission_granted(access.user, "orders:view_internal")
    return {"items": [_order_admin(row, include_internal) for row in rows], "total": count, "limit": limit, "offset": offset}


@orders_router.post("", response_model=OrderAdminRead, status_code=201)
def create_order(payload: OrderCreate, access: AccessContext = Depends(require_permission("orders:create")), db: Session = Depends(get_db)):
    client = db.get(Client, payload.client_id)
    if client is None or client.is_archived:
        raise HTTPException(status_code=422, detail="Клиент не найден или находится в архиве")
    if payload.project_id is not None:
        project = db.get(Project, payload.project_id)
        if project is None or project.is_archived or project.client_id not in (None, client.id):
            raise HTTPException(status_code=422, detail="Проект должен существовать и относиться к этому клиенту")
    if payload.amount_type == "fixed" and payload.amount is None:
        raise HTTPException(status_code=422, detail="Для фиксированной цены нужно указать сумму")
    data = payload.model_dump()
    ensure_related_scope(Order, data, access, db)
    now = utcnow()
    order = Order(
        **data,
        order_number=f"BVX-{now:%Y%m%d}-{secrets.token_hex(3).upper()}",
        status="draft",
        is_archived=False,
        created_by_user_id=access.user.id if access.user else None,
    )
    db.add(order)
    db.flush()
    actor_id, actor_name = _actor(access)
    db.add(OrderEvent(order_id=order.id, actor_user_id=actor_id, event_type="created", to_status="draft", message="Заказ создан", client_visible=False))
    db.add(ActivityEvent(actor=actor_name, entity_type="order", entity_id=order.id, action="created", summary=f"Создан заказ {order.order_number}"))
    db.commit()
    order = db.scalar(select(Order).options(selectinload(Order.client)).where(Order.id == order.id))
    return _order_admin(order, _permission_granted(access.user, "orders:view_internal"))


@orders_router.get("/{order_id}", response_model=OrderAdminRead)
def get_order(order_id: int, access: AccessContext = Depends(require_permission("orders:view")), db: Session = Depends(get_db)):
    order = _visible_order(order_id, access, db)
    return _order_admin(order, _permission_granted(access.user, "orders:view_internal"))


@orders_router.patch("/{order_id}", response_model=OrderAdminRead)
def update_order(order_id: int, payload: OrderUpdate, access: AccessContext = Depends(require_permission("orders:edit")), db: Session = Depends(get_db)):
    order = _visible_order(order_id, access, db)
    changes = payload.model_dump(exclude_unset=True)
    agreed_fields = {"scope", "amount", "amount_type", "currency", "target_delivery_date"}
    if order.status not in {"draft", "awaiting_proposal_approval"} and agreed_fields.intersection(changes):
        raise HTTPException(status_code=409, detail="Согласованный объём, цена и срок нельзя менять напрямую. Для этого нужен отдельный запрос на изменение.")
    scope_data = {**changes, "client_id": order.client_id, "project_id": order.project_id}
    ensure_related_scope(Order, scope_data, access, db)
    if "project_id" in changes and changes["project_id"] is not None:
        project = db.get(Project, changes["project_id"])
        if project is None or project.client_id not in (None, order.client_id):
            raise HTTPException(status_code=422, detail="Проект должен относиться к этому клиенту")
    amount_type = changes.get("amount_type", order.amount_type)
    amount = changes.get("amount", order.amount)
    if amount_type == "fixed" and amount is None:
        raise HTTPException(status_code=422, detail="Для фиксированной цены нужно указать сумму")
    for key, value in changes.items():
        setattr(order, key, value)
    order.updated_at = utcnow()
    actor_id, actor_name = _actor(access)
    db.add(OrderEvent(order_id=order.id, actor_user_id=actor_id, event_type="updated", message="Данные заказа изменены", client_visible=False))
    db.add(ActivityEvent(actor=actor_name, entity_type="order", entity_id=order.id, action="updated", summary=f"Изменён заказ {order.order_number}"))
    db.commit()
    order = db.scalar(select(Order).options(selectinload(Order.client)).where(Order.id == order.id))
    return _order_admin(order, _permission_granted(access.user, "orders:view_internal"))


@orders_router.post("/{order_id}/archive", response_model=OrderAdminRead)
def archive_order(order_id: int, access: AccessContext = Depends(require_permission("orders:archive")), db: Session = Depends(get_db)):
    order = _visible_order(order_id, access, db)
    order.is_archived = True
    order.updated_at = utcnow()
    actor_id, actor_name = _actor(access)
    db.add(OrderEvent(order_id=order.id, actor_user_id=actor_id, event_type="archived", message="Заказ помещён в архив", client_visible=False))
    db.add(ActivityEvent(actor=actor_name, entity_type="order", entity_id=order.id, action="archived", summary=f"Заархивирован заказ {order.order_number}"))
    db.commit()
    order = db.scalar(select(Order).options(selectinload(Order.client)).where(Order.id == order.id))
    return _order_admin(order, _permission_granted(access.user, "orders:view_internal"))


@orders_router.post("/{order_id}/restore", response_model=OrderAdminRead)
def restore_order(order_id: int, access: AccessContext = Depends(require_permission("orders:restore")), db: Session = Depends(get_db)):
    query = _order_query_for_access(access, db).where(Order.id == order_id, Order.is_archived.is_(True))
    order = db.scalar(query)
    if order is None:
        raise HTTPException(status_code=404, detail="Архивный заказ не найден")
    order.is_archived = False
    order.updated_at = utcnow()
    actor_id, actor_name = _actor(access)
    db.add(OrderEvent(order_id=order.id, actor_user_id=actor_id, event_type="restored", message="Заказ восстановлен из архива", client_visible=False))
    db.add(ActivityEvent(actor=actor_name, entity_type="order", entity_id=order.id, action="restored", summary=f"Восстановлен заказ {order.order_number}"))
    db.commit()
    order = db.scalar(select(Order).options(selectinload(Order.client)).where(Order.id == order.id))
    return _order_admin(order, _permission_granted(access.user, "orders:view_internal"))


@orders_router.post("/{order_id}/transition", response_model=OrderAdminRead)
def transition_order(order_id: int, payload: OrderTransition, access: AccessContext = Depends(require_permission("orders:transition")), db: Session = Depends(get_db)):
    order = _visible_order(order_id, access, db)
    if payload.status not in ALLOWED_TRANSITIONS.get(order.status, set()):
        raise HTTPException(status_code=409, detail=f"Недопустимый переход заказа: {order.status} → {payload.status}")
    previous = order.status
    order.status = payload.status
    order.updated_at = utcnow()
    actor_id, actor_name = _actor(access)
    db.add(OrderEvent(
        order_id=order.id,
        actor_user_id=actor_id,
        event_type="status_changed",
        from_status=previous,
        to_status=payload.status,
        message=payload.message,
        client_visible=payload.client_visible,
    ))
    db.add(ActivityEvent(actor=actor_name, entity_type="order", entity_id=order.id, action="status_changed", summary=f"Заказ {order.order_number}: {previous} → {payload.status}"))
    db.commit()
    order = db.scalar(select(Order).options(selectinload(Order.client)).where(Order.id == order.id))
    return _order_admin(order, _permission_granted(access.user, "orders:view_internal"))


@orders_router.get("/{order_id}/events", response_model=list[OrderEventRead])
def list_order_events(order_id: int, access: AccessContext = Depends(require_permission("orders:view")), db: Session = Depends(get_db)):
    order = _visible_order(order_id, access, db)
    query = select(OrderEvent).where(OrderEvent.order_id == order.id)
    if not _permission_granted(access.user, "orders:view_internal"):
        query = query.where(OrderEvent.client_visible.is_(True))
    rows = db.scalars(query.order_by(OrderEvent.created_at, OrderEvent.id)).all()
    return [{"id": row.id, "event_type": row.event_type, "from_status": row.from_status, "to_status": row.to_status, "message": row.message, "created_at": row.created_at} for row in rows]


@orders_router.get("/{order_id}/messages", response_model=list[OrderMessageRead])
def list_order_messages(order_id: int, access: AccessContext = Depends(require_permission("orders:messages:view")), db: Session = Depends(get_db)):
    order = _visible_order(order_id, access, db)
    query = select(OrderMessage).options(selectinload(OrderMessage.author)).where(OrderMessage.order_id == order.id)
    if not _permission_granted(access.user, "orders:messages:internal"):
        query = query.where(OrderMessage.is_internal.is_(False))
    messages = db.scalars(query.order_by(OrderMessage.created_at, OrderMessage.id)).all()
    return [_message_read(message) for message in messages]


@orders_router.post("/{order_id}/messages", response_model=OrderMessageRead, status_code=201)
def create_order_message(order_id: int, payload: OrderMessageCreate, access: AccessContext = Depends(require_permission("orders:messages:create")), db: Session = Depends(get_db)):
    order = _visible_order(order_id, access, db)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Сообщение не может быть пустым")
    if payload.is_internal and not _permission_granted(access.user, "orders:messages:internal"):
        raise HTTPException(status_code=403, detail="Недостаточно прав для внутреннего сообщения")
    message = OrderMessage(order_id=order.id, author_user_id=access.user.id if access.user else None, body=body, is_internal=payload.is_internal)
    db.add(message)
    db.flush()
    actor_id, actor_name = _actor(access)
    db.add(ActivityEvent(actor=actor_name, entity_type="order_message", entity_id=message.id, action="created", summary=f"Добавлено {'внутреннее ' if message.is_internal else ''}сообщение к заказу {order.order_number}"))
    db.commit()
    message = db.scalar(select(OrderMessage).options(selectinload(OrderMessage.author)).where(OrderMessage.id == message.id))
    return _message_read(message)


@portal_router.get("/me")
def portal_me(user: User = Depends(require_client_portal_user), db: Session = Depends(get_db)):
    client = db.get(Client, user.customer_id)
    if client is None or client.is_archived:
        raise HTTPException(status_code=403, detail="Клиентский профиль отключён")
    return {"id": user.id, "username": user.username, "customer_id": client.id, "customer_name": client.name}


@portal_router.get("/orders", response_model=OrderPortalListRead)
def portal_orders(
    limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=1000000),
    access: AccessContext = Depends(require_permission("portal:orders:view")),
    user: User = Depends(require_client_portal_user), db: Session = Depends(get_db),
):
    base = select(Order).where(Order.client_id == user.customer_id, Order.is_archived.is_(False), Order.status != "draft")
    count = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Order.updated_at.desc(), Order.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [_order_portal(row) for row in rows], "total": count, "limit": limit, "offset": offset}


@portal_router.get("/orders/{order_id}", response_model=OrderPortalRead)
def portal_order(order_id: int, _access: AccessContext = Depends(require_permission("portal:orders:view")), user: User = Depends(require_client_portal_user), db: Session = Depends(get_db)):
    order = _portal_order(order_id, user, db)
    return _order_portal(order)


@portal_router.get("/orders/{order_id}/events", response_model=list[OrderEventRead])
def portal_order_events(order_id: int, _access: AccessContext = Depends(require_permission("portal:orders:view")), user: User = Depends(require_client_portal_user), db: Session = Depends(get_db)):
    order = _portal_order(order_id, user, db)
    events = db.scalars(select(OrderEvent).where(OrderEvent.order_id == order.id, OrderEvent.client_visible.is_(True)).order_by(OrderEvent.created_at, OrderEvent.id)).all()
    return [{"id": row.id, "event_type": row.event_type, "from_status": row.from_status, "to_status": row.to_status, "message": row.message, "created_at": row.created_at} for row in events]


@portal_router.get("/orders/{order_id}/messages", response_model=list[PortalMessageRead])
def portal_order_messages(order_id: int, _access: AccessContext = Depends(require_permission("portal:messages:view")), user: User = Depends(require_client_portal_user), db: Session = Depends(get_db)):
    order = _portal_order(order_id, user, db)
    messages = db.scalars(select(OrderMessage).options(selectinload(OrderMessage.author)).where(OrderMessage.order_id == order.id, OrderMessage.is_internal.is_(False)).order_by(OrderMessage.created_at, OrderMessage.id)).all()
    return [_portal_message_read(message) for message in messages]


@portal_router.post("/orders/{order_id}/messages", response_model=PortalMessageRead, status_code=201)
def portal_send_message(order_id: int, payload: ClientOrderMessageCreate, _access: AccessContext = Depends(require_permission("portal:messages:create")), user: User = Depends(require_client_portal_user), db: Session = Depends(get_db)):
    order = _portal_order(order_id, user, db)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Сообщение не может быть пустым")
    message = OrderMessage(order_id=order.id, author_user_id=user.id, body=body, is_internal=False)
    db.add(message)
    db.flush()
    db.add(ActivityEvent(actor=user.username, entity_type="order_message", entity_id=message.id, action="created", summary=f"Получено сообщение клиента по заказу {order.order_number}"))
    db.commit()
    message = db.scalar(select(OrderMessage).options(selectinload(OrderMessage.author)).where(OrderMessage.id == message.id))
    return _portal_message_read(message)
