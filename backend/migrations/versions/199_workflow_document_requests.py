"""Workflow templates can request documents: definitions and the run step.

A bounded workflow template lists stages and checklist items; applying a run
sets the matter's stage and creates the tasks. Firms also want a rule such as
"on a new personal-injury matter, prepare the engagement letter and the HIPAA
release". This migration adds ``matter_workflow_document_definitions``, one
row per document a template version requests: which firm document template,
in which stage, with which assignee. On apply, each request opens a Smart
Fill session pre-filled from the matter and a "Prepare" task for the
assignee; nothing is rendered or filed without a person. The run step type
``document_propose`` records that evidence beside ``task_create``.

Downgrade drops the definition table and narrows the step-type check back.
Steps already recorded as ``document_propose`` are immutable history (the
``matter_workflow_run_steps_immutable`` trigger forbids deleting them), so
the narrower constraint is re-added ``NOT VALID``: new rows are checked,
existing evidence is kept.

Revision ID: 199_workflow_document_requests
Revises: 198_document_fill_sessions
"""

from alembic import op

revision = "199_workflow_document_requests"
down_revision = "198_document_fill_sessions"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
_TABLE = "matter_workflow_document_definitions"


def upgrade():
    op.execute(
        f"""CREATE TABLE {_TABLE} (
      id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
      tenant_id uuid NOT NULL,
      template_version_id uuid NOT NULL,
      stage_key varchar(64) NOT NULL,
      item_key varchar(64) NOT NULL,
      document_template_id uuid NOT NULL,
      title varchar(300),
      position integer NOT NULL,
      due_offset_days integer NOT NULL DEFAULT 0,
      assignee_role varchar(30) NOT NULL DEFAULT 'unassigned',
      CONSTRAINT uq_{_TABLE}_key UNIQUE (tenant_id, template_version_id, item_key),
      CONSTRAINT uq_{_TABLE}_position UNIQUE (tenant_id, template_version_id, position),
      CONSTRAINT ck_{_TABLE}_key CHECK (item_key ~ '^[a-z][a-z0-9_]{{0,63}}$'),
      CONSTRAINT ck_{_TABLE}_position CHECK (position BETWEEN 0 AND 49),
      CONSTRAINT ck_{_TABLE}_offset CHECK (due_offset_days BETWEEN 0 AND 3650),
      CONSTRAINT ck_{_TABLE}_title CHECK (title IS NULL OR btrim(title) <> ''),
      CONSTRAINT ck_{_TABLE}_assignee CHECK (assignee_role IN ('matter_owner', 'attorney_of_record', 'template_applier', 'unassigned')),
      FOREIGN KEY (tenant_id, template_version_id, stage_key)
        REFERENCES matter_workflow_stage_definitions (tenant_id, template_version_id, stage_key)
        ON DELETE RESTRICT
    )"""
    )
    op.execute(
        f"CREATE INDEX ix_{_TABLE}_version ON {_TABLE} (tenant_id, template_version_id, position)"
    )
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY {_TABLE}_tenant_isolation ON {_TABLE}
        USING (tenant_id = {_TENANT})
        WITH CHECK (tenant_id = {_TENANT})"""
    )
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")

    op.execute(
        "ALTER TABLE matter_workflow_run_steps "
        "DROP CONSTRAINT ck_matter_workflow_run_steps_type"
    )
    op.execute(
        "ALTER TABLE matter_workflow_run_steps "
        "ADD CONSTRAINT ck_matter_workflow_run_steps_type CHECK "
        "(step_type IN ('matter_stage', 'task_create', 'task_cancel', "
        "'stage_restore', 'document_propose'))"
    )


def downgrade():
    op.execute(
        "ALTER TABLE matter_workflow_run_steps "
        "DROP CONSTRAINT ck_matter_workflow_run_steps_type"
    )
    op.execute(
        "ALTER TABLE matter_workflow_run_steps "
        "ADD CONSTRAINT ck_matter_workflow_run_steps_type CHECK "
        "(step_type IN ('matter_stage', 'task_create', 'task_cancel', "
        "'stage_restore')) NOT VALID"
    )
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_tenant_isolation ON {_TABLE}")
    op.execute(f"DROP TABLE {_TABLE}")
