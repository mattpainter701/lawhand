"""Add the explicit Premium AI override for trial firms.

Revision ID: 193_trial_premium_override
Revises: 192_user_invitations
"""

from alembic import op
import sqlalchemy as sa


revision = "193_trial_premium_override"
down_revision = "192_user_invitations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenants",
        sa.Column(
            "premium_ai_trial_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("tenants", "premium_ai_trial_enabled")
