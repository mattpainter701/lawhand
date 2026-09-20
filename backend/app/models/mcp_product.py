import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MCPProductKey(Base):
    __tablename__ = "mcp_product_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    allowed_tools: Mapped[list | None] = mapped_column(JSON, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    monthly_call_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1000, server_default="1000"
    )
    monthly_budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_price_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=45, server_default="45"
    )
    burst_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )


class MCPUsageEvent(Base):
    __tablename__ = "mcp_usage_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mcp_product_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    oauth_grant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_mcp_grants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    auth_type: Mapped[str] = mapped_column(String(40), nullable=False)
    transport: Mapped[str] = mapped_column(String(40), nullable=False, default="rest")
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Request-level idempotency for billable calls. A client retry that reuses
    # the same key must not create a second billable event; credential_scope
    # keeps two different keys or grants from colliding on a shared key value.
    request_idempotency_key: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    credential_scope: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
        index=True,
    )


Index(
    "ix_mcp_usage_events_tenant_created",
    MCPUsageEvent.tenant_id,
    MCPUsageEvent.created_at,
)
Index(
    "ix_mcp_usage_events_oauth_grant_created",
    MCPUsageEvent.oauth_grant_id,
    MCPUsageEvent.created_at,
)
Index(
    "ix_mcp_usage_events_key_created",
    MCPUsageEvent.product_key_id,
    MCPUsageEvent.created_at,
)
# One billable event per (tenant, credential, client key). Partial so the many
# keyless rows are not bounded by a NULL-inclusive constraint.
Index(
    "uq_mcp_usage_request_idempotency",
    MCPUsageEvent.tenant_id,
    MCPUsageEvent.credential_scope,
    MCPUsageEvent.request_idempotency_key,
    unique=True,
    postgresql_where=text("request_idempotency_key IS NOT NULL"),
)
