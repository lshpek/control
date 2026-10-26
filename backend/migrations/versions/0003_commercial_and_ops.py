"""Commercial change requests and financial payment ledger."""
from alembic import op
import sqlalchemy as sa

revision = "0003_commercial_and_ops"
down_revision = "0002_accounts_rbac_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_change_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("scope_delta", sa.Text(), nullable=False),
        sa.Column("amount_delta", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("new_delivery_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("decision_note", sa.String(length=2000), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_change_requests_order_id", "order_change_requests", ["order_id"])
    op.create_index("ix_order_change_requests_status", "order_change_requests", ["status"])
    op.create_index("ix_order_change_requests_created_at", "order_change_requests", ["created_at"])

    op.create_table(
        "order_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_payments_order_id", "order_payments", ["order_id"])
    op.create_index("ix_order_payments_kind", "order_payments", ["kind"])
    op.create_index("ix_order_payments_status", "order_payments", ["status"])
    op.create_index("ix_order_payments_created_at", "order_payments", ["created_at"])


def downgrade() -> None:
    for name in [
        "ix_order_payments_created_at",
        "ix_order_payments_status",
        "ix_order_payments_kind",
        "ix_order_payments_order_id",
    ]:
        op.drop_index(name, table_name="order_payments")
    op.drop_table("order_payments")

    for name in [
        "ix_order_change_requests_created_at",
        "ix_order_change_requests_status",
        "ix_order_change_requests_order_id",
    ]:
        op.drop_index(name, table_name="order_change_requests")
    op.drop_table("order_change_requests")
