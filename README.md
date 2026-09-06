# Landlord/Maintenance Complaint Escalator

You reported a leaky tap three weeks ago. Nothing happened. You sent a polite reminder — still nothing. You don't want to be *that* tenant, but you also don't want water damage ruining your kitchen floor. What do you even say after three weeks? How firm is too firm?

**This Play solves that.** You log the complaint once, set a deadline, and walk away. If the issue isn't resolved in time, the Escalator automatically drafts the *exact* message to send — at exactly the right level of firmness for how long you've waited. A polite nudge after the first deadline. A firmer follow-up after twice the deadline. A formal notice referencing your tenancy agreement after three times the deadline.

You get a Telegram alert with the full message ready to copy-paste. Review it, personalize it if you want, and send it yourself. Done.

> **⚠️ Important: This Play NEVER auto-sends anything to your landlord or building management.** It only alerts *you* with a ready-to-send draft. You always review and send it yourself. This is a drafting tool, not an auto-mailer.

---

## How It Works

1. **Log a complaint** with `add` — describe the issue, set a deadline.
2. **Run `check`** daily (manually or via cron) — the escalator evaluates every open complaint.
3. **If a complaint crosses a deadline threshold**, a Telegram alert arrives with a drafted message you can copy-paste and send.
4. **Escalation levels increase automatically** — the tone gets firmer each time a new threshold is crossed:
   - **Level 1** (1× deadline): Polite reminder
   - **Level 2** (2× deadline): Firm follow-up referencing elapsed time
   - **Level 3** (3× deadline): Formal notice referencing your tenancy agreement
5. **Mark resolved** when fixed — no more escalations.

The escalator **never re-sends the same level twice**. Once level 1 fires, it won't fire again — it waits for level 2.

---

## Quick Start

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd landlord-complaint-escalator
```

### 2. Set up Telegram notifications

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=your-bot-token-from-botfather
TELEGRAM_CHAT_ID=your-chat-id-from-userinfobot
```

> **Tip:** If you already set up Telegram for another Play (document-expiry-watchdog, etc.), you can reuse the same bot token and chat ID.

### 3. Log your first complaint

```bash
python3 -m play.main add \
    --description "Leaky tap in kitchen" \
    --category plumbing \
    --reported-date 2026-09-01 \
    --deadline-days 3 \
    --contact "building-group@example.com"
```

### 4. Run the escalation check

```bash
python3 -m play.main check
```

If any complaint is past its deadline and hasn't been escalated at that level yet, you'll get a Telegram alert with a ready-to-send message.

---

## CLI Reference

### `add` — Log a new complaint

```bash
python3 -m play.main add \
    --description "Broken window latch in bedroom" \
    --category structural \
    --reported-date 2026-09-01 \
    --deadline-days 5 \
    --contact "landlord@example.com"
```

| Flag | Required | Description |
|------|----------|-------------|
| `--description` | Yes | What the issue is |
| `--category` | Yes | Category (plumbing, electrical, structural, etc.) |
| `--reported-date` | Yes | Date you reported it (YYYY-MM-DD) |
| `--deadline-days` | Yes | Days to wait before first escalation |
| `--contact` | Yes | Landlord/building contact (email, phone, Telegram handle) |

### `list` — Show all complaints

```bash
python3 -m play.main list
```

Output:

```
Complaints — 2026-09-10

  ID    Description                          Category      Status    Days    Level
  ----------------------------------------------------------------------------------
  1     Leaky tap in kitchen                 Plumbing      OVERDUE   9       2
  2     Broken window latch in bedroom       Structural    OPEN      3       0
  3     Flickering hallway light             Electrical    DONE      14      1

  Total: 3  |  Open: 1  |  Resolved: 1
```

### `resolve` — Mark a complaint as fixed

```bash
python3 -m play.main resolve --id 1
```

This stops all future escalation for complaint #1. The record is kept for your reference (not deleted).

### `remove` — Delete a complaint entirely

```bash
python3 -m play.main remove --id 2
```

Permanently removes the complaint from tracking.

### `check` — Run escalation check (default)

```bash
python3 -m play.main check
# or just:
python3 -m play.main
```

