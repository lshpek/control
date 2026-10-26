from datetime import datetime, date
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

class ClientCreate(Schema):
    name: str = Field(min_length=1, max_length=160)
    contact_person: str | None = Field(None, max_length=160)
    contacts: str | None = Field(None, max_length=500)
    notes: str | None = Field(None, max_length=10000)
    status: Literal["lead", "active", "paused", "archived"] = "lead"
class ClientUpdate(Schema):
    name: str | None = Field(None, min_length=1, max_length=160)
    contact_person: str | None = Field(None, max_length=160)
    contacts: str | None = Field(None, max_length=500)
    notes: str | None = Field(None, max_length=10000)
    status: Literal["lead", "active", "paused", "archived"] | None = None
class ClientRead(ClientCreate):
    id: int; is_archived: bool; created_at: datetime; updated_at: datetime

class ProjectCreate(Schema):
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(None, max_length=10000)
    client_id: int | None = None
    status: Literal["planning", "active", "on_hold", "completed", "archived"] = "planning"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    due_date: date | None = None
    repository_url: str | None = Field(None, max_length=500)
    environment: str | None = Field(None, max_length=80)
    notes: str | None = Field(None, max_length=10000)
    requirements: list[str] = Field(default_factory=list, max_length=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)
class ProjectUpdate(Schema):
    name: str | None = Field(None, min_length=1, max_length=180)
    description: str | None = Field(None, max_length=10000)
    client_id: int | None = None
    status: Literal["planning", "active", "on_hold", "completed", "archived"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    due_date: date | None = None
    repository_url: str | None = Field(None, max_length=500)
    environment: str | None = Field(None, max_length=80)
    notes: str | None = Field(None, max_length=10000)
    requirements: list[str] | None = Field(None, max_length=100)
    acceptance_criteria: list[str] | None = Field(None, max_length=100)
class ProjectRead(ProjectCreate):
    id: int; is_archived: bool; created_at: datetime; updated_at: datetime

class TaskCreate(Schema):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=10000)
    status: Literal["backlog", "in_progress", "blocked", "review", "done"] = "backlog"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    project_id: int | None = None
    due_date: date | None = None
    notes: str | None = Field(None, max_length=10000)
class TaskUpdate(Schema):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=10000)
    status: Literal["backlog", "in_progress", "blocked", "review", "done"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    project_id: int | None = None
    due_date: date | None = None
    notes: str | None = Field(None, max_length=10000)
class TaskRead(TaskCreate):
    id: int; completed_at: datetime | None; is_archived: bool; created_at: datetime; updated_at: datetime

class ServiceFields(Schema):
    name: str = Field(min_length=1, max_length=180)
    type: Literal["bot", "api", "external"] = "bot"
    url: str | None = Field(None, max_length=500)
    health_endpoint: str | None = Field(None, max_length=500)
    environment: str | None = Field(None, max_length=80)
    version: str | None = Field(None, max_length=80)
    hosting: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=10000)
    desired_check_interval_seconds: int = Field(300, ge=60, le=86400)
    status: Literal["manual", "unknown", "healthy", "degraded", "down"] = "unknown"
    status_source: Literal["manual", "unknown", "probe"] = "manual"
    project_id: int | None = None
    @field_validator("url", "health_endpoint")
    @classmethod
    def safe_http_url(cls, value):
        if value:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Разрешены только абсолютные URL http/https без логина и пароля")
        return value
class ServiceCreate(ServiceFields): pass
class ServiceUpdate(Schema):
    name: str | None = Field(None, min_length=1, max_length=180)
    type: Literal["bot", "api", "external"] | None = None
    url: str | None = Field(None, max_length=500)
    health_endpoint: str | None = Field(None, max_length=500)
    environment: str | None = Field(None, max_length=80)
    version: str | None = Field(None, max_length=80)
    hosting: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=10000)
    desired_check_interval_seconds: int | None = Field(None, ge=60, le=86400)
    status: Literal["manual", "unknown", "healthy", "degraded", "down"] | None = None
    status_source: Literal["manual", "unknown", "probe"] | None = None
    project_id: int | None = None
    @field_validator("url", "health_endpoint")
    @classmethod
    def safe_http_url(cls, value):
        if value:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Разрешены только абсолютные URL http/https без логина и пароля")
        return value
class ServiceRead(ServiceCreate):
    id: int; is_archived: bool; last_checked_at: datetime | None; created_at: datetime; updated_at: datetime

class LogEntryCreate(Schema):
    service_id: int | None = None
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str = Field(min_length=1, max_length=10000)
    source: Literal["manual"] = "manual"
class LogEntryUpdate(Schema):
    service_id: int | None = None
    level: Literal["debug", "info", "warning", "error"] | None = None
    message: str | None = Field(None, min_length=1, max_length=10000)
