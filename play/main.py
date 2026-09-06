"""CLI entry point for the Landlord/Maintenance Complaint Escalator.

Subcommands:
  add      — Log a new maintenance complaint
  list     — Show all complaints with status and escalation info
  resolve  — Mark a complaint as resolved (stops future escalation)
  remove   — Delete a complaint entirely
  check    — Run escalation check + send Telegram alerts (default)

Usage:
  python3 -m play.main add --description "Leaky tap" --category plumbing \\
      --reported-date 2026-09-01 --deadline-days 3 --contact "landlord@example.com"
  python3 -m play.main list
  python3 -m play.main resolve --id 1
  python3 -m play.main remove --id 1
  python3 -m play.main check
  python3 -m play.main          # same as 'check'
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from play.escalator import evaluate_all_complaints
from play.notifier import send_escalation_alert
from play.store import (
    DEFAULT_COMPLAINTS_FILE,
    add_complaint,
    load_complaints,
    remove_complaint,
    resolve_complaint,
    update_escalation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Date parsing helper
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> date:
    """Parse a YYYY-MM-DD date string, raising ValueError on failure."""
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"Invalid date '{date_str}'. Expected format: YYYY-MM-DD"
        ) from e


# ---------------------------------------------------------------------------
# Table rendering (proactively avoids emoji-width + buffering issues)
# ---------------------------------------------------------------------------

# Use simple ASCII markers instead of emoji in the table to avoid
# width-padding issues in monospace terminals.
STATUS_MARKERS = {
    "open": "OPEN",
    "resolved": "DONE",
    "overdue": "OVERDUE",
    "error": "ERROR",
}


def _print_table(complaints: list[dict], today: date) -> None:
    """Print a clean, aligned table of complaints.

    Uses fixed-width columns and ASCII status markers to avoid
    emoji-width rendering bugs.
    """
    if not complaints:
        print("  (no complaints tracked)", flush=True)
        return

    # Column widths
    w_id = 4
    w_desc = 35
    w_cat = 12
    w_status = 8
    w_days = 6
    w_level = 7

    # Header
    header = (
        f"  {'ID':<{w_id}}  "
        f"{'Description':<{w_desc}}  "
        f"{'Category':<{w_cat}}  "
        f"{'Status':<{w_status}}  "
        f"{'Days':<{w_days}}  "
        f"{'Level':<{w_level}}"
    )
    print(header, flush=True)
    print("  " + "-" * (len(header) - 2), flush=True)

    for c in complaints:
        cid = str(c.get("id", "?"))
        desc = c.get("description", "?")
        if len(desc) > w_desc:
            desc = desc[: w_desc - 3] + "..."
        cat = c.get("category", "?").replace("_", " ").title()
        if len(cat) > w_cat:
            cat = cat[: w_cat - 3] + "..."
        status = c.get("status", "open")

        # Calculate days since reported
        try:
            reported = date.fromisoformat(c.get("reported_date", ""))
            days_since = (today - reported).days
        except (ValueError, TypeError):
            days_since = "?"

        level = c.get("escalation_level", 0)
        status_display = STATUS_MARKERS.get(status, status.upper())

        # Mark overdue open complaints
        if status == "open" and isinstance(days_since, int):
            deadline = int(c.get("deadline_days", 7))
            if days_since >= deadline:
                status_display = "OVERDUE"

        row = (
            f"  {cid:<{w_id}}  "
            f"{desc:<{w_desc}}  "
            f"{cat:<{w_cat}}  "
            f"{status_display:<{w_status}}  "
            f"{str(days_since):<{w_days}}  "
            f"{str(level):<{w_level}}"
        )
        print(row, flush=True)

    print(flush=True)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_add(args):
    """Handle 'add' subcommand."""
    # Validate date
    try:
        _parse_date(args.reported_date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)

    if args.deadline_days < 1:
        print(
            "Error: --deadline-days must be at least 1.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    record = add_complaint(
        description=args.description,
        category=args.category,
        reported_date=args.reported_date,
        deadline_days=args.deadline_days,
        contact=args.contact,
        file_path=args.data_file,
    )

    print(
        f"Added complaint #{record['id']}: "
        f"'{record['description']}' ({record['category']})",
        flush=True,
    )
    print(
        f"  Reported: {record['reported_date']}  |  "
        f"Deadline: {record['deadline_days']} days  |  "
        f"Contact: {record['contact']}",
        flush=True,
    )


def cmd_list(args):
    """Handle 'list' subcommand."""
    complaints = load_complaints(args.data_file)

    if not complaints:
        print(
            "No complaints tracked yet. Use 'add' to log a complaint.",
            flush=True,
        )
        return

    today = date.today()
    print(f"\nComplaints — {today.isoformat()}\n", flush=True)
    _print_table(complaints, today)

    # Summary counts
    open_count = sum(1 for c in complaints if c.get("status") == "open")
    resolved_count = sum(
        1 for c in complaints if c.get("status") == "resolved"
    )
    print(
        f"  Total: {len(complaints)}  |  "
        f"Open: {open_count}  |  "
        f"Resolved: {resolved_count}",
        flush=True,
    )
    print(flush=True)


def cmd_resolve(args):
    """Handle 'resolve' subcommand."""
    try:
        result = resolve_complaint(args.id, file_path=args.data_file)
        print(
            f"Resolved complaint #{result['id']}: "
            f"'{result['description']}'",
            flush=True,
        )
        print(
            "  Future escalations for this complaint are now disabled.",
            flush=True,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


def cmd_remove(args):
    """Handle 'remove' subcommand."""
    try:
        removed = remove_complaint(args.id, file_path=args.data_file)
        print(
            f"Removed complaint #{removed['id']}: "
            f"'{removed['description']}'",
            flush=True,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


def cmd_check(args):
    """Handle 'check' subcommand — the core escalation check + alert run."""
    complaints = load_complaints(args.data_file)

    if not complaints:
        print(
            "No complaints tracked. Use 'add' to log a complaint.",
            flush=True,
        )
        return

    today = date.today()
    results = evaluate_all_complaints(complaints, today=today)

    # Process escalations
    notified_count = 0
    failed_count = 0

    for result in results:
        if not result.needs_notification:
            continue

        # Send Telegram alert to the USER
        success = send_escalation_alert(
            complaint_id=result.complaint_id,
            description=result.description,
            category=result.category,
            escalation_level=result.escalation_level,
            days_overdue=result.days_overdue,
            days_since_reported=result.days_since_reported,
            contact=result.contact,
            drafted_message=result.drafted_message,
        )

        if success:
            # Update the store with new escalation level + message history
            update_escalation(
                complaint_id=result.complaint_id,
                new_level=result.escalation_level,
                drafted_message=result.drafted_message,
                file_path=args.data_file,
            )
            notified_count += 1
            print(
                f"  Escalated #{result.complaint_id} to level "
                f"{result.escalation_level} — Telegram alert sent.",
                flush=True,
            )
        else:
            # Still update the store level to avoid re-triggering,
            # but log the notification failure
            update_escalation(
                complaint_id=result.complaint_id,
                new_level=result.escalation_level,
                drafted_message=result.drafted_message,
                file_path=args.data_file,
            )
            failed_count += 1
            logger.warning(
                "Telegram send failed for complaint #%s, but escalation "
                "level updated to prevent re-trigger.",
                result.complaint_id,
            )
            print(
                f"  Escalated #{result.complaint_id} to level "
                f"{result.escalation_level} — Telegram FAILED "
                f"(level still updated).",
                flush=True,
            )

    # Print summary table
    print(
        f"\nEscalation Check — {today.isoformat()}\n",
        flush=True,
    )

    # Reload complaints to show updated state
    updated_complaints = load_complaints(args.data_file)
    _print_table(updated_complaints, today)

    # Summary
    open_count = sum(
        1 for r in results if r.status in ("open", "overdue")
    )
    resolved_count = sum(1 for r in results if r.status == "resolved")
    overdue_count = sum(1 for r in results if r.status == "overdue")
    error_count = sum(1 for r in results if r.status == "error")

    print(
        f"  Open: {open_count}  |  Overdue: {overdue_count}  |  "
        f"Resolved: {resolved_count}  |  Errors: {error_count}",
        flush=True,
    )
    if notified_count:
        print(
            f"  Telegram alerts sent: {notified_count}",
            flush=True,
        )
    if failed_count:
        print(
            f"  Telegram alerts failed: {failed_count} "
            f"(check .env config)",
            flush=True,
        )
    newly_escalated = sum(1 for r in results if r.needs_notification)
    if newly_escalated == 0:
        print("  No new escalations needed.", flush=True)
    print(flush=True)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python3 -m play.main",
        description=(
            "Landlord/Maintenance Complaint Escalator — "
            "Track complaints and auto-draft escalation messages."
        ),
    )

    # Global options
    parser.add_argument(
        "--data-file",
        default=DEFAULT_COMPLAINTS_FILE,
        help=f"Path to complaints data file (default: {DEFAULT_COMPLAINTS_FILE})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command")

    # --- add ---
    add_parser = subparsers.add_parser(
        "add", help="Log a new maintenance complaint",
    )
    add_parser.add_argument(
        "--description", required=True,
        help="Describe the issue (e.g. 'Leaky tap in kitchen')",
    )
    add_parser.add_argument(
        "--category", required=True,
        help="Category (e.g. plumbing, electrical, structural)",
    )
    add_parser.add_argument(
        "--reported-date", required=True,
        help="Date the issue was reported (YYYY-MM-DD)",
    )
    add_parser.add_argument(
        "--deadline-days", type=int, required=True,
        help="Days to wait before first escalation",
    )
    add_parser.add_argument(
        "--contact", required=True,
        help="Landlord/building contact (email, phone, Telegram handle)",
    )
    add_parser.set_defaults(func=cmd_add)

    # --- list ---
    list_parser = subparsers.add_parser(
        "list", help="Show all tracked complaints",
    )
    list_parser.set_defaults(func=cmd_list)

    # --- resolve ---
    resolve_parser = subparsers.add_parser(
        "resolve", help="Mark a complaint as resolved",
    )
    resolve_parser.add_argument(
        "--id", required=True,
        help="Complaint ID to resolve (shown in 'list' output)",
    )
    resolve_parser.set_defaults(func=cmd_resolve)

    # --- remove ---
    remove_parser = subparsers.add_parser(
        "remove", help="Delete a complaint entirely",
    )
    remove_parser.add_argument(
        "--id", required=True,
        help="Complaint ID to remove (shown in 'list' output)",
    )
    remove_parser.set_defaults(func=cmd_remove)

    # --- check ---
    check_parser = subparsers.add_parser(
        "check",
        help="Run escalation check and send Telegram alerts (default)",
    )
    check_parser.set_defaults(func=cmd_check)

    return parser


def main():
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Default to 'check' if no subcommand given
    if args.command is None:
        args.command = "check"
        args.func = cmd_check

    args.func(args)


if __name__ == "__main__":
    main()
