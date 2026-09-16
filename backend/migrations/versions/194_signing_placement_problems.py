"""Persist why a generated document's signing fields could not be bound.

Revision ID: 194_signing_placement_problems
Revises: 193_trial_premium_override
"""

from alembic import op
import sqlalchemy as sa


revision = "194_signing_placement_problems"
down_revision = "193_trial_premium_override"
branch_labels = None
depends_on = None


def upgrade():
    # Generation already records *that* a document needs placement review
    # (signing_placement_required). It never recorded *why* binding failed, so
    # the dispatch gate could only ask staff to "review positions" without
    # naming the field, and an incident left no trace to diagnose afterwards.
    op.add_column(
        "matter_documents",
        sa.Column("signing_placement_problems", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("matter_documents", "signing_placement_problems")