class LogEntryRead(LogEntryCreate): id: int; created_at: datetime

class TestSuiteCreate(Schema):
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(None, max_length=10000)
    project_id: int | None = None
class TestSuiteUpdate(Schema):
    name: str | None = Field(None, min_length=1, max_length=180)
    description: str | None = Field(None, max_length=10000)
    project_id: int | None = None
class TestSuiteRead(TestSuiteCreate):
    id: int; last_status: str; created_at: datetime; updated_at: datetime
class TestRunCreate(Schema):
    status: Literal["passed", "failed", "skipped", "manual"]
    duration_ms: int | None = Field(None, ge=0, le=86400000)
    note: str | None = Field(None, max_length=10000)
    source: Literal["manual"] = "manual"
class TestRunRead(TestRunCreate): id: int; suite_id: int; created_at: datetime

class DeploymentCreate(Schema):
    project_id: int | None = None
    version: str = Field(min_length=1, max_length=80)
    environment: str = Field("local", min_length=1, max_length=80)
    status: Literal["recorded", "success", "failed", "rolled_back"] = "recorded"
    url: str | None = Field(None, max_length=500)
    note: str | None = Field(None, max_length=10000)
    source: Literal["manual"] = "manual"
    deployed_at: datetime | None = None
class DeploymentUpdate(Schema):
    project_id: int | None = None
    version: str | None = Field(None, min_length=1, max_length=80)
    environment: str | None = Field(None, min_length=1, max_length=80)
    status: Literal["recorded", "success", "failed", "rolled_back"] | None = None
    url: str | None = Field(None, max_length=500)
    note: str | None = Field(None, max_length=10000)
    deployed_at: datetime | None = None
class DeploymentRead(DeploymentCreate): id: int; created_at: datetime

class ActivityRead(Schema):
    id: int; actor: str; entity_type: str; entity_id: int | None; action: str; summary: str; created_at: datetime
class SettingRead(Schema): key: str; value: str; updated_at: datetime | None
class SettingsUpdate(Schema):
    display_name: str | None = Field(None, max_length=100)
    timezone: str | None = Field(None, max_length=80)

# Account authentication and authorization
class LoginRequest(Schema):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)

class ChangePasswordRequest(Schema):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=128)

class UserProfileRead(Schema):
    id: int
    username: str
    roles: list[str]
    permissions: dict[str, str]
    customer_id: int | None
    telegram_user_id: str | None = None
    is_owner: bool
    must_change_password: bool
    last_login_at: datetime | None

class AdminUserRead(Schema):
    id: int
    username: str
    roles: list[str]
    permissions: dict[str, str]
    customer_id: int | None
    telegram_user_id: str | None = None
    is_active: bool
    is_owner: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime

class AdminUserListRead(Schema):
    items: list[AdminUserRead]
    total: int
    limit: int
    offset: int

class AdminSessionRead(Schema):
    id: int
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    user_agent: str | None
    is_active: bool
    is_current: bool

class AdminSessionListRead(Schema):
    items: list[AdminSessionRead]
    total: int
    limit: int
    offset: int

class AdminUserCreate(Schema):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    role_slugs: list[str] = Field(min_length=1, max_length=10)
    customer_id: int | None = Field(None, gt=0)
    telegram_user_id: str | None = Field(None, min_length=1, max_length=64, pattern=r"^[0-9]+$")

class AdminUserCreateResult(Schema):
    user: AdminUserRead
    temporary_password: str
    message: str

class AdminUserUpdate(Schema):
    is_active: bool | None = None
    role_slugs: list[str] | None = Field(None, min_length=1, max_length=10)
    customer_id: int | None = Field(None, gt=0)
    telegram_user_id: str | None = Field(None, min_length=1, max_length=64, pattern=r"^[0-9]+$")

class RolePermissionInput(Schema):
    scope: Literal["all", "assigned", "own_customer"]

class RoleCreate(Schema):
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    permissions: dict[str, Literal["all", "assigned", "own_customer"]] = Field(default_factory=dict, max_length=100)

class RoleUpdate(Schema):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    is_active: bool | None = None
    permissions: dict[str, Literal["all", "assigned", "own_customer"]] | None = Field(None, max_length=100)

class RoleRead(Schema):
    id: int
    slug: str
    name: str
    description: str | None
    is_system: bool
    is_active: bool
    users_count: int
    permissions: dict[str, str]

class ProjectAssignmentCreate(Schema):
    user_id: int = Field(gt=0)

class ProjectAssignmentRead(Schema):
    id: int
    project_id: int
    user_id: int
    username: str
    created_at: datetime

