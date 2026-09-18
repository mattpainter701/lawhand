"""Where a Word template's signing fields land on the generated PDF.

A PDF template carries geometry: the author placed each signing field on a
page, and generation binds those rectangles to the output. A Word template
cannot. Its text reflows as the values are filled in, so a rectangle placed
on a preview lands somewhere else on the generated document, and until now a
Word template's signing fields were bound to nothing and left for staff to
place by hand on every generated copy.

What a Word template *can* carry is the caption printed beside the field:
"Client Signature:", "By:", "MOTHER". The template already knows it -- it is
the text around the field's span in the Word document -- and the author can
override it. This module finds that caption in the converted PDF and places
the field at it. It is what the detector in ``plan`` does by guessing, done
with an anchor the template declared, so the result is bound at generation
the way a PDF template's is and never reaches the dispatch gate as a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import re
from typing import Sequence

from pypdf import PdfReader

from app.services.esign import plan as _plan
from app.services.esign.placement import (
    ANCHOR_AMBIGUOUS,
    ANCHOR_NOT_FOUND,
    INVALID_GEOMETRY,
    MISSING_SIGNER_ROLE,
    UNREADABLE_PDF,
    PlacementError,
    PlacementProblem,
    validate_placements,
)

#: Where the field sits relative to its caption: "Client Signature: ____"
#: (after), "____, MOTHER" (before), or a rule on the line under "Client:"
#: (below).
PLACEMENTS = ("after", "before", "below")
#: How far under a caption its rule may sit before it is somebody else's.
_BELOW_REACH = 40.0
_RULE_LINE = re.compile(r"^[\s_]+$")


@dataclass(frozen=True)
class WordAnchor:
    field: str
    field_type: str
    role: str
    text: str
    placement: str = "after"


@dataclass(frozen=True)
class _Match:
    page_no: int
    lines: list
    index: int
    start: int
    end: int
    page_width: float
    page_height: float

    @property
    def line(self):
        return self.lines[self.index]


def _pattern(text: str, *, ignore_case: bool) -> re.Pattern:
    tokens = [re.escape(token) for token in text.split()]
    return re.compile(r"\s+".join(tokens), re.IGNORECASE if ignore_case else 0)


def _matches(pages: list, anchor: WordAnchor) -> list[_Match]:
    for ignore_case in (False, True):
        pattern = _pattern(anchor.text, ignore_case=ignore_case)
        found = []
        for page_no, lines, width, height in pages:
            for index, line in enumerate(lines):
                hit = pattern.search(line.text)
                if hit:
                    found.append(
                        _Match(
                            page_no, lines, index, hit.start(), hit.end(), width, height
                        )
                    )
        if found:
            return found
    return []


def _rule_for(match: _Match, placement: str):
    """The printed blank the field sits on: ``(line, underscore match)`` or None."""
    line = match.line
    if placement == "after":
        hit = _plan._UNDERSCORES.search(line.text, match.end)
        return (line, hit) if hit else None
    if placement == "before":
        hits = [
            hit
            for hit in _plan._UNDERSCORES.finditer(line.text)
            if hit.end() <= match.start
        ]
        return (line, hits[-1]) if hits else None
    below = match.lines[match.index + 1] if match.index + 1 < len(match.lines) else None
    if (
        below is not None
        and 0 < line.y - below.y <= _BELOW_REACH
        and _RULE_LINE.match(below.text)
    ):
        hit = _plan._UNDERSCORES.search(below.text)
        return (below, hit) if hit else None
    return None


def _rect(match: _Match, anchor: WordAnchor) -> tuple[float, float, float, float]:
    line = match.line
    if anchor.field_type == "date":
        default_width, height = _plan.DATE_BOX_WIDTH, 24.0
    else:
        default_width, height = _plan.SIGNATURE_BOX_WIDTH, _plan.SIGNATURE_BOX_HEIGHT
    rule = _rule_for(match, anchor.placement)
    if rule is not None:
        rule_line, hit = rule
        x0 = rule_line.x_at(hit.start())
        printed = max(_plan._text_width(hit.group(0), rule_line.font_size), 60.0)
        right = x0 + max(printed, default_width)
        following = _plan._next_content_x(rule_line, rule_line.text, hit.end())
        if following is not None:
            right = min(right, max(following, x0 + printed))
        baseline = rule_line.y
    elif anchor.placement == "before":
        right = max(line.x_at(match.start) - 6.0, default_width)
        x0 = right - default_width
        baseline = line.y
    elif anchor.placement == "below":
        x0 = line.x_at(match.start)
        right = x0 + default_width
        baseline = line.y - max(18.0, line.font_size * 1.8)
    else:
        x0 = line.x_at(match.end) + 6.0
        right = x0 + default_width
        baseline = line.y
    return _plan._clamp_rect(
        (x0, baseline - 4, right, baseline - 4 + height),
        match.page_width,
        match.page_height,
    )


def locate_word_signing_fields(
    pdf: bytes, anchors: Sequence[WordAnchor]
) -> tuple[list[dict], list[PlacementProblem]]:
    """Place each anchored field on the converted PDF, or say why it could not be.

    Never raises. A caption that is missing, or printed more than once with
    no blank to tell the copies apart, is reported for that field alone; the
    other fields still bind.
    """
    digest = hashlib.sha256(pdf).hexdigest()
    try:
        reader = PdfReader(BytesIO(pdf), strict=False)
        pages = [
            (
                number,
                _plan._text_lines(_plan._text_runs(page)),
                float(page.mediabox.width),
                float(page.mediabox.height),
            )
            for number, page in enumerate(reader.pages, start=1)
        ]
    except Exception:
        return [], [
            PlacementProblem(
                UNREADABLE_PDF, "The generated PDF could not be verified for signing"
            )
        ]
    placements: list[dict] = []
    problems: list[PlacementProblem] = []
    for index, anchor in enumerate(anchors):
        label = anchor.field or f"field {index + 1}"
        if not anchor.role.strip():
            # ``validate_placements`` is given this field's own role as the
            # signer set, so an empty one would validate against {""} here and
            # fail at dispatch instead, where nothing names the field.
            problems.append(
                PlacementProblem(
                    MISSING_SIGNER_ROLE,
                    f"Signing field {label!r} requires a signer role before it "
                    "can be positioned",
                    field=label,
                )
            )
            continue
        if not anchor.text.strip():
            problems.append(
                PlacementProblem(
                    ANCHOR_NOT_FOUND,
                    f"Signing field {label!r} has no caption to anchor to in the Word "
                    "document",
                    field=label,
                    role=anchor.role,
                )
            )
            continue
        matches = _matches(pages, anchor)
        if len(matches) > 1:
            with_rule = [item for item in matches if _rule_for(item, anchor.placement)]
            matches = with_rule or matches
        if not matches:
            problems.append(
                PlacementProblem(
                    ANCHOR_NOT_FOUND,
                    f"Signing field {label!r}: its caption {anchor.text!r} was not "
                    "found in the generated PDF",
                    field=label,
                    role=anchor.role,
                )
            )
            continue
        if len(matches) > 1:
            problems.append(
                PlacementProblem(
                    ANCHOR_AMBIGUOUS,
                    f"Signing field {label!r}: its caption {anchor.text!r} is printed "
                    f"{len(matches)} times in the generated PDF",
                    field=label,
                    role=anchor.role,
                )
            )
            continue
        match = matches[0]
        candidate = {
            "field_id": f"anchor-{index}",
            "field_type": anchor.field_type,
            "role": anchor.role,
            "page": match.page_no,
            "rect": list(_rect(match, anchor)),
            "page_width": match.page_width,
            "page_height": match.page_height,
            "source_sha256": digest,
            "source": "anchored",
        }
        try:
            validate_placements(
                [candidate], source_sha256=digest, signer_roles={anchor.role}
            )
        except PlacementError as exc:
            problems.append(
                PlacementProblem(
                    INVALID_GEOMETRY,
                    f"Signing field {label!r}: {exc}",
                    field=label,
                    role=anchor.role,
                )
            )
            continue
        placements.append(candidate)
    return placements, problems
