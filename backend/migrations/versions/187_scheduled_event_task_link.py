"""Link scheduled events to the task whose work they block out.

Revision ID: 187_scheduled_event_task_link
Revises: 186_billing_parity
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "187_scheduled_event_task_link"
down_revision = "186_billing_parity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scheduled_events",
        sa.Column("task_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_scheduled_events_task_id",
        "scheduled_events",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_scheduled_events_task_id",
        "scheduled_events",
        ["tenant_id", "task_id"],
    )


def downgrade():
    op.drop_index("idx_scheduled_events_task_id", table_name="scheduled_events")
    op.drop_constraint(
        "fk_scheduled_events_task_id", "scheduled_events", type_="foreignkey"
    )
    op.drop_column("scheduled_events", "task_id")
