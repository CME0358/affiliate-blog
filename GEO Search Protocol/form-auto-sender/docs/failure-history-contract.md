# Failure history contract

`logs/failure_events.csv` is the append-only historical event ledger. Each
production failure or safety event has an immutable `event_id`; repeated writes
with the same execution identity are ignored.

`logs/.failure_cooldown.csv` is a mutable operational current-state index. It
may update the current reason, category, failure date, and cooldown expiry for
one company/domain key. It is not historical evidence.

`logs/error.csv` remains a compatibility, append-oriented retry input. Active
cooldown suppression means it is intentionally incomplete and must not be used
as the authoritative event ledger.

Corrections preserve the original execution artifact and append a new ledger
event with `correction_of`; they do not delete or rewrite prior events.
`logs/failure_status_corrections.csv` records the authorized effective-status
correction itself, also append-only and idempotent.
