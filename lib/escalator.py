"""Complaint Escalation Engine — the core differentiator.

Given a complaint record, calculates whether it is overdue and at which
escalation level, then drafts a GENUINELY ESCALATING message the tenant
can copy-paste and send to their landlord / building management.

Escalation thresholds (multiples of the complaint's deadline_days):
  Level 1 — 1x deadline  (polite reminder)
  Level 2 — 2x deadline  (firm follow-up referencing elapsed time)
  Level 3 — 3x deadline  (formal notice referencing tenant rights)

Thresholds are configurable via the threshold_multipliers parameter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Default threshold multipliers: level N fires when
# days_since_reported >= multiplier[N-1] * deadline_days
DEFAULT_THRESHOLD_MULTIPLIERS: list[int] = [1, 2, 3]


@dataclass
class EscalationResult:
    """Structured result for a single complaint's escalation check."""

    complaint_id: str
    description: str
    category: str
    contact: str
    reported_date: str
    deadline_days: int
    days_since_reported: int
    days_overdue: int  # 0 if not yet overdue
    escalation_level: int  # 0 = not yet escalated
    previous_level: int  # what level was stored before this check
    drafted_message: Optional[str]  # None if no new escalation needed
    status: str  # "open", "resolved", "overdue"
    needs_notification: bool  # True only when level increased


def compute_escalation_level(
    days_since_reported: int,
    deadline_days: int,
    threshold_multipliers: Optional[list[int]] = None,
) -> int:
    """Determine the escalation level based on elapsed time.

    Returns 0 if the complaint is not yet overdue.
    """
    if deadline_days <= 0:
        deadline_days = 1  # guard against zero/negative

    multipliers = threshold_multipliers or DEFAULT_THRESHOLD_MULTIPLIERS

    level = 0
    for mult in sorted(multipliers):
        if days_since_reported >= mult * deadline_days:
            level += 1
        else:
            break

    return level


def draft_escalation_message(
    level: int,
    description: str,
    category: str,
    contact: str,
    reported_date: str,
    days_since_reported: int,
    deadline_days: int,
) -> str:
    """Draft an escalation message with genuinely different tone per level.

    Each level produces distinct wording — NOT just the same template with
    an updated day count.
    """
    category_display = category.replace("_", " ").title() if category else "General"

    if level <= 0:
        return ""

    if level == 1:
        return _draft_level_1(
            description, category_display, contact, reported_date,
            days_since_reported, deadline_days,
        )
    elif level == 2:
        return _draft_level_2(
            description, category_display, contact, reported_date,
            days_since_reported, deadline_days,
        )
    else:
        # Level 3+ — most formal
        return _draft_level_3(
            description, category_display, contact, reported_date,
            days_since_reported, deadline_days, level,
        )


def _draft_level_1(
    description: str,
    category_display: str,
    contact: str,
    reported_date: str,
    days_since_reported: int,
    deadline_days: int,
) -> str:
    """Level 1 — Polite reminder, friendly tone."""
    return (
        "Hi,\n"
        "\n"
        "I hope this message finds you well. I wanted to follow up on a "
        f"maintenance issue I reported on {reported_date}.\n"
        "\n"
        f"Issue: {description}\n"
        f"Category: {category_display}\n"
        "\n"
        f"It has been {days_since_reported} day(s) since I submitted this "
        "request, and the issue is still unresolved. I understand things "
        "can get busy, but I would really appreciate it if this could be "
        "looked into at your earliest convenience.\n"
        "\n"
        "Could you please provide an update on when I might expect a "
        "resolution? I'm happy to coordinate access to the unit or provide "
        "any additional details that would help.\n"
        "\n"
        "Thank you for your attention to this matter.\n"
        "\n"
        "Best regards"
    )


def _draft_level_2(
    description: str,
    category_display: str,
    contact: str,
    reported_date: str,
    days_since_reported: int,
    deadline_days: int,
) -> str:
    """Level 2 — Firmer follow-up, references prior report and elapsed time."""
    return (
        "Dear Management,\n"
        "\n"
        "I am writing to follow up — for the second time — regarding a "
        "maintenance issue that remains unresolved.\n"
        "\n"
        f"Issue: {description}\n"
        f"Category: {category_display}\n"
        f"Originally reported: {reported_date}\n"
        f"Days since report: {days_since_reported}\n"
        "\n"
        f"This has now been outstanding for {days_since_reported} days since "
        f"my original report on {reported_date}. I previously reached out "
        f"after the initial {deadline_days}-day window passed and have not "
        "received a satisfactory response or resolution.\n"
        "\n"
        "As a tenant, I expect reported maintenance issues to be addressed "
        "within a reasonable timeframe. The continued delay is causing "
        "inconvenience and I would like to request that this matter be "
        "treated as a priority.\n"
        "\n"
        "Please confirm within the next 48 hours what concrete steps will "
        "be taken to resolve this issue, including an expected completion "
        "date.\n"
        "\n"
        "I look forward to your prompt response.\n"
        "\n"
        "Regards"
    )