# Customer-facing order lifecycle. Internal notes are deliberately absent from
# every client portal response schema.
ORDER_STATUSES = (
    "draft", "awaiting_proposal_approval", "awaiting_customer_information",
    "approved", "in_progress", "internal_review", "awaiting_customer_review",
    "changes_requested", "ready_for_delivery", "delivered", "completed",
    "on_hold", "cancelled",
)

class OrderCreate(Schema):
    client_id: int = Field(gt=0)
    project_id: int | None = Field(None, gt=0)
    title: str = Field(min_length=2, max_length=180)
    scope: str = Field(min_length=1, max_length=20000)
    client_visible_summary: str | None = Field(None, max_length=10000)
    internal_notes: str | None = Field(None, max_length=20000)
    amount: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    amount_type: Literal["estimate", "fixed"] = "estimate"
    currency: str = Field("RUB", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    target_delivery_date: date | None = None

class OrderUpdate(Schema):
    project_id: int | None = Field(None, gt=0)
    title: str | None = Field(None, min_length=2, max_length=180)
    scope: str | None = Field(None, min_length=1, max_length=20000)
    client_visible_summary: str | None = Field(None, max_length=10000)
    internal_notes: str | None = Field(None, max_length=20000)
    amount: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    amount_type: Literal["estimate", "fixed"] | None = None
    currency: str | None = Field(None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    target_delivery_date: date | None = None

class OrderTransition(Schema):
    status: Literal[
        "awaiting_proposal_approval", "awaiting_customer_information", "approved",
        "in_progress", "internal_review", "awaiting_customer_review", "changes_requested",
        "ready_for_delivery", "delivered", "completed", "on_hold", "cancelled",
    ]
    message: str | None = Field(None, max_length=2000)
    client_visible: bool = False

class OrderAdminRead(Schema):
    id: int
    order_number: str
    client_id: int
    project_id: int | None
    client_name: str
    title: str
    scope: str
    status: str
    client_visible_summary: str | None
    internal_notes: str | None
    amount: str | None
    amount_type: str
    currency: str
    target_delivery_date: date | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

class OrderPortalRead(Schema):
    id: int
    order_number: str
    title: str
    status: str
    client_visible_summary: str | None
    amount: str | None
    amount_type: str
    currency: str
    target_delivery_date: date | None
    created_at: datetime
    updated_at: datetime

class OrderListRead(Schema):
    items: list[OrderAdminRead]
    total: int
    limit: int
    offset: int

class OrderPortalListRead(Schema):
    items: list[OrderPortalRead]
    total: int
    limit: int
    offset: int

class OrderEventRead(Schema):
    id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    message: str | None
    created_at: datetime

class OrderMessageCreate(Schema):
    body: str = Field(min_length=1, max_length=10000)
    is_internal: bool = False

class ClientOrderMessageCreate(Schema):
    body: str = Field(min_length=1, max_length=10000)

class OrderMessageRead(Schema):
    id: int
    author_username: str | None
    body: str
    is_internal: bool
    created_at: datetime

class PortalMessageRead(Schema):
    id: int
    author_username: str | None
    body: str
    created_at: datetime


class PortalOrderDecision(Schema):
    action: Literal["approve_proposal", "request_info", "accept_delivery", "request_changes"]
    comment: str | None = Field(None, max_length=2000)

class OrderChangeRequestCreate(Schema):
    title: str = Field(min_length=2, max_length=180)
    scope_delta: str = Field(min_length=1, max_length=10000)
    amount_delta: Decimal | None = Field(None, max_digits=12, decimal_places=2)
    new_delivery_date: date | None = None

class OrderChangeRequestDecision(Schema):
    status: Literal["approved", "rejected"]
    decision_note: str | None = Field(None, max_length=2000)

class OrderChangeRequestRead(Schema):
    id: int
    order_id: int
    title: str
    scope_delta: str
    amount_delta: str | None
    new_delivery_date: date | None
    status: str
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None

class OrderPaymentCreate(Schema):
    kind: Literal["payment", "expense"] = "payment"
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field("RUB", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    status: Literal["planned", "paid", "cancelled"] = "planned"
    note: str | None = Field(None, max_length=1000)

class OrderPaymentUpdate(Schema):
    status: Literal["planned", "paid", "cancelled"]
    note: str | None = Field(None, max_length=1000)

class OrderPaymentRead(Schema):
    id: int
    order_id: int
    kind: str
    amount: str
    currency: str
    status: str
    paid_at: datetime | None
    note: str | None
    created_at: datetime

class OrderPaymentSummaryRead(Schema):
    items: list[OrderPaymentRead]
    paid_amount: str
    planned_amount: str
    expenses_amount: str
    balance_due: str
    currency: str

class PortalPaymentSummaryRead(Schema):
    items: list[OrderPaymentRead]
    paid_amount: str
    planned_amount: str
    balance_due: str
    currency: str
