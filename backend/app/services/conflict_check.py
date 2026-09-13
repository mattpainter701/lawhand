"""
Shared conflict-check service.

Extracted from the contacts /conflict-check endpoint so it can be called
from both the contacts router (manual check) and the plugins router
(auto-check on matter create + manual re-run endpoint).

Matching deliberately fails toward review rather than clearance: a missed
conflict is the expensive error, an extra row for an attorney to dismiss is not.
"""

import operator
import re
import uuid
from functools import reduce

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.matter_assignment import MatterAssignment
from app.models.matter_party import MatterParty
from app.models.plugin import Matter

ZERO_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")

# Words shorter than this are ignored when matching a term out of order. "of",
# "&" and bare initials appear inside almost any name, so counting them would
# turn a firm name into a tenant-wide sweep.
MIN_TOKEN_LENGTH = 3
# How many distinct words of a multi-word term must appear. Two keeps
# "Alice Smith" from matching every Alice, while still finding the contact
# stored as "Alice Smith" when the search carries a middle name.
MIN_TOKEN_HITS = 2

_TOKEN_SPLIT = re.compile(r"[^0-9A-Za-z]+")


def _escape_ilike(text: str) -> str:
    """Escape % and _ wildcards for ILIKE patterns."""
    return text.replace("%", "\\%").replace("_", "\\_")


def _significant_tokens(term: str) -> list[str]:
    """Distinct words of a search term worth matching on their own."""
    tokens: list[str] = []
    seen: set[str] = set()
    for word in _TOKEN_SPLIT.split(term):
        if len(word) < MIN_TOKEN_LENGTH:
            continue
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(word)
    return tokens


def _matches_term(expr, term: str):
    """
    Match a search term against a text expression, tolerating word order.

    The whole term still matches as a substring. A term of several words also
    matches when MIN_TOKEN_HITS of its words are present in any order, which is
    what finds "Smith, Alice" copied from a caption, a first-and-last-name
    search against a record carrying a middle name, and reversed name entry.
    """
    clauses = [expr.ilike(f"%{_escape_ilike(term)}%")]
    tokens = _significant_tokens(term)
    if len(tokens) >= MIN_TOKEN_HITS:
        hits = reduce(
            operator.add,
            [
                case((expr.ilike(f"%{_escape_ilike(token)}%"), 1), else_=0)
                for token in tokens
            ],
        )
        clauses.append(hits >= MIN_TOKEN_HITS)
    return or_(*clauses)


def _contact_haystack():
    """Searchable contact fields as one string; concat_ws drops NULL columns."""
    return func.concat_ws(
        " ",
        Contact.first_name,
        Contact.last_name,
        Contact.organization_name,
        Contact.email,
    )


async def visible_matter_ids(db: AsyncSession, user) -> set[uuid.UUID] | None:
    """Matters this user may see named, or None when no restriction applies.

    Tenant isolation keeps another firm's matters out; it says nothing about a
    matter inside the firm that this user is not on. A conflict search must not
    become a way to enumerate those.
    """
    if user.role == "admin":
        return None
    assigned = set(
        (
            await db.scalars(
                select(MatterAssignment.matter_id).where(
                    MatterAssignment.tenant_id == user.tenant_id,
                    MatterAssignment.user_id == user.id,
                )
            )
        ).all()
    )
    owned = set(
        (
            await db.scalars(
                select(Matter.id).where(
                    Matter.tenant_id == user.tenant_id,
                    Matter.user_id == user.id,
                )
            )
        ).all()
    )
    return assigned | owned


def restrict_matches_to_visible(
    matches: list[dict], visible: set[uuid.UUID] | None
) -> tuple[list[dict], int]:
    """Strip matter identifiers the viewer may not see, and count what was held back.

    A counterparty-only row carries the adverse party's name as its display
    name and nothing else, so when every matter behind it is restricted the row
    itself is the disclosure and is dropped. A contact row stays: the contact is
    already listed in the firm's address book. The withheld count is returned so
    the caller can say something was hidden — a conflict search that silently
    shows less is its own hazard.
    """
    if visible is None:
        return matches, 0

    kept: list[dict] = []
    withheld = 0
    for match in matches:
        ids = list(match.get("matter_ids") or [])
        names = list(match.get("matter_names") or [])
        visible_ids = []
        visible_names = []
        for index, matter_id in enumerate(ids):
            if matter_id in visible:
                visible_ids.append(matter_id)
                if index < len(names):
                    visible_names.append(names[index])
            else:
                withheld += 1
        counterparty_only = match.get("contact_id") in (None, ZERO_UUID)
        if counterparty_only and ids and not visible_ids:
            continue
        kept.append({**match, "matter_ids": visible_ids, "matter_names": visible_names})
    return kept, withheld