def _draft_level_3(
    description: str,
    category_display: str,
    contact: str,
    reported_date: str,
    days_since_reported: int,
    deadline_days: int,
    level: int,
) -> str:
    """Level 3+ — Formal notice, references tenant rights, suggests next steps."""
    return (
        "Dear Management,\n"
        "\n"
        "RE: FORMAL NOTICE — Unresolved Maintenance Issue "
        f"(Reported {reported_date})\n"
        "\n"
        "I am writing to formally notify you that the following maintenance "
        f"issue has remained unresolved for {days_since_reported} days, "
        "despite multiple prior communications:\n"
        "\n"
        f"Issue: {description}\n"
        f"Category: {category_display}\n"
        f"Date originally reported: {reported_date}\n"
        f"Days elapsed: {days_since_reported}\n"
        f"Prior escalation attempts: {level - 1}\n"
        "\n"
        "As per my tenancy agreement and applicable local tenant protection "
        "regulations, landlords and property managers are generally expected "
        "to carry out necessary repairs within a reasonable period after "
        "being notified by the tenant. I believe that "
        f"{days_since_reported} days significantly exceeds what would be "
        "considered a reasonable timeframe, and I encourage you to review "
        "the relevant obligations.\n"
        "\n"
        "I am requesting that this issue be resolved within 7 calendar days "
        "of this notice. If I do not receive confirmation of a scheduled "
        "repair within this period, I intend to explore the following "
        "options:\n"
        "\n"
        "  1. Filing a formal written complaint with the relevant local "
        "tenant authority or housing ombudsman.\n"
        "  2. Seeking independent legal advice regarding my rights as a "
        "tenant.\n"
        "  3. Documenting all correspondence and the condition of the "
        "property for any future proceedings.\n"
        "\n"
        "I want to resolve this amicably and would prefer not to pursue "
        "these steps. However, the extended period without resolution "
        "leaves me with limited alternatives.\n"
        "\n"
        "Please treat this as a matter of urgency.\n"
        "\n"
        "Yours sincerely"
    )


def evaluate_complaint(
    complaint: dict,
    today: Optional[date] = None,
    threshold_multipliers: Optional[list[int]] = None,
) -> EscalationResult:
    """Evaluate a single complaint and determine if it needs escalation.

    Args:
        complaint: A complaint record dict from the store.
        today: Override for current date (for testing).
        threshold_multipliers: Override threshold multipliers.

    Returns:
        An EscalationResult with escalation details and drafted message.
    """
    today = today or date.today()

    complaint_id = complaint.get("id", "unknown")
    description = complaint.get("description", "No description")
    category = complaint.get("category", "general")
    contact = complaint.get("contact", "")
    reported_date_str = complaint.get("reported_date", "")
    deadline_days = int(complaint.get("deadline_days", 7))
    status = complaint.get("status", "open")
    previous_level = int(complaint.get("escalation_level", 0))

    # Parse reported_date
    try:
        reported_date = date.fromisoformat(reported_date_str)
    except (ValueError, TypeError):
        logger.error(
            "Complaint %s has invalid reported_date: %s",
            complaint_id, reported_date_str,
        )
        return EscalationResult(
            complaint_id=complaint_id,
            description=description,
            category=category,
            contact=contact,
            reported_date=reported_date_str,
            deadline_days=deadline_days,
            days_since_reported=0,
            days_overdue=0,
            escalation_level=previous_level,
            previous_level=previous_level,
            drafted_message=None,
            status="error",
            needs_notification=False,
        )

    days_since_reported = (today - reported_date).days
    deadline_date = reported_date + timedelta(days=deadline_days)
    days_overdue = max(0, (today - deadline_date).days)

    # Resolved complaints never escalate
    if status == "resolved":
        return EscalationResult(
            complaint_id=complaint_id,
            description=description,
            category=category,
            contact=contact,
            reported_date=reported_date_str,
            deadline_days=deadline_days,
            days_since_reported=days_since_reported,
            days_overdue=0,
            escalation_level=previous_level,
            previous_level=previous_level,
            drafted_message=None,
            status="resolved",
            needs_notification=False,
        )

    # Compute current level
    current_level = compute_escalation_level(
        days_since_reported, deadline_days, threshold_multipliers,
    )

    # Determine effective status
    if current_level > 0:
        effective_status = "overdue"
    else:
        effective_status = "open"

    # Only draft + notify if level actually increased
    needs_notification = current_level > previous_level
    drafted_message = None

    if needs_notification:
        drafted_message = draft_escalation_message(
            level=current_level,
            description=description,
            category=category,
            contact=contact,
            reported_date=reported_date_str,
            days_since_reported=days_since_reported,
            deadline_days=deadline_days,
        )

    return EscalationResult(
        complaint_id=complaint_id,
        description=description,
        category=category,
        contact=contact,
        reported_date=reported_date_str,
        deadline_days=deadline_days,
        days_since_reported=days_since_reported,
        days_overdue=days_overdue,
        escalation_level=current_level,
        previous_level=previous_level,
        drafted_message=drafted_message,
        status=effective_status,
        needs_notification=needs_notification,
    )


def evaluate_all_complaints(
    complaints: list[dict],
    today: Optional[date] = None,
    threshold_multipliers: Optional[list[int]] = None,
) -> list[EscalationResult]:
    """Evaluate all complaints and return escalation results.

    Only open complaints are checked for escalation — resolved ones
    are returned with their current state unchanged.
    """
    results = []
    for complaint in complaints:
        result = evaluate_complaint(complaint, today, threshold_multipliers)
        results.append(result)
    return results
