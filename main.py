# ---
# name: landlord-complaint-escalator
# description: Zero-API local maintenance complaint tracker with automated 3-tier Telegram escalation message drafting.
# metadata:
#   version: 0.1.0
#   status: released
#   rote_version: 0.78.0
#   kind: atomic
#   flow_type: sequential
#   execution_model: legacy
#   requires_sessions: false
# ---

"""Main entrypoint for Rote Play: Landlord/Maintenance Complaint Escalator."""

import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from play.main import main

if __name__ == "__main__":
    main()
