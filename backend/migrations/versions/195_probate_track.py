"""Probate track, facts, and clock anchors on estates; client-submitted assets.

Revision ID: 195_probate_track
Revises: 194_signing_placement_problems

Additive and nullable throughout: existing estates keep working with no
backfill, and the new asset columns default to the values every existing row
already meant (entered by staff, taken as verified).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "195_probate_track"
down_revision = "194_signing_placement_problems"
branch_labels = None
depends_on = None


_ESTATE_COLUMNS = (
    sa.Column("domicile_county", sa.String(150), nullable=True),
    sa.Column("will_execution_date", sa.Date(), nullable=True),
    sa.Column("probate_track", sa.String(40), nullable=True),
    sa.Column("probate_facts", postgresql.JSONB(), nullable=True),
    sa.Column("probate_determination", postgresql.JSONB(), nullable=True),
    sa.Column("probate_determined_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("appointment_date", sa.Date(), nullable=True),
    sa.Column("first_publication_date", sa.Date(), nullable=True),
    sa.Column("letters_issued_date", sa.Date(), nullable=True),
    sa.Column("closing_statement_filed_date", sa.Date(), nullable=True),
)

_ASSET_COLUMNS = (
    sa.Column(
        "source",
        sa.String(30),
        nullable=False,
        server_default=sa.text("'staff'"),
    ),
    sa.Column(
        "verification_status",
        sa.String(30),
        nullable=False,
        server_default=sa.text("'verified'"),
    ),
    sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "artifact_document_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(
            "matter_documents.id",
            ondelete="SET NULL",
            name="fk_estate_assets_artifact_document",
        ),
        nullable=True,
    ),
)


def upgrade():
    for column in _ESTATE_COLUMNS:
        op.add_column("estates", column)
    for column in _ASSET_COLUMNS:
        op.add_column("estate_assets", column)
    op.create_index(
        "ix_estate_assets_artifact_document_id",
        "estate_assets",
        ["artifact_document_id"],
    )


def downgrade():
    op.drop_index("ix_estate_assets_artifact_document_id", table_name="estate_assets")
    for column in reversed(_ASSET_COLUMNS):
        op.drop_column("estate_assets", column.name)
    for column in reversed(_ESTATE_COLUMNS):
        op.drop_column("estates", column.name)
