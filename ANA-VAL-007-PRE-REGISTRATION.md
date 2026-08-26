# ANA-VAL-007 — Kubernetes / Deployment Conditional Update
Pre-registration date: 2026-08-25
Status: PRE-REGISTERED / FROZEN
H3 changes: NONE

## Evidence grade

This phase has two layers:

1. Official Kubernetes mechanism audit, grounded in Kubernetes documentation.
2. Local API-semantics reference harness implementing the documented `resourceVersion` lost-update contract.

A real kube-apiserver cluster is not available in the current execution runtime. Therefore a reference-harness PASS must not be relabelled as real-cluster validation.

## Designs

### K1 — Deployment `resourceVersion` CAS only

Authority is external to the Deployment object.

Flow:
- check external authority;
- read Deployment at resourceVersion r;
- external authority may change;
- update Deployment using expected resourceVersion r.

Hypothesis:
K1 protects stale Deployment state, but does not make external authority revocation atomic with the Deployment update.

### K2 — authority/version + action identity in the SAME Deployment object

The Deployment object carries:
- authority state/version;
- parent/delegated authority version where relevant;
- bound H3 ActionDigest;
- consequence state;
- commit receipt/id.

Revocation or authority change updates that same object and therefore changes `resourceVersion`.

Consequence update must:
- present the exact prior `resourceVersion`;
- match the bound authority version/state;
- match exact ActionDigest;
- update consequence state conditionally.

Hypothesis:
Within one object, `resourceVersion` can provide the serialization boundary needed for the tested update consequence.

### K3 — authority in a separate Kubernetes object

Authority is in ConfigMap/Authority CR object A.
Consequence is Deployment object D.

Client reads A and D, then updates D conditional only on D.resourceVersion.

Hypothesis:
Separate resourceVersions do not create an atomic multi-object authority+consequence transaction. Revoking A can race with updating D.

## Frozen test matrix

Q01 K1 valid authority + current Deployment RV -> ALLOW/UPDATE.
Q02 K1 stale Deployment RV -> 409 / no update.
Q03 K1 external authority revoked before precheck -> BLOCK.
Q04 K1 external authority revoked after precheck before update, Deployment RV unchanged -> EXPECT VULNERABILITY: update succeeds.
Q05 K1 exact action mutated after prepare -> BLOCK by action digest.
Q06 K1 target Deployment substituted -> BLOCK by CAI/target binding.
Q07 K1 competing updates from same RV -> at most one succeeds.

Q08 K2 valid authority embedded in same object + exact action -> UPDATE.
Q09 K2 revocation update serializes first -> stale consequence RV -> 409/no consequence.
Q10 K2 consequence update serializes first -> consequence UPDATE then revocation may update afterward.
Q11 K2 authority version changes with scope unchanged -> stale RV -> 409.
Q12 K2 parent/delegated authority version changes -> stale RV -> 409.
Q13 K2 action digest mismatch -> BLOCK.
Q14 K2 recipient/target/tool/environment material mutation -> BLOCK.
Q15 K2 replay same stale authorization after successful update -> 409/no second transition.
Q16 K2 duplicate delivery from same expected RV -> one update maximum.
Q17 K2 two competing consequences from same RV -> one maximum.
Q18 K2 legitimate independent Deployment updates -> both may succeed.
Q19 K2 expired authority encoded in current object -> BLOCK.
Q20 K2 receipt binds ActionDigest + authorityVersion + resulting RV/commit identity -> PASS.

Q21 K3 separate authority object revoked after read, Deployment unchanged -> EXPECT VULNERABILITY: Deployment update can succeed.
Q22 K3 stale Deployment RV as well -> Deployment update rejected.
Q23 K3 authority object and Deployment updated independently with retries -> no claim of atomic ANA.
Q24 K3 valid authority with no race -> legitimate Deployment update succeeds.

## Forced race audit

R1 K1 external revocation after precheck vs Deployment update.
Expected: reproduce K1 vulnerability.

R2 K2 revocation same-object update gets CAS first.
Expected: consequence stale RV rejected.

R3 K2 consequence same-object update gets CAS first.
Expected: consequence commits while authority state in serialized object is current; revocation follows.

R4 K2 two competing consequences from same RV.
Expected: exactly one succeeds.

R5 K3 separate authority-object revocation first, Deployment RV unchanged.
Expected: consequence can still update Deployment, demonstrating lack of cross-object atomicity.

## Kill conditions

K2 is falsified if:
- a consequence update succeeds with a stale same-object resourceVersion;
- material action differs from bound ActionDigest;
- revocation/version change in the same object serializes first yet stale consequence still updates;
- duplicate/competing transition causes more than one forbidden consequence.

## Positive controls

Q01, Q08, Q18, Q24 must allow legitimate updates.

## Claim boundary

Even if K2 passes the reference harness, real Kubernetes validation remains pending until these cases execute against a real kube-apiserver / etcd persistence path.
