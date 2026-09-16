"""Positioned e-signature field validation.

The canonical coordinate system is the generated PDF: points, origin at the
bottom-left, and a one-based page number. The portal and the executed-copy
renderer consume the validated manifest rather than coordinates from a DOCX
preview, so a placement is always bound to the exact PDF digest it was
reviewed on.

Binding a template's signing fields to a freshly generated document can fail
for reasons only the template author can fix (a signing field carrying no
signer role, a field nobody ever positioned) and for one reason nobody can fix
on the saved artifact at all: a Word or Markdown output has no PDF page to
position anything on. Generation must still save the unsigned document, so
those reasons are collected per field into a :class:`PlacementReport` instead
of raised. They are then carried on the document, because the dispatch gate
that reads them is the moment staff actually feel the block -- and a gate that
cannot say which field is wrong, or that asks for a review no screen can show,
is what turns a template defect into a stalled matter.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from math import isfinite
import re
from typing import Any, Iterable

logger = logging.getLogger(__name__)


class PlacementError(ValueError):
    """Raised when a placement cannot be safely bound to a signing request."""


#: Stable reason codes. They are persisted on the matter document and read
#: back at dispatch, so they are part of the contract: rename one and old rows
#: stop explaining themselves.
MISSING_SIGNER_ROLE = "missing_signer_role"
MISSING_PDF_PLACEMENT = "missing_pdf_placement"
UNREADABLE_PDF = "unreadable_pdf"
UNSUPPORTED_PDF_PAGE = "unsupported_pdf_page"
PAGE_OUT_OF_RANGE = "page_out_of_range"
INVALID_GEOMETRY = "invalid_geometry"
NO_PDF_OUTPUT = "no_pdf_output"
WORD_SOURCE_NOT_POSITIONABLE = "word_source_not_positionable"

#: What the firm has to change to clear each code. Keyed by code so the
#: dispatch message and the generation warning give identical advice.
REMEDIES = {
    MISSING_SIGNER_ROLE: (
        "Open the template, select this field, and set its signer role."
    ),
    MISSING_PDF_PLACEMENT: (
        "Position this field on the template's PDF, or place it by hand on the "
        "generated PDF before sending."
    ),
    UNREADABLE_PDF: "Regenerate the document and try again.",
    UNSUPPORTED_PDF_PAGE: (
        "Rebuild the template from an unrotated PDF whose CropBox matches its "
        "MediaBox."
    ),
    PAGE_OUT_OF_RANGE: (
        "The generated document has fewer pages than the template placed "
        "fields on. Re-review the template's placements."
    ),
    INVALID_GEOMETRY: (
        "Re-review this field's position in the template so it sits inside the " "page."
    ),
    NO_PDF_OUTPUT: (
        "Regenerate this document with Word-to-PDF conversion enabled: signing "
        "positions can only be placed on a PDF."
    ),
    WORD_SOURCE_NOT_POSITIONABLE: (
        "Open the placement review on this generated PDF and place a field for "
        "each signer."
    ),
}


@dataclass(frozen=True)
class PlacementProblem:
    """One reason a signing field could not be bound to the generated PDF."""

    code: str
    detail: str
    field: str = ""
    role: str = ""

    @property
    def remedy(self) -> str:
        return REMEDIES.get(self.code, "")

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "detail": self.detail,
            "field": self.field,
            "role": self.role,
            "remedy": self.remedy,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "PlacementProblem | None":
        if not isinstance(raw, dict):
            return None
        code = str(raw.get("code") or "").strip()
        detail = str(raw.get("detail") or "").strip()
        if not code and not detail:
            return None
        return cls(
            code=code,
            detail=detail,
            field=str(raw.get("field") or ""),
            role=str(raw.get("role") or ""),
        )


@dataclass(frozen=True)
class PlacementReport:
    """What binding a template's signing fields to one generated file found."""

    placements: list[dict]
    roles: list[str]
    signing_required: bool
    problems: list[PlacementProblem]
    output_is_pdf: bool

    @property
    def blocked(self) -> bool:
        """The document needs positions before dispatch but carries none."""
        return bool(self.signing_required and not self.placements)

    @property
    def recoverable(self) -> bool:
        """Staff can still place fields by hand -- only ever true for a PDF."""
        return self.output_is_pdf

    def as_dicts(self) -> list[dict[str, str]]:
        return [problem.as_dict() for problem in self.problems]


