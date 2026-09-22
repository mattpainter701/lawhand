"""A matter-scoped index over the cached text of its documents (Phase 5e).

``document_text_extractions`` (migration 197) keeps each document's text and
OCR lines per tenant and digest, but nothing could search it: reading a
matter's documents meant opening them one at a time. This table holds that
text in retrieval-sized pieces, per matter and per document, with a
full-text vector always and an embedding when the firm has an embedding
provider, so "what do this matter's documents say about the hearing date"
is one query over one matter.

Rows are derived data. They are keyed by the document's digest and the
extraction engine version, so a document whose bytes change is re-indexed
and a document that is deleted takes its rows with it (``ON DELETE
CASCADE`` on the matter document and the matter). Nothing here is a matter
record; a search result is a pointer to an excerpt of a document a person
can open.

Downgrade drops the table; the extraction cache it was built from remains.

Revision ID: 200_matter_document_index
Revises: 199_workflow_document_requests
"""

from alembic import op

revision = "200_matter_document_index"
down_revision = "199_workflow_document_requests"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
_TABLE = "matter_document_chunks"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""CREATE TABLE {_TABLE} (
      id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
      tenant_id uuid NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
      matter_id uuid NOT NULL,
      matter_document_id uuid NOT NULL,
      document_sha256 varchar(64) NOT NULL,
      engine_version varchar(20) NOT NULL,
      chunk_index integer NOT NULL,
      content text NOT NULL,
      fts tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED,
      embedding vector(1536),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_{_TABLE}_position UNIQUE (tenant_id, matter_document_id, chunk_index),
      CONSTRAINT ck_{_TABLE}_sha256 CHECK (document_sha256 ~ '^[0-9a-f]{{64}}$'),
      CONSTRAINT ck_{_TABLE}_index CHECK (chunk_index >= 0),
      FOREIGN KEY (tenant_id, matter_document_id)
        REFERENCES matter_documents (tenant_id, id) ON DELETE CASCADE,
      FOREIGN KEY (tenant_id, matter_id)
        REFERENCES matters (tenant_id, id) ON DELETE CASCADE
    )"""
    )
    op.execute(f"CREATE INDEX ix_{_TABLE}_matter ON {_TABLE} (tenant_id, matter_id)")
    op.execute(f"CREATE INDEX ix_{_TABLE}_fts ON {_TABLE} USING gin (fts)")
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
