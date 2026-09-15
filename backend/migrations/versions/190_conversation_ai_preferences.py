"""Persist an assistant conversation's tier and public-case-law preference.

Both settings were request-only fields: the browser held them in component
state and never read them back, so closing and reopening a conversation
silently reverted it to Standard with public case law on. Storing them on the
conversation makes the choice survive the reopen.

Both columns carry the previous in-memory defaults as server defaults, so every
existing conversation keeps the behaviour it had before this release.

Revision ID: 190_conversation_ai_preferences
Revises: 189_matter_engagement
"""

from alembic import op
import sqlalchemy as sa

revision = "190_conversation_ai_preferences"
down_revision = "189_matter_engagement"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversations",
        sa.Column(
            "use_premium_llm",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "include_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade():
    op.drop_column("conversations", "include_public")
    op.drop_column("conversations", "use_premium_llm")
