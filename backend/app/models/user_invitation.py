import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserInvitation(Base):
    """A single-use, expiring invitation for a staff user to join a firm.

    Only the sha256 of the emailed token is stored. The raw token never
    touches the database, so a read of this table cannot be replayed as an
    acceptance. Acceptance is claimed with a conditional update, so two
    concurrent requests carrying the same token cannot both succeed.
    """

    __tablename__ = "user_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "user_id"),
            ("users.tenant_id", "users.id"),
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "accepted_method IS NULL OR accepted_method IN "
            "('password', 'google', 'microsoft')",
            name="ck_user_invitations_accepted_method",
        ),
        Index("idx_user_invitations_tenant", "tenant_id"),
        Index(
            "uq_user_invitations_open",
            "user_id",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