For every open complaint past its deadline, this:
1. Calculates the current escalation level
2. Drafts a message at the appropriate tone
3. Sends you a Telegram alert with the full message
4. Updates the complaint's escalation state

---

## Escalation Messages — Real Examples

Here's what the escalator actually drafts. These are the real messages, not summaries.

### Level 1 — Polite Reminder (fires at 1× deadline)

```
Hi,

I hope this message finds you well. I wanted to follow up on a
maintenance issue I reported on 2026-09-01.

Issue: Leaky tap in kitchen
Category: Plumbing

It has been 3 day(s) since I submitted this request, and the issue
is still unresolved. I understand things can get busy, but I would
really appreciate it if this could be looked into at your earliest
convenience.

Could you please provide an update on when I might expect a
resolution? I'm happy to coordinate access to the unit or provide
any additional details that would help.

Thank you for your attention to this matter.

Best regards
```

### Level 2 — Firm Follow-up (fires at 2× deadline)

```
Dear Management,

I am writing to follow up — for the second time — regarding a
maintenance issue that remains unresolved.

Issue: Leaky tap in kitchen
Category: Plumbing
Originally reported: 2026-09-01
Days since report: 6

This has now been outstanding for 6 days since my original report
on 2026-09-01. I previously reached out after the initial 3-day
window passed and have not received a satisfactory response or
resolution.

As a tenant, I expect reported maintenance issues to be addressed
within a reasonable timeframe. The continued delay is causing
inconvenience and I would like to request that this matter be
treated as a priority.

Please confirm within the next 48 hours what concrete steps will
be taken to resolve this issue, including an expected completion
date.

I look forward to your prompt response.

Regards
```

### Level 3 — Formal Notice (fires at 3× deadline)

```
Dear Management,

RE: FORMAL NOTICE — Unresolved Maintenance Issue (Reported 2026-09-01)

I am writing to formally notify you that the following maintenance
issue has remained unresolved for 9 days, despite multiple prior
communications:

Issue: Leaky tap in kitchen
Category: Plumbing
Date originally reported: 2026-09-01
Days elapsed: 9
Prior escalation attempts: 2

As per my tenancy agreement and applicable local tenant protection
regulations, landlords and property managers are generally expected
to carry out necessary repairs within a reasonable period after
being notified by the tenant. I believe that 9 days significantly
exceeds what would be considered a reasonable timeframe, and I
encourage you to review the relevant obligations.

I am requesting that this issue be resolved within 7 calendar days
of this notice. If I do not receive confirmation of a scheduled
repair within this period, I intend to explore the following options:

  1. Filing a formal written complaint with the relevant local
     tenant authority or housing ombudsman.
  2. Seeking independent legal advice regarding my rights as a
     tenant.
  3. Documenting all correspondence and the condition of the
     property for any future proceedings.

I want to resolve this amicably and would prefer not to pursue
these steps. However, the extended period without resolution
leaves me with limited alternatives.

Please treat this as a matter of urgency.

Yours sincerely
```

> **Note:** These messages are templates. The escalator fills in your actual dates and day counts automatically. You should personalize the sign-off (add your name, unit number, etc.) before sending.

---

## Scheduling Automatic Checks

Add a cron job to run the check daily:

```bash
# Run at 9 AM every day
0 9 * * * cd /path/to/landlord-complaint-escalator && python3 -m play.main check
```

---

## Project Structure

```
landlord-complaint-escalator/
├── play/
│   ├── __init__.py
│   ├── main.py          # CLI entry point (5 subcommands)
│   ├── escalator.py     # Core escalation logic + message drafting
│   ├── store.py         # Atomic JSON persistence + CRUD
│   └── notifier.py      # Telegram alert sender
├── tests/
│   ├── test_escalator.py  # 33 tests: thresholds, messages, evaluation
│   ├── test_store.py      # 30 tests: CRUD, atomic writes, corruption
│   └── test_cli.py        # 13 tests: subcommands + full lifecycle
├── data/
│   └── complaints.json    # Auto-created on first add
├── .env                   # Telegram credentials (not committed)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Running Tests

```bash
python3 -m pytest tests/ -v
```

---

## License

MIT
