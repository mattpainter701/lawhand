"""Add request-level idempotency to Research MCP usage events.

A client retry that reuses one idempotency key must not create a second
billable event (and therefore a second Stripe meter unit). The columns are
nullable and the unique index is partial, so existing keyless events and the
internal chat path are unaffected.

Revision ID: 196_mcp_usage_idempotency
Revises: 195_probate_track
"""

from alembic import op
import sqlalchemy as sa


revision = "196_mcp_usage_idempotency"
down_revision = "195_probate_track"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_usage_events",
        sa.Column("request_idempotency_key", sa.String(200), nullable=True),
    )
    op.add_column(
        "mcp_usage_events",
        sa.Column("credential_scope", sa.String(80), nullable=True),
    )
    op.add_column(
        "mcp_usage_events",
        sa.Column("request_sha256", sa.String(64), nullable=True),
    )
    op.create_index(
        "uq_mcp_usage_request_idempotency",
        "mcp_usage_events",
        ["tenant_id", "credential_scope", "request_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("request_idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_mcp_usage_request_idempotency",
        table_name="mcp_usage_events",
    )
    op.drop_column("mcp_usage_events", "request_sha256")
    op.drop_column("mcp_usage_events", "credential_scope")
    op.drop_column("mcp_usage_events", "request_idempotency_key")
