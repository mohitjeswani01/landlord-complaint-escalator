"""Tests for play.store — complaint persistence and CRUD operations.

Covers:
  - Add complaint, verify fields and auto-incrementing ID
  - Load/save round-trip
  - Resolve complaint (sets status, keeps record)
  - Remove complaint (deletes record entirely)
  - Resolve/remove non-existent ID → ValueError with clear message
  - Resolve already-resolved complaint → idempotent
  - Corrupted file recovery (backup + fresh start)
  - Empty file recovery
  - Escalation update + message history tracking
  - ID generation with gaps
"""

import json
import os
import tempfile

import pytest

from play.store import (
    load_complaints,
    save_complaints,
    add_complaint,
    find_complaint_by_id,
    resolve_complaint,
    remove_complaint,
    update_escalation,
    _next_id,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_file(tmp_path):
    """Provide a temporary complaints file path."""
    return str(tmp_path / "complaints.json")


@pytest.fixture
def populated_file(tmp_file):
    """Create a file with 3 complaints already in it."""
    complaints = [
        {
            "id": "1",
            "description": "Leaky tap in kitchen",
            "category": "plumbing",
            "reported_date": "2026-09-01",
            "deadline_days": 3,
            "contact": "landlord@example.com",
            "status": "open",
            "escalation_level": 0,
            "last_escalated_at": None,
            "drafted_message_history": [],
        },
        {
            "id": "2",
            "description": "Broken window latch",
            "category": "structural",
            "reported_date": "2026-08-20",
            "deadline_days": 5,
            "contact": "building-group@example.com",
            "status": "open",
            "escalation_level": 1,
            "last_escalated_at": "2026-08-26T12:00:00+00:00",
            "drafted_message_history": [
                {
                    "level": 1,
                    "message": "Hi, following up...",
                    "sent_at": "2026-08-26T12:00:00+00:00",
                },
            ],
        },
        {
            "id": "3",
            "description": "Flickering hallway light",
            "category": "electrical",
            "reported_date": "2026-09-03",
            "deadline_days": 7,
            "contact": "landlord@example.com",
            "status": "resolved",
            "escalation_level": 0,
            "last_escalated_at": None,
            "drafted_message_history": [],
        },
    ]
    save_complaints(complaints, tmp_file)
    return tmp_file


# ---------------------------------------------------------------------------
# load / save basics
# ---------------------------------------------------------------------------

class TestLoadSave:
    """Test low-level load/save operations."""

    def test_load_nonexistent_file(self, tmp_path):
        """Loading from a path that doesn't exist returns empty list."""
        result = load_complaints(str(tmp_path / "does_not_exist.json"))
        assert result == []

    def test_load_empty_file(self, tmp_file):
        """Loading from an empty file returns empty list."""
        open(tmp_file, "w").close()  # create empty file
        result = load_complaints(tmp_file)
        assert result == []

    def test_round_trip(self, tmp_file):
        """Save then load returns the same data."""
        data = [{"id": "1", "description": "test"}]
        save_complaints(data, tmp_file)
        loaded = load_complaints(tmp_file)
        assert loaded == data

    def test_corrupted_file_recovery(self, tmp_file):
        """Corrupted JSON triggers backup and returns empty list."""
        with open(tmp_file, "w") as f:
            f.write("{{{INVALID JSON")

        result = load_complaints(tmp_file)
        assert result == []

        # Verify backup was created
        parent = os.path.dirname(tmp_file)
        backups = [
            f for f in os.listdir(parent)
            if "corrupted" in f
        ]
        assert len(backups) == 1

    def test_wrong_type_recovery(self, tmp_file):
        """JSON that's valid but wrong type (dict instead of list)."""
        with open(tmp_file, "w") as f:
            json.dump({"wrong": "type"}, f)

        result = load_complaints(tmp_file)
        assert result == []

    def test_atomic_write_no_partial(self, tmp_file):
        """Verify the temp file is cleaned up after a successful save."""
        save_complaints([{"id": "1"}], tmp_file)
        tmp_path = tmp_file.replace(".json", ".tmp")
        assert not os.path.exists(tmp_path)


# ---------------------------------------------------------------------------
# add_complaint
# ---------------------------------------------------------------------------

class TestAddComplaint:
    """Test adding new complaints."""

    def test_add_first_complaint(self, tmp_file):
        """First complaint gets ID '1'."""
        record = add_complaint(
            description="Leaky tap",
            category="plumbing",
            reported_date="2026-09-01",
            deadline_days=3,
            contact="landlord@example.com",
            file_path=tmp_file,
        )

        assert record["id"] == "1"
        assert record["description"] == "Leaky tap"
        assert record["category"] == "plumbing"
        assert record["status"] == "open"
        assert record["escalation_level"] == 0
        assert record["last_escalated_at"] is None
        assert record["drafted_message_history"] == []

    def test_add_increments_id(self, tmp_file):
        """Second complaint gets ID '2'."""
        add_complaint("First", "cat", "2026-09-01", 3, "x", file_path=tmp_file)
        record = add_complaint(
            "Second", "cat", "2026-09-02", 5, "y", file_path=tmp_file,
        )
        assert record["id"] == "2"

    def test_add_persists_to_disk(self, tmp_file):
        """Adding a complaint actually writes to disk."""
        add_complaint("Test", "cat", "2026-09-01", 3, "x", file_path=tmp_file)
        loaded = load_complaints(tmp_file)
        assert len(loaded) == 1
        assert loaded[0]["description"] == "Test"

    def test_add_strips_whitespace(self, tmp_file):
        """Input strings are trimmed."""
        record = add_complaint(
            "  Leaky tap  ", "  Plumbing  ", "2026-09-01", 3,
            "  landlord@example.com  ", file_path=tmp_file,
        )
        assert record["description"] == "Leaky tap"
        assert record["category"] == "plumbing"
        assert record["contact"] == "landlord@example.com"


# ---------------------------------------------------------------------------
# find_complaint_by_id
# ---------------------------------------------------------------------------

class TestFindComplaintById:
    """Test ID lookup."""

    def test_find_existing(self, populated_file):
        result = find_complaint_by_id("2", populated_file)
        assert result is not None
        assert result["description"] == "Broken window latch"

    def test_find_nonexistent(self, populated_file):
        result = find_complaint_by_id("99", populated_file)
        assert result is None

    def test_find_handles_string_int_mismatch(self, populated_file):
        """ID stored as string '1' should match lookup with int-like '1'."""
        result = find_complaint_by_id(1, populated_file)
        assert result is not None


# ---------------------------------------------------------------------------
# resolve_complaint
# ---------------------------------------------------------------------------

class TestResolveComplaint:
    """Test resolving complaints."""

    def test_resolve_sets_status(self, populated_file):
        """Resolve changes status to 'resolved'."""
        result = resolve_complaint("1", populated_file)
        assert result["status"] == "resolved"

        # Verify it persisted
        loaded = find_complaint_by_id("1", populated_file)
        assert loaded["status"] == "resolved"

    def test_resolve_keeps_record(self, populated_file):
        """Resolved complaint is NOT deleted — still in the list."""
        resolve_complaint("1", populated_file)
        all_complaints = load_complaints(populated_file)
        assert len(all_complaints) == 3  # still 3, not 2

    def test_resolve_already_resolved_is_idempotent(self, populated_file):
        """Resolving an already-resolved complaint doesn't crash."""
        result = resolve_complaint("3", populated_file)
        assert result["status"] == "resolved"

    def test_resolve_nonexistent_raises_valueerror(self, populated_file):
        """Resolving a non-existent ID raises ValueError with message."""
        with pytest.raises(ValueError, match="not found"):
            resolve_complaint("99", populated_file)

    def test_resolve_with_clear_error_message(self, populated_file):
        """Error message should suggest using 'list'."""
        with pytest.raises(ValueError, match="list"):
            resolve_complaint("999", populated_file)


# ---------------------------------------------------------------------------
# remove_complaint
# ---------------------------------------------------------------------------

class TestRemoveComplaint:
    """Test removing complaints."""

    def test_remove_deletes_record(self, populated_file):
        """Remove actually removes the complaint from the list."""
        removed = remove_complaint("1", populated_file)
        assert removed["description"] == "Leaky tap in kitchen"

        all_complaints = load_complaints(populated_file)
        assert len(all_complaints) == 2
        assert find_complaint_by_id("1", populated_file) is None

    def test_remove_nonexistent_raises_valueerror(self, populated_file):
        """Removing a non-existent ID raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            remove_complaint("99", populated_file)

    def test_remove_returns_removed_record(self, populated_file):
        """The removed record is returned for confirmation."""
        removed = remove_complaint("2", populated_file)
        assert removed["id"] == "2"
        assert removed["description"] == "Broken window latch"


# ---------------------------------------------------------------------------
# update_escalation
# ---------------------------------------------------------------------------

class TestUpdateEscalation:
    """Test escalation state updates."""

    def test_update_sets_level(self, populated_file):
        """Update changes escalation_level."""
        result = update_escalation(
            "1", new_level=1, drafted_message="Follow up...",
            file_path=populated_file,
        )
        assert result["escalation_level"] == 1

    def test_update_records_history(self, populated_file):
        """Update appends to drafted_message_history."""
        update_escalation(
            "1", new_level=1, drafted_message="Level 1 msg",
            file_path=populated_file,
        )
        update_escalation(
            "1", new_level=2, drafted_message="Level 2 msg",
            file_path=populated_file,
        )

        complaint = find_complaint_by_id("1", populated_file)
        history = complaint["drafted_message_history"]
        assert len(history) == 2
        assert history[0]["level"] == 1
        assert history[0]["message"] == "Level 1 msg"
        assert history[1]["level"] == 2
        assert history[1]["message"] == "Level 2 msg"

    def test_update_sets_last_escalated_at(self, populated_file):
        """Update records the timestamp."""
        result = update_escalation(
            "1", new_level=1, drafted_message="msg",
            file_path=populated_file,
        )
        assert result["last_escalated_at"] is not None

    def test_update_nonexistent_returns_none(self, populated_file):
        """Updating a non-existent complaint returns None."""
        result = update_escalation(
            "99", new_level=1, drafted_message="msg",
            file_path=populated_file,
        )
        assert result is None

    def test_update_persists(self, populated_file):
        """Escalation update is persisted to disk."""
        update_escalation(
            "1", new_level=2, drafted_message="Firm follow up",
            file_path=populated_file,
        )
        loaded = find_complaint_by_id("1", populated_file)
        assert loaded["escalation_level"] == 2


# ---------------------------------------------------------------------------
# _next_id edge cases
# ---------------------------------------------------------------------------

class TestNextId:
    """Test ID generation."""

    def test_empty_list(self):
        assert _next_id([]) == "1"

    def test_sequential(self):
        complaints = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        assert _next_id(complaints) == "4"

    def test_with_gaps(self):
        """IDs with gaps: [1, 3, 5] → next is 6."""
        complaints = [{"id": "1"}, {"id": "3"}, {"id": "5"}]
        assert _next_id(complaints) == "6"

    def test_with_non_numeric_ids_skipped(self):
        """Non-numeric IDs are gracefully skipped."""
        complaints = [{"id": "abc"}, {"id": "2"}]
        assert _next_id(complaints) == "3"
