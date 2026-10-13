# LESSONS - auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation - do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-001 - When a decision requires every write path to refresh derived aggregates, audit bulk deletes and ORM or FK cascades (import undo, account delete), not only service CRUD functions
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `write-paths` · harmful: 0
- features: credit-card-bills
- evidence: backend/app/api/import_logs.py:93-97; backend/app/services/account_service.py:622 (write-paths)
- last seen: 2026-10-13T06:24:57Z

### L-002 - Cover behavior that relies on database foreign key cascades with a PostgreSQL test, since the SQLite test schema does not enforce foreign keys
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `tests` · harmful: 0
- features: credit-card-bills
- evidence: spec Edge Cases: card account deleted (tests)
- last seen: 2026-10-13T06:24:57Z

### L-003 - For a concurrency edge case, assert every stated outcome of the race (single row and all writers attached to it), not only the uniqueness
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `tests` · harmful: 0
- features: credit-card-bills
- evidence: backend/tests/test_bill_service.py:330-335 (tests)
- last seen: 2026-10-13T06:24:57Z

### L-004 - When the spec says two screens must show equal figures, assert both screens against the same fixture in one test
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `frontend` · harmful: 0
- features: credit-card-bills
- evidence: BVIEW AC 8 (frontend)
- last seen: 2026-10-13T06:24:58Z

### L-005 - Name the outcome for every amount relation (below, equal, above) in a matching spec so implementers do not invent a category
- signal: `spec_deviation` · recurrence: 1 feature(s) · scope: `matching` · harmful: 0
- features: credit-card-bills
- evidence: backend/app/services/bill_match_service.py:104 (matching)
- last seen: 2026-10-13T06:24:58Z

### L-006 - Do not prescribe a savepoint per item in design when the called service commits internally; check the callee's transaction behavior first
- signal: `spec_deviation` · recurrence: 1 feature(s) · scope: `design` · harmful: 0
- features: credit-card-bills
- evidence: backend/app/services/bill_match_service.py:316 (design)
- last seen: 2026-10-13T06:24:58Z

## Quarantined (failed when applied - ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
