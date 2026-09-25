"""Retire the customer-LLM (BYOK) settings and wipe any stored provider key.

LawHand no longer calls a firm's own model provider: firms reach LawHand
through its MCP servers from the AI tool they already pay for, so the
API-only "bring your own key" path was removed from the application. This
revision clears the three ``tenant_settings`` columns it used, so no
encrypted provider key, endpoint or deployment outlives the feature. The
columns themselves stay until a later contract migration drops them.

``tenant_settings`` carries FORCE row level security, and the migrator is the
table owner but NOBYPASSRLS, so the scoped update runs inside a NO FORCE
window and FORCE is restored straight after, as 089/090/109 do. Without the
window the statement would match no rows and leave the keys in place.

The downgrade is a no-op: the cleared secrets cannot be restored, and the
columns were never removed.

Revision ID: 204_retire_customer_llm
Revises: 203_matter_folder_share_grants
"""

from alembic import op

revision = "204_retire_customer_llm"
down_revision = "203_matter_folder_share_grants"
branch_labels = None
depends_on = None

CLEAR_CUSTOMER_LLM_SQL = """
UPDATE tenant_settings
   SET use_customer_llm = false,
       customer_llm_provider = NULL,
       customer_llm_config = NULL
 WHERE use_customer_llm IS TRUE
    OR customer_llm_provider IS NOT NULL
    OR customer_llm_config IS NOT NULL
"""


def upgrade() -> None:
    op.execute("ALTER TABLE tenant_settings NO FORCE ROW LEVEL SECURITY")
    op.execute(CLEAR_CUSTOMER_LLM_SQL)
    op.execute("ALTER TABLE tenant_settings FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Nothing to undo: the wiped provider keys cannot be recovered, and the
    # columns are still present for the previous revision's code.
    pass
