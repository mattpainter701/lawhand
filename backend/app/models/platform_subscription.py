"""LawHand subscription billing; separate from firms' end-client invoices."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PlatformSubscription(Base):
    __tablename__ = "platform_subscriptions"
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    customer_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )
    subscription_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )
    status: Mapped[str] = mapped_column(String(30), default="none", nullable=False)
    phase: Mapped[str] = mapped_column(String(30), default="idle", nullable=False)
    checkout_token: Mapped[str | None] = mapped_column(String(200), nullable=True)
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkout_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    offer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consent_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
