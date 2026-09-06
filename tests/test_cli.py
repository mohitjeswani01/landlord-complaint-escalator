"""Tests for play.main — CLI integration tests.

Covers:
  - add subcommand (valid + invalid date)
  - list subcommand (empty + populated)
  - resolve subcommand (valid + non-existent ID)
  - remove subcommand (valid + non-existent ID)
  - check subcommand (no complaints, with escalation)
  - Default command (no subcommand → check)
  - Full escalation lifecycle: open → level 1 → level 2 → level 3 → resolved
"""

import json
import os
import sys
from datetime import date
from unittest.mock import patch

import pytest

from play.main import build_parser, cmd_add, cmd_list, cmd_resolve, cmd_remove, cmd_check


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_file(tmp_path):
    """Provide a temporary data file path."""
    return str(tmp_path / "complaints.json")


@pytest.fixture
def parser():
    return build_parser()


def _run_cmd(parser, args_list, data_file):
    """Parse args and run the command function."""
    full_args = ["--data-file", data_file] + args_list
    args = parser.parse_args(full_args)
    if args.command is None:
        args.command = "check"
        args.func = cmd_check
    args.func(args)


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

class TestCmdAdd:
    def test_add_creates_complaint(self, parser, tmp_data_file, capsys):
        _run_cmd(parser, [
            "add",
            "--description", "Leaky tap in kitchen",
            "--category", "plumbing",
            "--reported-date", "2026-09-01",
            "--deadline-days", "3",
            "--contact", "landlord@example.com",
        ], tmp_data_file)

        captured = capsys.readouterr()
        assert "Added complaint #1" in captured.out
        assert "Leaky tap in kitchen" in captured.out

        # Verify persisted
        with open(tmp_data_file) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["id"] == "1"

    def test_add_invalid_date(self, parser, tmp_data_file):
        with pytest.raises(SystemExit):
            _run_cmd(parser, [
                "add",
                "--description", "Test",
                "--category", "test",
                "--reported-date", "not-a-date",
                "--deadline-days", "3",
                "--contact", "test",
            ], tmp_data_file)

    def test_add_invalid_deadline(self, parser, tmp_data_file):
        with pytest.raises(SystemExit):
            _run_cmd(parser, [
                "add",
                "--description", "Test",
                "--category", "test",
                "--reported-date", "2026-09-01",
                "--deadline-days", "0",
                "--contact", "test",
            ], tmp_data_file)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

class TestCmdList:
    def test_list_empty(self, parser, tmp_data_file, capsys):
        _run_cmd(parser, ["list"], tmp_data_file)
        captured = capsys.readouterr()
        assert "No complaints tracked" in captured.out

    def test_list_shows_complaints(self, parser, tmp_data_file, capsys):
        # Add two complaints
        _run_cmd(parser, [
            "add", "--description", "Broken door",
            "--category", "structural",
            "--reported-date", "2026-09-01",
            "--deadline-days", "5",
            "--contact", "landlord@example.com",
        ], tmp_data_file)
        _run_cmd(parser, [
            "add", "--description", "Flickering light",
            "--category", "electrical",
            "--reported-date", "2026-09-03",
            "--deadline-days", "3",
            "--contact", "super@example.com",
        ], tmp_data_file)

        _run_cmd(parser, ["list"], tmp_data_file)
        captured = capsys.readouterr()
        assert "Broken door" in captured.out
        assert "Flickering light" in captured.out
        assert "Total: 2" in captured.out


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

