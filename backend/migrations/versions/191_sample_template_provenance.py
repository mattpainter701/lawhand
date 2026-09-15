"""Record where each sample-library form came from.

The catalog holds distinct files that share a title (three "ND Divorce" forms,
two "ND General", and so on). They differ in field count, size, and hash, so
they cannot be de-duplicated mechanically, and nothing in the manifest says
which court form or edition each one is. This column is where that answer
belongs once the import source is known; until then it stays null and the UI
says so rather than guessing.

Revision ID: 191_sample_template_provenance
Revises: 190_conversation_ai_preferences
"""

from alembic import op
import sqlalchemy as sa

revision = "191_sample_template_provenance"
down_revision = "190_conversation_ai_preferences"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sample_templates",
        sa.Column("provenance", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("sample_templates", "provenance")
