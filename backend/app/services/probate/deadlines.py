"""The North Dakota probate clock.

Statutory and practical dates computed from three anchors — the date of
death, the appointment date, and the first publication of the notice to
creditors — plus the closing-statement date for the one deadline that hangs
off it. The rules are a table so an attorney can read them, and ``compute`` is
pure so the table is tested without a database. ``sync`` writes the rows.

Sources: N.D.C.C. 30.1-18-05, 30.1-18-06, 30.1-19-01, 30.1-19-03, 30.1-19-06,
30.1-05-02, 30.1-21-03, 57-37.1-07, 50-06.3-07 / 50-24.1-07 and the State
Court Administrator's guidebook (Rev. Aug 2025), Appendix A.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from dateutil.relativedelta import relativedelta

DEATH = "date_of_death"
APPOINTMENT = "appointment_date"
PUBLICATION = "first_publication_date"
CLOSING = "closing_statement_filed_date"

ANCHORS: tuple[str, ...] = (DEATH, APPOINTMENT, PUBLICATION, CLOSING)


@dataclass(frozen=True)
class DeadlineRule:
    deadline_type: str
    title: str
    #: ``(anchor, offset)`` pairs; the latest resulting date wins, and a rule
    #: is skipped while any listed anchor is missing.
    anchored: tuple[tuple[str, relativedelta], ...]
    statute: str
    note: str = ""
    #: ``None`` applies to every track; otherwise the tracks it applies to.
    tracks: tuple[str, ...] | None = None
    #: A rule that needs an anchor only when it exists (publication is optional).
    when_present: str | None = None


_INFORMAL = ("informal_testate", "informal_intestate")

RULES: tuple[DeadlineRule, ...] = (
    DeadlineRule(
        "notice_heirs",
        "Send Notice and Information to Heirs and Devisees (Form 5)",
        ((APPOINTMENT, relativedelta(days=30)),),
        "N.D.C.C. 30.1-18-05",
        "Within 30 days of appointment, to every heir and devisee.",
    ),
    DeadlineRule(
        "hhs_affidavit",
        "Send Affidavit Forwarding Application to Health & Human Services (Form 7)",
        ((APPOINTMENT, relativedelta(days=14)),),
        "N.D.C.C. 50-06.3-07; 50-24.1-07",
        "With a copy of the application (Form 2 or 17) and the list of surviving "
        "joint tenants. Fourteen days is the firm's working target; the statute "
        "says after appointment.",
    ),
    DeadlineRule(
        "creditor_publication",
        "Publish Notice to Creditors (Form 6) — optional",
        ((APPOINTMENT, relativedelta(days=14)),),
        "N.D.C.C. 30.1-19-01",
        "Once a week for three successive weeks; mail to known creditors; file the "
        "affidavit of publication. Publishing starts the three-month claims bar.",
    ),
    DeadlineRule(
        "creditor_bar",
        "Creditor claims bar date",
        ((PUBLICATION, relativedelta(months=3)),),
        "N.D.C.C. 30.1-19-03",
        "Three months after first publication. Without publication, claims may be "
        "presented for three years after death.",
    ),
    DeadlineRule(
        "claims_disallowance",
        "Disallow any claim in writing or it is deemed allowed",
        ((PUBLICATION, relativedelta(months=3, days=60)),),
        "N.D.C.C. 30.1-19-06",
        "Sixty days after the claims period ends.",
    ),
    DeadlineRule(
        "inventory",
        "File or mail the Inventory and Appraisement (Form 10)",
        ((APPOINTMENT, relativedelta(months=6)), (DEATH, relativedelta(months=9))),
        "N.D.C.C. 30.1-18-06",
        "The later of six months after appointment or nine months after death.",
    ),
    DeadlineRule(
        "tax_706",
        "Federal estate tax return (Form 706), if required",
        ((DEATH, relativedelta(months=9)),),
        "IRC 6075(a)",
        "Only if the gross estate exceeds the federal filing threshold.",
    ),
    DeadlineRule(
        "nd_estate_tax",
        "North Dakota estate tax return, if a federal return was filed",
        ((DEATH, relativedelta(months=15)),),
        "N.D.C.C. 57-37.1-07",
    ),
    DeadlineRule(
        "elective_share",
        "Surviving spouse's elective-share petition deadline",
        ((DEATH, relativedelta(months=9)), (APPOINTMENT, relativedelta(months=6))),
        "N.D.C.C. 30.1-05-01; 30.1-05-05",
        "The later of nine months after death or six months after probate of the "
        "will. Applies only where a spouse survives.",
    ),
    DeadlineRule(
        "closing_earliest",
        "Earliest date to file the closing statement (Form 15)",
        ((PUBLICATION, relativedelta(months=3)),),
        "N.D.C.C. 30.1-21-03",
        "Not before three months after first publication of the notice to "
        "creditors, and only after distribution. Without publication a small "
        "estate closes on Form 16 any time after distribution.",
    ),
    DeadlineRule(
        "pr_termination",
        "Appointment terminates one year after the closing statement",
        ((CLOSING, relativedelta(years=1)),),
        "N.D.C.C. 30.1-21-03",
        "If no proceeding involving the personal representative is pending.",
    ),
)

RULE_TYPES: tuple[str, ...] = tuple(rule.deadline_type for rule in RULES)


@dataclass(frozen=True)
class ComputedDeadline:
    deadline_type: str
    title: str
    due_date: date
    statute: str
    note: str
    anchor_used: str

    def to_json(self) -> dict:
        return {
            "deadline_type": self.deadline_type,
            "title": self.title,
            "due_date": self.due_date.isoformat(),
            "statute": self.statute,
            "note": self.note,
            "anchor_used": self.anchor_used,
        }


@dataclass(frozen=True)
class DeadlinePlan:
    deadlines: tuple[ComputedDeadline, ...]
    #: ``{anchor: [deadline_type, ...]}`` for rules that could not run yet.
    waiting_on: dict[str, list[str]]

    def to_json(self) -> dict:
        return {
            "deadlines": [item.to_json() for item in self.deadlines],
            "waiting_on": self.waiting_on,
        }


def compute(
    *,
    date_of_death: date | None,
    appointment_date: date | None = None,
    first_publication_date: date | None = None,
    closing_statement_filed_date: date | None = None,
    track: str | None = None,
) -> DeadlinePlan:
    anchors = {
        DEATH: date_of_death,
        APPOINTMENT: appointment_date,
        PUBLICATION: first_publication_date,
        CLOSING: closing_statement_filed_date,
    }
    computed: list[ComputedDeadline] = []
    waiting: dict[str, list[str]] = {}
    for rule in RULES:
        if rule.tracks is not None and track not in rule.tracks:
            continue
        candidates: list[tuple[date, str]] = []
        blocked = False
        for anchor, offset in rule.anchored:
            value = anchors.get(anchor)
            if value is None:
                waiting.setdefault(anchor, []).append(rule.deadline_type)
                blocked = True
                continue
            candidates.append((value + offset, anchor))
        if blocked or not candidates:
            continue
        due, anchor_used = max(candidates)
        computed.append(
            ComputedDeadline(
                deadline_type=rule.deadline_type,
                title=rule.title,
                due_date=due,
                statute=rule.statute,
                note=rule.note,
                anchor_used=anchor_used,
            )
        )
    computed.sort(key=lambda item: (item.due_date, item.deadline_type))
    return DeadlinePlan(deadlines=tuple(computed), waiting_on=waiting)


def plan_for_estate(estate, track: str | None = None) -> DeadlinePlan:
    return compute(
        date_of_death=getattr(estate, "date_of_death", None),
        appointment_date=getattr(estate, "appointment_date", None),
        first_publication_date=getattr(estate, "first_publication_date", None),
        closing_statement_filed_date=getattr(
            estate, "closing_statement_filed_date", None
        ),
        track=track or getattr(estate, "probate_track", None),
    )


async def sync(
    db, estate, *, mirror_tasks: bool = False, actor_id: uuid.UUID | None = None
) -> dict:
    """Upsert one ``EstateDeadline`` per rule; never touch a completed row.

    Idempotent on ``(estate_id, deadline_type)``. Re-running after an anchor
    changes moves the due date of every open row and leaves finished ones as
    the record of what was done. Rows are never deleted here.
    """

    from sqlalchemy import select

    from app.models.estate import EstateDeadline

    plan = plan_for_estate(estate)
    existing = {
        row.deadline_type: row
        for row in (
            await db.execute(
                select(EstateDeadline).where(
                    EstateDeadline.estate_id == estate.id,
                    EstateDeadline.deadline_type.in_(RULE_TYPES),
                )
            )
        ).scalars()
    }
    created: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    rows: list[EstateDeadline] = []
    for item in plan.deadlines:
        note = f"{item.statute}. {item.note}".strip()
        row = existing.get(item.deadline_type)
        if row is None:
            row = EstateDeadline(
                id=uuid.uuid4(),
                tenant_id=estate.tenant_id,
                estate_id=estate.id,
                title=item.title,
                deadline_type=item.deadline_type,
                due_date=item.due_date,
                status="pending",
                notes=note,
            )
            db.add(row)
            created.append(item.deadline_type)
        elif row.status in ("complete", "na", "cancelled"):
            unchanged.append(item.deadline_type)
        elif row.due_date != item.due_date or row.title != item.title:
            row.due_date = item.due_date
            row.title = item.title
            row.notes = note
            row.updated_at = datetime.now(timezone.utc)
            updated.append(item.deadline_type)
        else:
            unchanged.append(item.deadline_type)
        rows.append(row)
    await db.flush()
    if mirror_tasks:
        await _mirror_tasks(db, estate, rows, actor_id)
    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "waiting_on": plan.waiting_on,
        "deadlines": [item.to_json() for item in plan.deadlines],
    }


async def _mirror_tasks(db, estate, rows: Iterable, actor_id: uuid.UUID | None) -> None:
    """Keep one matter task per estate deadline so the firm's task list sees it."""

    from sqlalchemy import select

    from app.models.task import Task

    if not estate.matter_id:
        return
    for row in rows:
        ref = f"estate_deadline:{row.id}"
        task = await db.scalar(
            select(Task).where(
                Task.tenant_id == estate.tenant_id, Task.external_ref == ref
            )
        )
        if task is None:
            if row.status in ("complete", "na", "cancelled"):
                continue
            db.add(
                Task(
                    id=uuid.uuid4(),
                    tenant_id=estate.tenant_id,
                    matter_id=estate.matter_id,
                    title=row.title[:500],
                    description=row.notes,
                    task_type="deadline",
                    status="pending",
                    priority="high",
                    due_date=row.due_date,
                    assigned_to_user_id=row.assigned_to,
                    created_by_user_id=actor_id,
                    source="estate_deadline",
                    external_ref=ref,
                )
            )
        elif task.status not in ("completed", "cancelled"):
            task.due_date = row.due_date
            task.title = row.title[:500]
    await db.flush()