@dataclass(frozen=True)
class PositionedField:
    field_id: str
    field_type: str
    role: str
    page: int
    rect: tuple[float, float, float, float]
    page_width: float
    page_height: float
    source_sha256: str

    @property
    def width(self) -> float:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> float:
        return self.rect[3] - self.rect[1]


def is_signing_template_field(field: dict | None) -> bool:
    """Signing dates are supplied by the signer, unlike ordinary document dates."""
    return bool(
        isinstance(field, dict)
        and (
            field.get("field_type") in {"signature", "initials"}
            or (
                field.get("field_type") == "date"
                and str(field.get("signer_role") or "").strip()
            )
        )
    )


def signing_template_fields(variable_schema: dict | None) -> list[dict]:
    schema = variable_schema if isinstance(variable_schema, dict) else {}
    return [
        field
        for field in schema.get("fields", [])
        if isinstance(field, dict)
        and field.get("included") is not False
        and is_signing_template_field(field)
    ]


def signing_field_roles(variable_schema: dict | None) -> list[str]:
    """The distinct signer roles an included signing field names."""
    return sorted(
        {
            str(field.get("signer_role") or "").strip()
            for field in signing_template_fields(variable_schema)
        }
        - {""}
    )


def _field_label(field: dict, index: int) -> str:
    for key in ("name", "label"):
        value = str(field.get(key) or "").strip()
        if value:
            return value
    return f"field {index + 1}"


def _overlays_of(field: dict) -> list:
    overlays = field.get("pdf_overlays")
    if isinstance(overlays, list) and overlays:
        return overlays
    overlay = field.get("pdf_overlay")
    return [overlay] if overlay else []


def _unsupported_page_reason(page) -> str | None:
    """Why this PDF page cannot carry a positioned signature, or ``None``.

    Shared so the per-field report and the fail-closed dispatch check apply
    exactly one definition of a placeable page.
    """
    if int(page.get("/Rotate", 0) or 0) % 360 or page.get("/UserUnit") not in (
        None,
        1,
        1.0,
    ):
        return "Rotated or scaled PDF pages are not supported for signing placement"
    box = page.mediabox
    crop = page.cropbox
    if (
        float(box.left) != 0
        or float(box.bottom) != 0
        or float(crop.left) != 0
        or float(crop.bottom) != 0
    ):
        return "PDF pages with non-zero origin or CropBox are not supported"
    if (
        abs(float(crop.width) - float(box.width)) > 0.5
        or abs(float(crop.height) - float(box.height)) > 0.5
    ):
        return "PDF CropBox must match MediaBox for signing placement"
    return None


