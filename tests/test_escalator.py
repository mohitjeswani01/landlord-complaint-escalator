"""Tests for play.escalator — the core escalation logic.

Covers:
  - Complaint not yet overdue → no escalation
  - Complaint crossing 1x deadline → level 1 fires
  - Complaint crossing 2x deadline → level 2 fires, level 1 does NOT re-fire
  - Complaint crossing 3x deadline → level 3 fires
  - Resolved complaint → never escalates regardless of elapsed time
  - Invalid reported_date → error status, no crash
  - Level calculation edge cases (exact boundary, just before boundary)
  - Message drafting produces genuinely distinct text per level
  - evaluate_all_complaints batch processing
"""

import pytest
from datetime import date

from play.escalator import (
    compute_escalation_level,
    draft_escalation_message,
    evaluate_complaint,
    evaluate_all_complaints,
    EscalationResult,
    DEFAULT_THRESHOLD_MULTIPLIERS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_complaint(
    complaint_id="c1",
    description="Leaky tap in kitchen",
    category="plumbing",
    reported_date="2026-09-01",
    deadline_days=3,
    contact="landlord@example.com",
    status="open",
    escalation_level=0,
):
    return {
        "id": complaint_id,
        "description": description,
        "category": category,
        "reported_date": reported_date,
        "deadline_days": deadline_days,
        "contact": contact,
        "status": status,
        "escalation_level": escalation_level,
    }


# ---------------------------------------------------------------------------
# compute_escalation_level
# ---------------------------------------------------------------------------

class TestComputeEscalationLevel:
    """Test the threshold computation logic."""

    def test_not_yet_overdue(self):
        """2 days elapsed, deadline is 3 → level 0."""
        assert compute_escalation_level(2, 3) == 0

    def test_exactly_at_deadline(self):
        """3 days elapsed, deadline is 3 → level 1 (1x threshold met)."""
        assert compute_escalation_level(3, 3) == 1

    def test_one_day_past_deadline(self):
        """4 days elapsed, deadline is 3 → level 1."""
        assert compute_escalation_level(4, 3) == 1

    def test_exactly_at_2x_deadline(self):
        """6 days elapsed, deadline is 3 → level 2."""
        assert compute_escalation_level(6, 3) == 2

    def test_between_2x_and_3x(self):
        """7 days elapsed, deadline is 3 → level 2 (not yet 3x=9)."""
        assert compute_escalation_level(7, 3) == 2

    def test_exactly_at_3x_deadline(self):
        """9 days elapsed, deadline is 3 → level 3."""
        assert compute_escalation_level(9, 3) == 3

    def test_well_past_3x_deadline(self):
        """15 days elapsed, deadline is 3 → level 3 (max with default)."""
        assert compute_escalation_level(15, 3) == 3

    def test_zero_days_elapsed(self):
        """0 days → level 0."""
        assert compute_escalation_level(0, 3) == 0

    def test_zero_deadline_days_guarded(self):
        """deadline_days=0 should be guarded to 1."""
        assert compute_escalation_level(1, 0) == 1

    def test_custom_multipliers(self):
        """Custom multipliers [1, 5, 10] with deadline=2."""
        mults = [1, 5, 10]
        assert compute_escalation_level(1, 2, mults) == 0   # < 1x2=2
        assert compute_escalation_level(2, 2, mults) == 1   # = 1x2
        assert compute_escalation_level(9, 2, mults) == 1   # < 5x2=10
        assert compute_escalation_level(10, 2, mults) == 2  # = 5x2
        assert compute_escalation_level(20, 2, mults) == 3  # = 10x2

    def test_negative_days(self):
        """Negative days elapsed (future date) → level 0."""
        assert compute_escalation_level(-5, 3) == 0


# ---------------------------------------------------------------------------
# draft_escalation_message
# ---------------------------------------------------------------------------

class TestDraftEscalationMessage:
    """Test that each level produces distinct, meaningful message text."""

    def _draft(self, level):
        return draft_escalation_message(
            level=level,
            description="Leaky tap in kitchen",
            category="plumbing",
            contact="landlord@example.com",
            reported_date="2026-09-01",
            days_since_reported=6,
            deadline_days=3,
        )

    def test_level_0_returns_empty(self):
        """Level 0 → no message."""
        assert self._draft(0) == ""

    def test_level_1_polite_tone(self):
        msg = self._draft(1)
        assert "Hi," in msg
        assert "follow up" in msg.lower()
        assert "Leaky tap in kitchen" in msg
        assert "2026-09-01" in msg
        assert "6 day(s)" in msg
        assert "Best regards" in msg
        # Should NOT contain formal/legal language
        assert "FORMAL NOTICE" not in msg
        assert "tenant authority" not in msg.lower()

    def test_level_2_firm_tone(self):
        msg = self._draft(2)
        assert "Dear Management" in msg
        assert "second time" in msg.lower()
        assert "Leaky tap in kitchen" in msg
        assert "2026-09-01" in msg
        assert "6 days" in msg
        assert "priority" in msg.lower()
        assert "48 hours" in msg
        assert "FORMAL NOTICE" not in msg

    def test_level_3_formal_tone(self):
        msg = self._draft(3)
        assert "FORMAL NOTICE" in msg
        assert "Dear Management" in msg
        assert "Leaky tap in kitchen" in msg
        assert "2026-09-01" in msg
        assert "tenant authority" in msg.lower() or "housing ombudsman" in msg.lower()
        assert "legal advice" in msg.lower()
        assert "Yours sincerely" in msg

    def test_all_levels_are_distinct(self):
        """Each level must produce substantially different text."""
        msg1 = self._draft(1)
        msg2 = self._draft(2)
        msg3 = self._draft(3)

        assert msg1 != msg2
        assert msg2 != msg3
        assert msg1 != msg3

        # Different opening lines
        first_line_1 = msg1.split("\n")[0]
        first_line_2 = msg2.split("\n")[0]
        assert first_line_1 != first_line_2

    def test_level_4_uses_level_3_template(self):
        """Level 4+ should use the level-3 template with updated counts."""
        msg4 = self._draft(4)
        assert "FORMAL NOTICE" in msg4
        assert "Prior escalation attempts: 3" in msg4

    def test_category_formatting(self):
        """Category with underscores should be title-cased."""
        msg = draft_escalation_message(
            level=1,
            description="Test",
            category="water_heater",
            contact="test",
            reported_date="2026-09-01",
            days_since_reported=3,
            deadline_days=3,
        )
        assert "Water Heater" in msg


# ---------------------------------------------------------------------------
# evaluate_complaint
# ---------------------------------------------------------------------------

class TestEvaluateComplaint:
    """Test end-to-end evaluation of a single complaint."""

    def test_not_yet_overdue(self):
        """Complaint reported recently with 3-day deadline → no escalation."""
        complaint = _make_complaint(reported_date="2026-09-06", deadline_days=3)
        result = evaluate_complaint(complaint, today=date(2026, 9, 7))

        assert result.status == "open"
        assert result.escalation_level == 0
        assert result.days_overdue == 0
        assert result.drafted_message is None
        assert result.needs_notification is False

    def test_just_crossing_deadline_level_1(self):
        """3 days elapsed, deadline=3 → level 1 fires."""
        complaint = _make_complaint(
            reported_date="2026-09-01", deadline_days=3, escalation_level=0,
        )
        result = evaluate_complaint(complaint, today=date(2026, 9, 4))

        assert result.status == "overdue"
        assert result.escalation_level == 1
        assert result.previous_level == 0
        assert result.needs_notification is True
        assert result.drafted_message is not None
        assert "follow up" in result.drafted_message.lower()

    def test_level_1_does_not_refire(self):
        """Already at level 1, still in level-1 window → no notification."""
        complaint = _make_complaint(
            reported_date="2026-09-01", deadline_days=3, escalation_level=1,
        )
        result = evaluate_complaint(complaint, today=date(2026, 9, 5))

        assert result.escalation_level == 1
        assert result.previous_level == 1
        assert result.needs_notification is False
        assert result.drafted_message is None

    def test_crossing_2x_deadline_level_2(self):
        """6 days elapsed (2x3), previous level=1 → level 2 fires."""
        complaint = _make_complaint(
            reported_date="2026-09-01", deadline_days=3, escalation_level=1,
        )
        result = evaluate_complaint(complaint, today=date(2026, 9, 7))

        assert result.escalation_level == 2
        assert result.previous_level == 1
        assert result.needs_notification is True
        assert result.drafted_message is not None
        assert "second time" in result.drafted_message.lower()

    def test_crossing_3x_deadline_level_3(self):
        """9 days elapsed (3x3), previous level=2 → level 3 fires."""
        complaint = _make_complaint(
            reported_date="2026-09-01", deadline_days=3, escalation_level=2,
        )
        result = evaluate_complaint(complaint, today=date(2026, 9, 10))

        assert result.escalation_level == 3
        assert result.previous_level == 2
        assert result.needs_notification is True
        assert result.drafted_message is not None
        assert "FORMAL NOTICE" in result.drafted_message

    def test_resolved_complaint_never_escalates(self):
        """Resolved complaint should NEVER escalate even well past deadline."""
        complaint = _make_complaint(
            reported_date="2026-09-01",
            deadline_days=3,
            status="resolved",
            escalation_level=1,
        )
        result = evaluate_complaint(complaint, today=date(2026, 9, 20))

        assert result.status == "resolved"
        assert result.escalation_level == 1  # stays at stored level
        assert result.needs_notification is False
        assert result.drafted_message is None

    def test_invalid_reported_date(self):
        """Invalid date → error status, no crash."""
        complaint = _make_complaint(reported_date="not-a-date")
        result = evaluate_complaint(complaint, today=date(2026, 9, 6))

        assert result.status == "error"
        assert result.needs_notification is False
        assert result.drafted_message is None

    def test_empty_reported_date(self):
        """Empty date → error status, no crash."""
        complaint = _make_complaint(reported_date="")
        result = evaluate_complaint(complaint, today=date(2026, 9, 6))

        assert result.status == "error"

    def test_days_overdue_calculation(self):
        """Verify days_overdue is calculated correctly."""
        complaint = _make_complaint(
            reported_date="2026-09-01", deadline_days=3,
        )
        # Sep 1 + 3 days = Sep 4 deadline. Today Sep 7 → 3 days overdue
        result = evaluate_complaint(complaint, today=date(2026, 9, 7))

        assert result.days_overdue == 3
        assert result.days_since_reported == 6

    def test_days_overdue_zero_when_not_overdue(self):
        """Before deadline → days_overdue should be 0."""
        complaint = _make_complaint(
            reported_date="2026-09-06", deadline_days=5,
        )
        result = evaluate_complaint(complaint, today=date(2026, 9, 7))

        assert result.days_overdue == 0

    def test_missing_contact_handled_gracefully(self):
        """Missing contact info should not crash."""
        complaint = _make_complaint(contact="")
        result = evaluate_complaint(complaint, today=date(2026, 9, 10))

        assert result.contact == ""
        assert result.escalation_level > 0  # should still escalate

    def test_skips_already_matched_level(self):
        """If already at level 2 and still in level-2 window → no notif."""
        complaint = _make_complaint(
            reported_date="2026-09-01", deadline_days=3, escalation_level=2,
        )
        result = evaluate_complaint(complaint, today=date(2026, 9, 8))

        assert result.escalation_level == 2
        assert result.needs_notification is False

    def test_custom_threshold_multipliers(self):
        """Custom multipliers should be respected."""
        complaint = _make_complaint(
            reported_date="2026-09-01", deadline_days=2, escalation_level=0,
        )
        # 10 days elapsed, multipliers [5, 10, 15]:
        # 5x2=10 → level 1, 10x2=20 → not reached
        result = evaluate_complaint(
            complaint,
            today=date(2026, 9, 11),
            threshold_multipliers=[5, 10, 15],
        )

        assert result.escalation_level == 1
        assert result.needs_notification is True


# ---------------------------------------------------------------------------
# evaluate_all_complaints
# ---------------------------------------------------------------------------

class TestEvaluateAllComplaints:
    """Test batch processing of multiple complaints."""

    def test_mixed_statuses(self):
        """Process a mix of open, resolved, and overdue complaints."""
        complaints = [
            _make_complaint(
                complaint_id="c1",
                reported_date="2026-09-06",
                deadline_days=5,
            ),  # not yet due
            _make_complaint(
                complaint_id="c2",
                reported_date="2026-09-01",
                deadline_days=3,
                escalation_level=0,
            ),  # overdue
            _make_complaint(
                complaint_id="c3",
                status="resolved",
                escalation_level=1,
            ),  # resolved
        ]

        results = evaluate_all_complaints(complaints, today=date(2026, 9, 7))

        assert len(results) == 3
        assert results[0].status == "open"
        assert results[0].needs_notification is False
        assert results[1].status == "overdue"
        assert results[1].needs_notification is True
        assert results[2].status == "resolved"
        assert results[2].needs_notification is False

    def test_empty_list(self):
        """Empty complaint list → empty results."""
        results = evaluate_all_complaints([], today=date(2026, 9, 7))
        assert results == []
