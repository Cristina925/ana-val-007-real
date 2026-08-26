# ANA-VAL-007-REAL runner v2

Purpose: execute the frozen ANA-VAL-007 Kubernetes protocol against a real Kubernetes control plane.

## Frozen inputs
- ANA-VAL-007-PRE-REGISTRATION.md is copied byte-for-byte from the preserved final evidence package.
- H3 is not modified.
- Q01-Q24 and R1-R5 are not changed.

## Execution environment
The GitHub Actions workflow creates a real kind Kubernetes cluster:
- kind v0.32.0
- Kubernetes node image v1.36.1 pinned by digest
- real kube-apiserver and etcd inside the kind control-plane node.

The harness talks to the kube-apiserver through `kubectl proxy` using Kubernetes REST PUT/POST/GET requests.
The observable consequence is persisted Deployment metadata/consequence state, not an internal policy flag.

## Run
Copy this folder into a GitHub repository, commit it, open:
Actions -> ANA-VAL-007-REAL Kubernetes -> Run workflow.

No change to the published ContinuityOS Integrated RC-1 is required. A dedicated experiment repository is preferable.

## Evidence
The workflow uploads `ANA-VAL-007-REAL-EVIDENCE`, containing:
- per-request HTTP records (including 409 Conflict status),
- Kubernetes version,
- Docker/kind environment,
- final Deployment / ConfigMap / event JSON,
- control-plane logs,
- etcd endpoint status,
- Q01-Q24 + R1-R5 result summary,
- SHA-256 manifests.

## Scientific rule
Freeze any discrepancy before changing the design or harness.
Do not call K2 real-cluster validated unless all frozen outcomes are observed on the real control plane.

## Runner-v2 instrument corrections
- programme annotation namespace changed from an inappropriate OpenAI-labelled prefix to `ana.continuityos/`;
- R1-R5 now use two request clients plus synchronization barriers/events for the frozen forced interleavings;
- API evidence records include client identity and explicit request/response resourceVersion fields;
- kind control plane is configured with Kubernetes audit logging and the audit log is captured.

These corrections change the execution instrument only. They do not change H3, K1/K2/K3, Q01-Q24, R1-R5, the oracle, or any prior result.
