"""Fixed/stage fees and invoice billing snapshots.

Revision ID: 186_billing_parity
Revises: 185_platform_email_suppression
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "186_billing_parity"
down_revision = "185_platform_email_suppression"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenants", sa.Column("platform_billing_provider", sa.String(20), nullable=True)
    )
    op.add_column(
        "tenants", sa.Column("platform_customer_id", sa.String(100), nullable=True)
    )
    op.add_column(
        "tenants",
        sa.Column("platform_subscription_status", sa.String(40), nullable=True),
    )
    op.add_column("invoices", sa.Column("generation_key", sa.String(36), nullable=True))
    op.create_unique_constraint(
        "uq_invoice_generation_key", "invoices", ["tenant_id", "generation_key"]
    )
    op.add_column("invoices", sa.Column("billing_details", sa.JSON(), nullable=True))
    op.create_table(
        "billing_fees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "matter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("matters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "invoice_id",
            UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_billing_fee_amount"),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'billed', 'cancelled')",
            name="ck_billing_fee_status",
        ),
    )
    op.create_index(
        "ix_billing_fees_matter", "billing_fees", ["tenant_id", "matter_id"]
    )
    op.execute("ALTER TABLE billing_fees ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE billing_fees FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON billing_fees
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)""")

    op.create_table(
        "billing_schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "matter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("matters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("next_date", sa.Date(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "matter_id", name="uq_billing_schedule_matter"
        ),
    )
    op.execute("ALTER TABLE billing_schedules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE billing_schedules FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON billing_schedules
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)""")

    op.create_table(
        "platform_subscriptions",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("customer_code", sa.String(100), nullable=True, unique=True),
        sa.Column("subscription_id", sa.String(100), nullable=True, unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("phase", sa.String(30), nullable=False),
        sa.Column("checkout_token", sa.String(200), nullable=True),
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
        sa.Column("checkout_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offer", sa.JSON(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("consent_by", UUID(as_uuid=True), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("ALTER TABLE platform_subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform_subscriptions FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON platform_subscriptions
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)""")


def downgrade():
    op.drop_column("tenants", "platform_subscription_status")
    op.drop_column("tenants", "platform_customer_id")
    op.drop_column("tenants", "platform_billing_provider")
    op.drop_table("platform_subscriptions")
    op.drop_table("billing_schedules")
    op.drop_table("billing_fees")
    op.drop_column("invoices", "billing_details")
    op.drop_constraint("uq_invoice_generation_key", "invoices", type_="unique")
    op.drop_column("invoices", "generation_key")
