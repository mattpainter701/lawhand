"""Store staff invitations as hashed, expiring, single-use rows.

Until now an invite wrote its raw token into ``users.password_hash`` as
``invite:<token>`` and emailed a reset-password link that nothing could
redeem, so an invited person had no way in. This table is where the token
hash, expiry, and acceptance live instead.

Legacy ``invite:`` rows are backfilled with a fresh seven-day window: their
links never worked, so restarting the clock is the only way those invitees can
use them. ``users.password_hash`` is not touched here; clearing the legacy
prefix is a later contract migration once this has been live for a week.

The lookup policy is SELECT-only and matches exactly one presented token hash,
the same shape as the SMB bootstrap policy in 130. It never uses the global
``app.rls_bypass`` escape hatch.

Downgrade drops the table. Invitations created after upgrade are lost and
their users stay inactive; an administrator re-invites them. Nothing else is
affected because upgrade only adds.

Revision ID: 192_user_invitations
Revises: 191_sample_template_provenance
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "192_user_invitations"
down_revision = "191_sample_template_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_invitations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_method", sa.String(20)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "accepted_method IS NULL OR accepted_method IN "
            "('password', 'google', 'microsoft')",
            name="ck_user_invitations_accepted_method",
        ),
    )
    op.create_index("idx_user_invitations_tenant", "user_invitations", ["tenant_id"])
    op.create_index(
        "uq_user_invitations_open",
        "user_invitations",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )

    # Backfill before RLS is enabled on the new table. Reading ``users`` across
    # tenants needs the transaction-local auth bypass the users policy honours;
    # it is switched off again immediately afterwards.
    op.execute("SELECT set_config('app.rls_bypass', 'on', true)")
    op.execute(
        """
        INSERT INTO user_invitations (tenant_id, user_id, token_hash, expires_at)
        SELECT tenant_id,
               id,
               encode(digest(substr(password_hash, 8), 'sha256'), 'hex'),
               now() + interval '7 days'
        FROM users
        WHERE password_hash LIKE 'invite:%'
          AND is_active = false
        """
    )
    op.execute("SELECT set_config('app.rls_bypass', 'off', true)")

    op.execute("ALTER TABLE user_invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_invitations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY user_invitations_tenant_isolation ON user_invitations
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY user_invitations_token_lookup ON user_invitations
        FOR SELECT TO PUBLIC
        USING (
            NULLIF(current_setting('app.invite_token_hash', true), '') IS NOT NULL
            AND token_hash = current_setting('app.invite_token_hash', true)
        )
        """
    )


def downgrade():
    op.execute("DROP POLICY IF EXISTS user_invitations_token_lookup ON user_invitations")
    op.execute(
        "DROP POLICY IF EXISTS user_invitations_tenant_isolation ON user_invitations"
    )
    op.drop_index("uq_user_invitations_open", table_name="user_invitations")
    op.drop_index("idx_user_invitations_tenant", table_name="user_invitations")
    op.drop_table("user_invitations")