class TestCmdResolve:
    def test_resolve_valid(self, parser, tmp_data_file, capsys):
        _run_cmd(parser, [
            "add", "--description", "Leaky tap",
            "--category", "plumbing",
            "--reported-date", "2026-09-01",
            "--deadline-days", "3",
            "--contact", "test",
        ], tmp_data_file)

        _run_cmd(parser, ["resolve", "--id", "1"], tmp_data_file)
        captured = capsys.readouterr()
        assert "Resolved complaint #1" in captured.out

        # Verify persisted
        with open(tmp_data_file) as f:
            data = json.load(f)
        assert data[0]["status"] == "resolved"

    def test_resolve_nonexistent(self, parser, tmp_data_file):
        with pytest.raises(SystemExit):
            _run_cmd(parser, ["resolve", "--id", "99"], tmp_data_file)


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

class TestCmdRemove:
    def test_remove_valid(self, parser, tmp_data_file, capsys):
        _run_cmd(parser, [
            "add", "--description", "Leaky tap",
            "--category", "plumbing",
            "--reported-date", "2026-09-01",
            "--deadline-days", "3",
            "--contact", "test",
        ], tmp_data_file)

        _run_cmd(parser, ["remove", "--id", "1"], tmp_data_file)
        captured = capsys.readouterr()
        assert "Removed complaint #1" in captured.out

        # Verify gone
        with open(tmp_data_file) as f:
            data = json.load(f)
        assert len(data) == 0

    def test_remove_nonexistent(self, parser, tmp_data_file):
        with pytest.raises(SystemExit):
            _run_cmd(parser, ["remove", "--id", "99"], tmp_data_file)


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

class TestCmdCheck:
    def test_check_empty(self, parser, tmp_data_file, capsys):
        _run_cmd(parser, ["check"], tmp_data_file)
        captured = capsys.readouterr()
        assert "No complaints tracked" in captured.out

    @patch("play.main.send_escalation_alert", return_value=True)
    def test_check_triggers_escalation(
        self, mock_send, parser, tmp_data_file, capsys,
    ):
        """Add an overdue complaint, run check, verify escalation."""
        _run_cmd(parser, [
            "add", "--description", "Leaky tap",
            "--category", "plumbing",
            "--reported-date", "2026-08-01",
            "--deadline-days", "3",
            "--contact", "test@example.com",
        ], tmp_data_file)

        _run_cmd(parser, ["check"], tmp_data_file)
        captured = capsys.readouterr()

        # Should have sent an alert
        assert mock_send.called
        assert "Escalated #1" in captured.out

    @patch("play.main.send_escalation_alert", return_value=True)
    def test_default_command_is_check(
        self, mock_send, parser, tmp_data_file, capsys,
    ):
        """Running with no subcommand should default to check."""
        _run_cmd(parser, [
            "add", "--description", "Test",
            "--category", "test",
            "--reported-date", "2026-08-01",
            "--deadline-days", "3",
            "--contact", "test",
        ], tmp_data_file)

        # Run with no subcommand
        _run_cmd(parser, [], tmp_data_file)
        captured = capsys.readouterr()
        assert "Escalation Check" in captured.out


# ---------------------------------------------------------------------------
# Full lifecycle test
# ---------------------------------------------------------------------------