def _bind_template_placements(
    variable_schema: dict | None, *, source: bytes
) -> tuple[list[dict], list[PlacementProblem]]:
    """Bind every included signing placement, collecting per-field failures.

    One misconfigured field used to discard every good placement in the
    template alongside it, so a single missing signer role could strand a
    document that was otherwise fully positioned. Each field is judged on its
    own here; only a page-level defect can take its neighbours with it.
    """
    from io import BytesIO
    from pypdf import PdfReader

    fields = signing_template_fields(variable_schema)
    if not fields:
        return [], []
    digest = hashlib.sha256(source).hexdigest()
    try:
        pages = PdfReader(BytesIO(source), strict=False).pages
    except Exception:
        return [], [
            PlacementProblem(
                UNREADABLE_PDF,
                "The generated PDF could not be verified for signing",
            )
        ]

    placements: list[dict] = []
    problems: list[PlacementProblem] = []
    for index, field in enumerate(fields):
        label = _field_label(field, index)
        role = str(field.get("signer_role") or "").strip()
        overlays = _overlays_of(field)
        if not role:
            problems.append(
                PlacementProblem(
                    MISSING_SIGNER_ROLE,
                    f"Signing field {label!r} requires a signer role before it "
                    "can be positioned",
                    field=label,
                )
            )
            continue
        if not overlays:
            problems.append(
                PlacementProblem(
                    MISSING_PDF_PLACEMENT,
                    f"Signing field {label!r} has no reviewed PDF placement",
                    field=label,
                    role=role,
                )
            )
            continue
        for overlay_index, overlay in enumerate(overlays):
            if not isinstance(overlay, dict) or not overlay.get("rect"):
                problems.append(
                    PlacementProblem(
                        MISSING_PDF_PLACEMENT,
                        f"Signing field {label!r} requires final PDF placement "
                        "review",
                        field=label,
                        role=role,
                    )
                )
                continue
            page_no = overlay.get("page")
            if (
                isinstance(page_no, bool)
                or not isinstance(page_no, int)
                or not 1 <= page_no <= len(pages)
            ):
                problems.append(
                    PlacementProblem(
                        PAGE_OUT_OF_RANGE,
                        f"Signing field {label!r} is placed on a page that is "
                        "absent from the generated PDF",
                        field=label,
                        role=role,
                    )
                )
                continue
            page = pages[page_no - 1]
            unsupported = _unsupported_page_reason(page)
            if unsupported:
                problems.append(
                    PlacementProblem(
                        UNSUPPORTED_PDF_PAGE,
                        f"{unsupported} (page {page_no})",
                        field=label,
                        role=role,
                    )
                )
                continue
            box = page.mediabox
            candidate = {
                "field_id": f"field-{index}-{overlay_index}",
                "field_type": field.get("signing_type") or field["field_type"],
                "role": role,
                "page": page_no,
                "rect": overlay["rect"],
                "page_width": float(box.width),
                "page_height": float(box.height),
                "source_sha256": digest,
            }
            try:
                validate_placements(
                    [candidate], source_sha256=digest, signer_roles={role}
                )
            except PlacementError as exc:
                problems.append(
                    PlacementProblem(
                        INVALID_GEOMETRY,
                        f"Signing field {label!r}: {exc}",
                        field=label,
                        role=role,
                    )
                )
                continue
            placements.append(candidate)
    return placements, problems


def template_positioned_fields(
    variable_schema: dict | None, *, source: bytes
) -> list[dict]:
    """Bind every included signing placement, raising on the first problem.

    The fail-closed form, for callers that must not proceed on a partially
    bound template. Generation uses :func:`template_placement_report` instead
    so it can save the unsigned document and still report what went wrong.
    """
    placements, problems = _bind_template_placements(variable_schema, source=source)
    if problems:
        raise PlacementError(problems[0].detail)
    return placements


