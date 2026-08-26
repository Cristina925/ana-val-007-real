# ANA-VAL-007-REAL runner preparation defect freeze

Date: 2026-08-26
Status: FROZEN BEFORE RUNNER CORRECTION

Superseded runner package SHA-256:
`262b4563e8e6d4cf593070b8242dc2c41d9f34c2f153d4a420bf47a19a66e6a0`

No ANA scientific result was produced by the superseded runner.

## RD-001 — ownership namespace
The superseded script used the annotation prefix `ana.openai-research/`.
ANA is Cristina Rasmussen's independent research programme; that prefix was inappropriate.
This is an instrument-label defect, not an ANA hypothesis change.

## RD-002 — forced-race fidelity
R1, R2, R3 and R5 in the superseded script were implemented as sequential ordered calls.
The frozen protocol requires the forced races to be exercised with two clients/barriers.
The superseded runner therefore must not be used to claim protocol-complete real-cluster validation.

## RD-003 — missing Kubernetes audit log
The superseded workflow captured control-plane logs but did not configure kube-apiserver audit logging.
The frozen evidence plan explicitly requires audit events.

## RD-004 — concurrent evidence sequencing
Concurrent HTTP calls shared an unsynchronised evidence sequence counter.
This could cause ambiguous/colliding evidence filenames under concurrency.

## Correction rule
Correct the runner instrument only.
Do not change:
- H3;
- K1/K2/K3;
- Q01-Q24;
- R1-R5;
- expected outcomes;
- kill conditions;
- published RC-1.

Freeze any future runner discrepancy before altering the experiment.
