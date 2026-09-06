# ---
# name: landlord-complaint-escalator
# description: "Local-first, zero-API maintenance complaint tracker and automated 3-tier Telegram escalation drafter. Designed for tenants dealing with slow landlord or property management maintenance responses. Log complaints locally once (e.g. 'leaky faucet in kitchen', 'broken radiator'), set resolution deadlines, and run daily checks. If unresolved, it automatically drafts progressively escalating messages (Level 1: Polite Reminder -> Level 2: Firm Follow-Up -> Level 3: Formal Notice referencing generic tenancy agreements) delivered straight to your personal Telegram for 1-tap copy-pasting to building groups or property managers. Zero auto-sending to third parties guarantees 100% human-in-the-loop safety. Includes 76/76 unit tests, atomic JSON persistence, and corrupted-file recovery."
# metadata:
#   version: 0.1.1
#   status: released
#   rote_version: 0.78.0
#   kind: atomic
#   flow_type: sequential
#   execution_model: legacy
#   requires_sessions: false
# inputs:
#   command:
#     type: string
#     description: "CLI subcommand to execute: add, list, resolve, remove, or check (default: check)"
#     required: false
#     default: "check"
#   description:
#     type: string
#     description: "Maintenance issue description (e.g. 'Leaky faucet in kitchen sink')"
#     required: false
#   category:
#     type: string
#     description: "Category of maintenance issue (e.g. plumbing, electrical, structural, HVAC)"
#     required: false
#     default: "general"
#   reported_date:
#     type: string
#     description: "Date issue was reported in YYYY-MM-DD format (e.g. '2026-09-01')"
#     required: false
#   deadline_days:
#     type: integer
#     description: "Number of days allowed before first escalation triggers (default: 3)"
#     required: false
#     default: 3
#   contact:
#     type: string
#     description: "Landlord or property manager contact info (phone, email, Telegram handle)"
#     required: false
# ---

"""Main entrypoint for Rote Play: Landlord/Maintenance Complaint Escalator."""

import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from lib.main import main
except ImportError:
    from play.main import main

if __name__ == "__main__":
    main()
