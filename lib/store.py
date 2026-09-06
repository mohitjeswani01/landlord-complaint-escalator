"""Complaint data store with atomic writes and corrupted-file recovery.

Manages the complaint list (data/complaints.json) with:
- Atomic writes (temp file + os.replace) for crash safety
- Corrupted-file backup and recovery
- Auto-incrementing integer IDs for user-friendly references
- Full CRUD: add, resolve, remove, load, save
- Escalation state tracking per complaint

Ported from document-expiry-watchdog store with adapted schema.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_COMPLAINTS_FILE = os.path.join("data", "complaints.json")


# ---------------------------------------------------------------------------
# Low-level JSON persistence (atomic write + corruption recovery)
# ---------------------------------------------------------------------------

def _load_json_file(file_path: str, expected_type: type):
    """Load and validate a JSON file, recovering gracefully if it is missing
    or is corrupted. Corrupted files are backed up before resetting.
    """
    path = Path(file_path)

    if not path.exists():
        logger.info(
            "File %s does not exist yet — will create on first write.",
            file_path,
        )
        return expected_type()

    if path.stat().st_size == 0:
        logger.info("File %s is empty — starting fresh.", file_path)
        return expected_type()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, expected_type):
            raise ValueError(
                f"Expected {expected_type.__name__}, got {type(data).__name__}"
            )

        return data

    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
        logger.warning(
            "File %s is corrupted (%s). Backing up and starting fresh.",
            file_path,
            e,
        )
        backup_path = (
            f"{file_path}.corrupted."
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        try:
            path.rename(backup_path)
            logger.info("Corrupted file backed up to %s", backup_path)
        except OSError as rename_err:
            logger.error("Failed to back up corrupted file: %s", rename_err)
        return expected_type()


def _save_json_file(file_path: str, data) -> None:
    """Atomically save data to a JSON file.

    Writes to a temp file first, then renames for crash safety.
    """
    path = Path(file_path)
    tmp_path = path.with_suffix(".tmp")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())

        tmp_path.replace(path)
        logger.debug("Saved data to %s", file_path)

    except OSError as e:
        logger.error("Failed to save to %s: %s", file_path, e)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


# ---------------------------------------------------------------------------
# Complaint list management
# ---------------------------------------------------------------------------

def load_complaints(file_path: str = DEFAULT_COMPLAINTS_FILE) -> list[dict]:
    """Load the complaint list from disk.

    Returns an empty list if the file doesn't exist yet.
    """
    data = _load_json_file(file_path, list)
    if not isinstance(data, list):
        return []
    return data


def save_complaints(
    complaints: list[dict], file_path: str = DEFAULT_COMPLAINTS_FILE
) -> None:
    """Save the complaint list atomically."""
    _save_json_file(file_path, complaints)


def _next_id(complaints: list[dict]) -> str:
    """Generate the next auto-incrementing integer ID.

    Scans existing IDs to find the max, then returns max + 1.
    Handles gaps gracefully — always increments from the highest existing.
    """
    max_id = 0
    for c in complaints:
        try:
            cid = int(c.get("id", 0))
            if cid > max_id:
                max_id = cid
        except (ValueError, TypeError):
            continue
    return str(max_id + 1)


def add_complaint(
    description: str,
    category: str,
    reported_date: str,
    deadline_days: int,
    contact: str,
    file_path: str = DEFAULT_COMPLAINTS_FILE,
) -> dict:
    """Add a new complaint and return the created record.

    Auto-assigns an integer ID. Initial status is 'open',
    escalation_level is 0.
    """
    complaints = load_complaints(file_path)
    new_id = _next_id(complaints)

    record = {
        "id": new_id,
        "description": description.strip(),
        "category": category.strip().lower(),
        "reported_date": reported_date.strip(),
        "deadline_days": int(deadline_days),
        "contact": contact.strip(),
        "status": "open",
        "escalation_level": 0,
        "last_escalated_at": None,
        "drafted_message_history": [],
    }

    complaints.append(record)
    save_complaints(complaints, file_path)
    logger.info(
        "Added complaint #%s: '%s' (deadline: %d days).",
        new_id, description, deadline_days,
    )
    return record


def find_complaint_by_id(
    complaint_id: str, file_path: str = DEFAULT_COMPLAINTS_FILE
) -> Optional[dict]:
    """Find a complaint by its ID. Returns None if not found."""
    complaints = load_complaints(file_path)
    target = str(complaint_id).strip()
    for c in complaints:
        if str(c.get("id", "")).strip() == target:
            return c
    return None


def resolve_complaint(
    complaint_id: str, file_path: str = DEFAULT_COMPLAINTS_FILE
) -> Optional[dict]:
    """Mark a complaint as resolved. Does NOT delete it (keeps history).

    Returns the updated record, or None if the ID was not found.

    Raises:
        ValueError: If the complaint ID does not exist.
    """
    complaints = load_complaints(file_path)
    target = str(complaint_id).strip()

    for c in complaints:
        if str(c.get("id", "")).strip() == target:
            if c.get("status") == "resolved":
                logger.info(
                    "Complaint #%s is already resolved.", complaint_id,
                )
                return c

            c["status"] = "resolved"
            save_complaints(complaints, file_path)
            logger.info("Resolved complaint #%s.", complaint_id)
            return c

    raise ValueError(
        f"Complaint #{complaint_id} not found. "
        f"Use 'list' to see all complaint IDs."
    )


def remove_complaint(
    complaint_id: str, file_path: str = DEFAULT_COMPLAINTS_FILE
) -> Optional[dict]:
    """Fully remove a complaint record.

    Returns the removed record, or None if not found.

    Raises:
        ValueError: If the complaint ID does not exist.
    """
    complaints = load_complaints(file_path)
    target = str(complaint_id).strip()

    for i, c in enumerate(complaints):
        if str(c.get("id", "")).strip() == target:
            removed = complaints.pop(i)
            save_complaints(complaints, file_path)
            logger.info(
                "Removed complaint #%s: '%s'.",
                complaint_id, removed.get("description"),
            )
            return removed

    raise ValueError(
        f"Complaint #{complaint_id} not found. "
        f"Use 'list' to see all complaint IDs."
    )


def update_escalation(
    complaint_id: str,
    new_level: int,
    drafted_message: str,
    file_path: str = DEFAULT_COMPLAINTS_FILE,
) -> Optional[dict]:
    """Update a complaint's escalation level and record the drafted message.

    Appends the message to drafted_message_history with timestamp and level.
    Returns the updated record.
    """
    complaints = load_complaints(file_path)
    target = str(complaint_id).strip()

    for c in complaints:
        if str(c.get("id", "")).strip() == target:
            c["escalation_level"] = new_level
            c["last_escalated_at"] = datetime.now(
                timezone.utc
            ).isoformat()

            # Initialize history if missing (backward compat)
            if "drafted_message_history" not in c:
                c["drafted_message_history"] = []

            c["drafted_message_history"].append({
                "level": new_level,
                "message": drafted_message,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            })

            save_complaints(complaints, file_path)
            logger.info(
                "Escalated complaint #%s to level %d.",
                complaint_id, new_level,
            )
            return c

    logger.warning(
        "Could not update escalation — complaint #%s not found.",
        complaint_id,
    )
    return None