def template_placement_report(
    variable_schema: dict | None,
    *,
    source: bytes,
    template_format: str,
    output_format: str | None = None,
) -> PlacementReport:
    """Bind a template's signing fields to one generated file, and explain.

    Never raises: generation must be able to save an unsigned document. The
    report says whether dispatch will be blocked, why, and whether placing
    fields by hand can still clear it.

    The two formats are genuinely different questions. ``template_format``
    decides whether the template carries PDF geometry to bind at all -- only a
    PDF template does. ``output_format`` decides whether the *saved artifact*
    has a page a human could place a field on, which is what makes a block
    recoverable. A Word template converted to PDF is unbindable but perfectly
    recoverable; the same template saved as .docx is neither.
    """
    fields = signing_template_fields(variable_schema)
    roles = signing_field_roles(variable_schema)
    signing_required = bool(fields)
    source_format = str(template_format or "").lower()
    saved_format = str(
        output_format if output_format is not None else template_format or ""
    ).lower()
    output_is_pdf = saved_format == "pdf"
    if not signing_required:
        return PlacementReport([], roles, False, [], output_is_pdf)
    if not output_is_pdf:
        # A Word or Markdown artifact has no page geometry at all. Saying so is
        # the whole point: this used to produce an empty manifest in silence and
        # leave dispatch demanding a review of a file no placement screen opens.
        return PlacementReport(
            [],
            roles,
            True,
            [
                PlacementProblem(
                    NO_PDF_OUTPUT,
                    "This document was generated as "
                    f"{(saved_format or 'a non-PDF file').upper()}, which has no "
                    "PDF page to position signing fields on",
                )
            ],
            False,
        )
    if source_format != "pdf":
        # Converted to PDF from a Word template: there were never any overlay
        # coordinates to bind, but the saved PDF can be reviewed by hand.
        return PlacementReport(
            [],
            roles,
            True,
            [
                PlacementProblem(
                    WORD_SOURCE_NOT_POSITIONABLE,
                    "This document came from a Word template, which carries no "
                    "PDF geometry to bind signing fields to",
                )
            ],
            True,
        )
    placements, problems = _bind_template_placements(variable_schema, source=source)
    return PlacementReport(placements, roles, True, problems, True)


def generated_signing_metadata(
    variable_schema: dict | None, *, source: bytes, template_format: str
) -> tuple[list[dict], list[str], bool]:
    """Keep generation usable while requiring verified placements at dispatch.

    Compatibility shim over :func:`template_placement_report` for callers that
    only need the manifest. Prefer the report: it carries the reasons, and a
    caller that drops them reproduces the silent failure this module exists to
    prevent.
    """
    report = template_placement_report(
        variable_schema,
        source=source,
        template_format=template_format,
        output_format=template_format,
    )
    return report.placements, report.roles, report.signing_required


def placement_block_detail(
    problems: Iterable[Any],
    *,
    filename: str | None = None,
    output_is_pdf: bool = True,
) -> str:
    """The dispatch-time message for a document that carries no placements.

    Accepts stored dicts or :class:`PlacementProblem` values, because this is
    read back from a JSON column written by an earlier request.
    """
    parsed = [
        item if isinstance(item, PlacementProblem) else PlacementProblem.from_dict(item)
        for item in problems or []
    ]
    parsed = [item for item in parsed if item is not None]
    document = f'"{filename}"' if filename else "this document"
    if not parsed:
        return (
            f"Review signing field positions on {document} before sending. "
            "Open the placement review and add a field for every signer."
        )
    if any(problem.code == NO_PDF_OUTPUT for problem in parsed):
        blocking = next(problem for problem in parsed if problem.code == NO_PDF_OUTPUT)
        return f"{document} cannot be sent for signature: {blocking.detail}. {blocking.remedy}"
    # Repeat a page-level reason once, not once per field that tripped it.
    seen: set[tuple[str, str]] = set()
    lines: list[str] = []
    for problem in parsed:
        key = (problem.code, problem.detail)
        if key in seen:
            continue
        seen.add(key)
        lines.append(problem.detail)
    remedies = list(
        dict.fromkeys(problem.remedy for problem in parsed if problem.remedy)
    )
    head = f"{document} has no reviewed signing positions."
    if output_is_pdf:
        head += (
            " Place the fields on the generated PDF before sending, or fix the "
            "template so they bind automatically."
        )
    return " ".join([head, "Unbound: " + "; ".join(lines) + ".", *remedies])