class TestFullLifecycle:
    """End-to-end: open -> level 1 -> level 2 -> level 3 -> resolved.

    Uses direct data manipulation (writing fixture data to the store)
    instead of fragile date mocking across modules. The approach:
    set reported_date far enough in the past that the real date.today()
    triggers each escalation level, and set escalation_level to simulate
    the stored state from prior runs.
    """

    @patch("play.main.send_escalation_alert", return_value=True)
    def test_full_escalation_lifecycle(
        self, mock_send, parser, tmp_data_file, capsys,
    ):
        from play.store import load_complaints, save_complaints
        from datetime import timedelta

        today = date.today()

        # --- Phase 1: Complaint is fresh, not yet overdue ---
        # reported_date = yesterday, deadline = 3 days → not overdue
        reported = (today - timedelta(days=1)).isoformat()
        save_complaints([{
            "id": "1",
            "description": "Leaky tap in kitchen",
            "category": "plumbing",
            "reported_date": reported,
            "deadline_days": 3,
            "contact": "landlord@example.com",
            "status": "open",
            "escalation_level": 0,
            "last_escalated_at": None,
            "drafted_message_history": [],
        }], tmp_data_file)

        _run_cmd(parser, ["check"], tmp_data_file)
        complaints = load_complaints(tmp_data_file)
        assert complaints[0]["escalation_level"] == 0
        assert not mock_send.called
        assert len(complaints[0]["drafted_message_history"]) == 0

        # --- Phase 2: 1x deadline crossed → level 1 ---
        # reported_date = 4 days ago, deadline = 3 → level 1
        reported = (today - timedelta(days=4)).isoformat()
        save_complaints([{
            "id": "1",
            "description": "Leaky tap in kitchen",
            "category": "plumbing",
            "reported_date": reported,
            "deadline_days": 3,
            "contact": "landlord@example.com",
            "status": "open",
            "escalation_level": 0,
            "last_escalated_at": None,
            "drafted_message_history": [],
        }], tmp_data_file)

        mock_send.reset_mock()
        _run_cmd(parser, ["check"], tmp_data_file)
        complaints = load_complaints(tmp_data_file)
        assert complaints[0]["escalation_level"] == 1
        assert mock_send.called
        assert len(complaints[0]["drafted_message_history"]) == 1
        assert "follow up" in complaints[0][
            "drafted_message_history"
        ][0]["message"].lower()

        # --- Phase 3: Still at 1x window, already level 1 → no re-fire ---
        mock_send.reset_mock()
        _run_cmd(parser, ["check"], tmp_data_file)
        complaints = load_complaints(tmp_data_file)
        assert complaints[0]["escalation_level"] == 1
        assert not mock_send.called
        assert len(complaints[0]["drafted_message_history"]) == 1

        # --- Phase 4: 2x deadline crossed → level 2 ---
        # reported_date = 7 days ago, deadline = 3 → 2x crossed
        reported = (today - timedelta(days=7)).isoformat()
        complaints[0]["reported_date"] = reported
        save_complaints(complaints, tmp_data_file)

        mock_send.reset_mock()
        mock_send.return_value = True
        _run_cmd(parser, ["check"], tmp_data_file)
        complaints = load_complaints(tmp_data_file)
        assert complaints[0]["escalation_level"] == 2
        assert mock_send.called
        assert len(complaints[0]["drafted_message_history"]) == 2
        assert "second time" in complaints[0][
            "drafted_message_history"
        ][1]["message"].lower()

        # --- Phase 5: 3x deadline crossed → level 3 ---
        reported = (today - timedelta(days=10)).isoformat()
        complaints[0]["reported_date"] = reported
        save_complaints(complaints, tmp_data_file)

        mock_send.reset_mock()
        mock_send.return_value = True
        _run_cmd(parser, ["check"], tmp_data_file)
        complaints = load_complaints(tmp_data_file)
        assert complaints[0]["escalation_level"] == 3
        assert mock_send.called
        assert len(complaints[0]["drafted_message_history"]) == 3
        assert "FORMAL NOTICE" in complaints[0][
            "drafted_message_history"
        ][2]["message"]

        # --- Phase 6: Resolve the complaint ---
        _run_cmd(parser, ["resolve", "--id", "1"], tmp_data_file)
        complaints = load_complaints(tmp_data_file)
        assert complaints[0]["status"] == "resolved"

        # --- Phase 7: Check after resolve — should NOT escalate ---
        mock_send.reset_mock()
        # Push date even further back to confirm no escalation
        reported = (today - timedelta(days=30)).isoformat()
        complaints[0]["reported_date"] = reported
        save_complaints(complaints, tmp_data_file)

        _run_cmd(parser, ["check"], tmp_data_file)
        assert not mock_send.called
        complaints = load_complaints(tmp_data_file)
        assert complaints[0]["escalation_level"] == 3
        assert complaints[0]["status"] == "resolved"

