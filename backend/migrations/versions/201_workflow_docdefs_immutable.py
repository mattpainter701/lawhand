"""Approved workflow versions keep their document requests immutable at the database.

Migration 148 guards every definition table of an approved workflow template
version with ``prevent_approved_workflow_mutation``: a stage, checklist item
or field requirement of an approved version cannot be inserted, changed or
deleted, except by the authorised demo purge. Migration 199 added
``matter_workflow_document_definitions`` beside them without that trigger.
The application still catches a drift (the preview recomputes the version
digest and refuses with 409), but the sibling tables are protected one layer
lower, and this one should be too.

Downgrade drops the trigger only; the function belongs to 148.

Revision ID: 201_workflow_docdefs_immutable
Revises: 200_matter_document_index
"""

from alembic import op

revision = "201_workflow_docdefs_immutable"
down_revision = "200_matter_document_index"
branch_labels = None
depends_on = None

_TABLE = "matter_workflow_document_definitions"


def upgrade():
    op.execute(
        f"CREATE TRIGGER {_TABLE}_approved_immutable "
        f"BEFORE INSERT OR UPDATE OR DELETE ON {_TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION prevent_approved_workflow_mutation()"
    )


def downgrade():
    op.execute(f"DROP TRIGGER IF EXISTS {_TABLE}_approved_immutable ON {_TABLE}")
