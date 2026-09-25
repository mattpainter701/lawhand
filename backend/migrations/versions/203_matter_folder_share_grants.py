"""Remember each cloud folder share LawHand gives a matter assignee (D07).

Assigning someone to a matter shares its OneDrive and Google Drive folders
with them, but nothing recorded the provider's permission id, so removing
them from the matter (or deactivating them) never took the share back: a
person walled off from a matter kept write access to its files. This table
records every permission LawHand creates so it can remove exactly that one,
and never a share a person added in the provider directly.

``status`` moves from ``active`` to ``revoke_pending`` in the same
transaction as the unassign, then to ``revoked`` once the provider confirms.
``kept`` marks a share someone else made that LawHand deliberately left.
``matter_id`` and ``user_id`` are SET NULL so a pending removal outlives the
matter or user row that caused it.

Downgrade drops the table. Shares already removed stay removed; pending ones
are no longer retried.

Revision ID: 203_matter_folder_share_grants
Revises: 202_matter_doc_external_edit
"""

from alembic import op

revision = "203_matter_folder_share_grants"
down_revision = "202_matter_doc_external_edit"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
_TABLE = "matter_folder_share_grants"


def upgrade():
    op.execute(
        f"""CREATE TABLE {_TABLE} (
      id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
      tenant_id uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
      matter_id uuid REFERENCES matters (id) ON DELETE SET NULL,
      user_id uuid REFERENCES users (id) ON DELETE SET NULL,
      grantee_email varchar(320) NOT NULL,
      provider varchar(20) NOT NULL,
      folder_id varchar(500) NOT NULL,
      role varchar(20) NOT NULL,
      permission_id varchar(500),
      origin varchar(20) NOT NULL DEFAULT 'lawhand',
      status varchar(20) NOT NULL DEFAULT 'active',
      revoke_attempts integer NOT NULL DEFAULT 0,
      last_error text,
      revoke_requested_by uuid REFERENCES users (id) ON DELETE SET NULL,
      revoke_reason varchar(40),
      granted_at timestamptz NOT NULL DEFAULT now(),
      revoke_requested_at timestamptz,
      revoked_at timestamptz,
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_{_TABLE}_target
        UNIQUE (tenant_id, matter_id, provider, folder_id, grantee_email),
      CONSTRAINT ck_{_TABLE}_provider
        CHECK (provider IN ('onedrive', 'google_drive')),
      CONSTRAINT ck_{_TABLE}_origin
        CHECK (origin IN ('lawhand', 'legacy', 'preexisting')),
      CONSTRAINT ck_{_TABLE}_status
        CHECK (status IN ('active', 'revoke_pending', 'revoked', 'kept'))
    )"""
    )
    op.execute(f"CREATE INDEX ix_{_TABLE}_pending ON {_TABLE} (tenant_id, status)")
    op.execute(f"CREATE INDEX ix_{_TABLE}_user ON {_TABLE} (tenant_id, user_id)")
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY {_TABLE}_tenant_isolation ON {_TABLE}
        USING (tenant_id = {_TENANT})
        WITH CHECK (tenant_id = {_TENANT})"""
    )
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")


def downgrade():
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_tenant_isolation ON {_TABLE}")
    op.execute(f"DROP TABLE {_TABLE}")
