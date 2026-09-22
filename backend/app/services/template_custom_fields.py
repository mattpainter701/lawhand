"""Tenant-scoped, non-sensitive typed field sources for Template Studio."""

from dataclasses import dataclass

from sqlalchemy import select
from app.models.plugin import MatterEvent
from app.models.configurable_workflow import (
    CustomFieldDefinition,
    MatterCustomFieldValue,
    ContactCustomFieldValue,
)
from app.schemas.document_template import DocumentTemplateVariableSuggestion
from app.services.template_bindings import custom_binding


async def definitions(db, tenant_id):
    return list(
        (
            await db.scalars(
                select(CustomFieldDefinition)
                .where(
                    CustomFieldDefinition.tenant_id == tenant_id,
                    CustomFieldDefinition.active.is_(True),
                    CustomFieldDefinition.sensitive.is_(False),
                    CustomFieldDefinition.field_type.in_(
                        [
                            "text",
                            "long_text",
                            "number",
                            "date",
                            "boolean",
                            "single_select",
                        ]
                    ),
                )
                .order_by(CustomFieldDefinition.label)
            )
        ).all()
    )


def display_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@dataclass
class CustomFieldSources:
    """Eligible custom fields plus the matter's and client's values, read once.

    ``resolve`` builds the suggestions for as many templates as need them from
    this snapshot, so a prefill run over twenty templates does a handful of
    queries rather than re-reading the definitions and values per template.
    """

    definitions: dict
    matter_values: dict
    contact_values: dict
    reviewed: dict


async def load(db, tenant_id, matter) -> CustomFieldSources:
    definitions_by_identity = {
        (field.entity_type, str(field.id)): field
        for field in await definitions(db, tenant_id)
    }
    matter_id = getattr(matter, "id", None)
    contact_id = getattr(matter, "client_contact_id", None)
    matter_values: dict = {}
    if matter_id:
        rows = await db.scalars(
            select(MatterCustomFieldValue).where(
                MatterCustomFieldValue.tenant_id == tenant_id,
                MatterCustomFieldValue.matter_id == matter_id,
            )
        )
        matter_values = {row.field_definition_id: row for row in rows}
    contact_values: dict = {}
    if contact_id:
        rows = await db.scalars(
            select(ContactCustomFieldValue).where(
                ContactCustomFieldValue.tenant_id == tenant_id,
                ContactCustomFieldValue.contact_id == contact_id,
            )
        )
        contact_values = {row.field_definition_id: row for row in rows}
    reviewed: dict = {}
    if matter_id:
        events = await db.scalars(
            select(MatterEvent)
            .where(
                MatterEvent.tenant_id == tenant_id,
                MatterEvent.matter_id == matter_id,
                MatterEvent.event_type == "template_fact_reviewed",
            )
            .order_by(MatterEvent.created_at.desc())
        )
        for event in events:
            evidence = event.metadata_json or {}
            key = (
                str(evidence.get("field")),
                str(evidence.get("accepted_value_hmac")),
                str(evidence.get("reviewed_at")),
            )
            reviewed.setdefault(key, event)
    return CustomFieldSources(
        definitions=definitions_by_identity,
        matter_values=matter_values,
        contact_values=contact_values,
        reviewed=reviewed,
    )


def resolve(sources: CustomFieldSources, tenant_id, matter, bindings) -> dict:
    requested = {
        name: custom_binding(path)
        for name, path in bindings.items()
        if custom_binding(path)
    }
    if not requested:
        return {}
    output = {}
    for name, identity in requested.items():
        field = sources.definitions.get(identity)
        entity_type = identity[0]
        entity_id = (
            getattr(matter, "id", None)
            if entity_type == "matter"
            else getattr(matter, "client_contact_id", None)
        )
        value = None
        if field and entity_id:
            value = (
                sources.matter_values.get(field.id)
                if entity_type == "matter"
                else sources.contact_values.get(field.id)
            )
        provenance = {
            "status": "from_custom_record" if value else "binding_unresolved",
            "binding": bindings[name],
            "binding_label": field.label if field else "Unavailable data source",
        }
        if value:
            provenance.update(
                field_definition_id=str(field.id),
                schema_version=field.schema_version,
                record_id=str(value.id),
                updated_at=value.updated_at.isoformat(),
                updated_by_user_id=str(value.updated_by_user_id),
            )
        if value and entity_type == "matter":
            reviewed = sources.reviewed.get(
                (str(field.id), value.value_hmac, value.updated_at.isoformat())
            )
            if reviewed:
                evidence = reviewed.metadata_json
                provenance.update(
                    status="reviewed_from_document",
                    source_document_id=evidence["document"],
                    source_sha256=evidence["source_sha256"],
                    reviewed_by_user_id=str(reviewed.created_by),
                    reviewed_at=evidence["reviewed_at"],
                )
        output[name] = DocumentTemplateVariableSuggestion(
            variable=name,
            suggested_value=display_value(value.value_json) if value else None,
            source_type="custom_record" if value else None,
            source_field=bindings[name],
            provenance=provenance,
            review_required=True,
        )
    return output


async def suggestions(db, tenant_id, matter, bindings):
    """Read and resolve in one call, for a caller filling a single template.

    A template that binds no custom field costs nothing: the read is skipped
    rather than loading a snapshot nothing will consume.
    """

    if not any(custom_binding(path) for path in bindings.values()):
        return {}
    return resolve(await load(db, tenant_id, matter), tenant_id, matter, bindings)