async def run_conflict_check(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    names: list[str],
    emails: list[str],
    organization_names: list[str] | None = None,
    exclude_matter_ids: list[uuid.UUID] | None = None,
) -> dict:
    """
    Run a fuzzy conflict check across contacts and matter counterparties.

    Returns a dict with keys:
      clear   : bool — True when no matches found
      matches : list of dicts, each with keys:
                  contact_id, display_name, contact_type, email,
                  match_field, match_value, matter_ids, matter_names
    """
    if organization_names is None:
        organization_names = []
    if exclude_matter_ids is None:
        exclude_matter_ids = []
    matches: list[dict] = []
    # Matters already reported through a counterparty hit, so phase 2 does not
    # list the same matter a second time.
    reported_counterparty: set[uuid.UUID] = set()

    # Build (search_term, field_type) pairs
    terms = (
        [(n, "name") for n in names if n]
        + [(e, "email") for e in emails if e]
        + [(o, "organization") for o in organization_names if o]
    )

    # ── Phase 1: contact-based matches ───────────────────────────────────────
    for term, field_type in terms:
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.is_active.is_(True),
            _matches_term(_contact_haystack(), term),
        )
        result = await db.execute(stmt)
        found = result.scalars().all()

        for c in found:
            # Matters where this contact is the client
            m_stmt = select(Matter).where(
                Matter.tenant_id == tenant_id,
                Matter.client_contact_id == c.id,
            )
            m_result = await db.execute(m_stmt)
            matters = m_result.scalars().all()

            # Matters where this contact is linked in any party role. The
            # standalone search must not miss opposing counsel, witnesses, or
            # other participants merely because they are not the client.
            party_stmt = (
                select(Matter)
                .join(MatterParty, MatterParty.matter_id == Matter.id)
                .where(
                    Matter.tenant_id == tenant_id,
                    MatterParty.tenant_id == tenant_id,
                    MatterParty.contact_id == c.id,
                )
            )
            party_result = await db.execute(party_stmt)
            party_matters = party_result.scalars().all()

            # Matters where counterparty string matches
            cp_stmt = select(Matter).where(
                Matter.tenant_id == tenant_id,
                _matches_term(Matter.counterparty, term),
            )
            cp_result = await db.execute(cp_stmt)
            cp_matters = cp_result.scalars().all()

            all_matters = {
                m.id: m
                for m in matters + party_matters + cp_matters
                if m.id not in exclude_matter_ids
            }

            # Avoid duplicate contact entries
            already_seen = any(m.get("contact_id") == c.id for m in matches)
            if not already_seen:
                matches.append(
                    {
                        "contact_id": c.id,
                        "display_name": c.display_name,
                        "contact_type": c.contact_type,
                        "email": c.email,
                        "match_field": field_type,
                        "match_value": term,
                        "matter_ids": list(all_matters.keys()),
                        "matter_names": [m.matter_name for m in all_matters.values()],
                    }
                )
                reported_counterparty.update(
                    m.id for m in cp_matters if m.id in all_matters
                )

    # ── Phase 2: counterparty matches with no Contact record of their own ────
    # Whether the matter also stores a client contact says nothing about the
    # opposing party, so this is not restricted to matters without one: an
    # adverse party recorded only as free text is still a conflict.
    for term in list(names) + list(organization_names):
        if not term:
            continue
        cp_filters = [
            Matter.tenant_id == tenant_id,
            _matches_term(Matter.counterparty, term),
        ]
        if exclude_matter_ids:
            cp_filters.append(Matter.id.notin_(exclude_matter_ids))
        cp_stmt = select(Matter).where(*cp_filters)
        cp_result = await db.execute(cp_stmt)
        cp_matters = cp_result.scalars().all()

        for m in cp_matters:
            if m.id in reported_counterparty:
                continue
            reported_counterparty.add(m.id)
            matches.append(
                {
                    "contact_id": ZERO_UUID,
                    "display_name": m.counterparty,
                    "contact_type": "opposing_party",
                    "email": None,
                    "match_field": "matter_counterparty",
                    "match_value": term,
                    "matter_ids": [m.id],
                    "matter_names": [m.matter_name],
                }
            )

    return {
        "clear": len(matches) == 0,
        "matches": matches,
    }