def log_placement_report(report: PlacementReport, **context: Any) -> None:
    """Record an unbound signing field. Silence here is what cost us a matter."""
    if not report.problems:
        return
    logger.warning(
        "signing placements unbound: %s",
        "; ".join(
            f"{problem.code}:{problem.field or '-'}" for problem in report.problems
        ),
        extra={
            "signing_placement_problems": report.as_dicts(),
            "signing_placement_blocked": report.blocked,
            "signing_placement_recoverable": report.recoverable,
            **context,
        },
    )


def _number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PlacementError(f"{label} must be a finite number") from exc
    if not isfinite(result):
        raise PlacementError(f"{label} must be a finite number")
    return result


def validate_placements(
    placements: Iterable[dict[str, Any]],
    *,
    source_sha256: str,
    signer_roles: set[str],
    required_roles: Iterable[str] = (),
) -> list[PositionedField]:
    """Validate and freeze placements against the exact generated PDF digest."""
    if not isinstance(source_sha256, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}", source_sha256
    ):
        raise PlacementError("A generated PDF SHA-256 is required for placements")
    result: list[PositionedField] = []
    placements = list(placements)
    if len(placements) > 100:
        raise PlacementError("At most 100 positioned fields are supported")
    seen_ids: set[str] = set()
    for raw in placements:
        if not isinstance(raw, dict):
            raise PlacementError("Each positioned field must be an object")
        field_id = str(raw.get("field_id") or "").strip()
        role = str(raw.get("role") or "").strip()
        field_type = str(raw.get("field_type") or "").strip().lower()
        if not field_id or len(field_id) > 200 or field_id in seen_ids:
            raise PlacementError("Positioned field IDs must be unique and non-empty")
        if len(role) > 100 or role not in signer_roles:
            raise PlacementError(f"Positioned field role '{role}' has no signer")
        if field_type not in {"signature", "date", "initials"}:
            raise PlacementError(
                "Positioned fields must be signature, date, or initials"
            )
        if str(raw.get("source_sha256") or "").lower() != source_sha256.lower():
            raise PlacementError("Positioned field geometry is stale for this PDF")
        page = raw.get("page")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise PlacementError("Positioned field page must be a positive integer")
        page_width = _number(raw.get("page_width"), "page_width")
        page_height = _number(raw.get("page_height"), "page_height")
        rect = raw.get("rect")
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            raise PlacementError("Positioned field rect must contain four numbers")
        values = tuple(_number(value, "rect") for value in rect)
        x0, y0, x1, y1 = values
        if page_width <= 0 or page_height <= 0 or x1 - x0 < 1 or y1 - y0 < 1:
            raise PlacementError("Positioned field geometry must have positive bounds")
        if x0 < 0 or y0 < 0 or x1 > page_width or y1 > page_height:
            raise PlacementError("Positioned field falls outside its PDF page")
        seen_ids.add(field_id)
        result.append(
            PositionedField(
                field_id,
                field_type,
                role,
                page,
                values,
                page_width,
                page_height,
                source_sha256.lower(),
            )
        )
    if set(required_roles) - {field.role for field in result}:
        raise PlacementError(
            "Add signing fields for every role required by the generated document"
        )
    return result


def validate_pdf_geometry(source: bytes, fields: Iterable[PositionedField]) -> None:
    """Bind page count and MediaBox geometry to the supplied generated PDF."""
    try:
        from io import BytesIO
        from pypdf import PdfReader

        pages = PdfReader(BytesIO(source), strict=False).pages
    except Exception as exc:
        raise PlacementError(
            "The generated PDF geometry could not be verified"
        ) from exc
    for field in fields:
        if field.page > len(pages):
            raise PlacementError(
                "Positioned field page is absent from the generated PDF"
            )
        page = pages[field.page - 1]
        unsupported = _unsupported_page_reason(page)
        if unsupported:
            raise PlacementError(unsupported)
        box = page.mediabox
        if (
            abs(float(box.width) - field.page_width) > 0.5
            or abs(float(box.height) - field.page_height) > 0.5
        ):
            raise PlacementError("Positioned field geometry is stale for this PDF page")
