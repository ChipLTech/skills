# Profiling Evidence Contract

Use `scripts/validate-dlc-profile-artifacts.py` only on an existing
`dlc-profile-evidence-manifest/v1`. The validator is read-only: it neither
starts profiling nor executes a model.

The manifest and `dlc-profile-validation-result/v1` are closed-world
`qualification-artifact-envelope/v1` artifacts. Their topic fields are explicit
extensions to the shared envelope. The generated envelope contract is required;
if it cannot be loaded, validation fails closed with only
`missing_generated_contract`. Producer policy, full subject identity, canonical
blocker ordering, aggregate status, canonical digest, and stale-identity behavior
come from that contract.

It reports trace syntax, exact trace-byte identity, and localization scopes
separately. A valid Chrome trace can establish `trace_track` localization.
Request, phase, rank, and device remain `not_verified` unless an exact,
digest-bound `dlc-profile-semantic-artifact/v1` companion supplies that scope.
The companion is itself a closed-world shared-envelope artifact. Its validated
contents, not fields in the manifest reference, define the scopes. It must bind
the exact trace digest, workload digest, full subject identity, and diagnostic
epoch, and its producer must match the manifest reference. An arbitrary file,
even one containing plausible scope names, cannot upgrade localization. Chrome trace
`pid` and `tid` are opaque track labels; they are not OS PID/TID, rank, or
device identities.

Complete-event `ts` and `dur` must be non-negative integers and cannot be
booleans. `pid` and `tid` must be integer or string opaque labels and cannot be
null, booleans, arrays, or objects.

`dlcProfilerStart` or `dlcProfilerStop` returning success is never acquisition
evidence. An actual trace file with a matching SHA-256 digest is required.
Diagnostic profile evidence is always acceptance-ineligible and cannot be
promoted to a formal benchmark.

Claim Boundary: this contract proves deterministic read-only validation and
bounded localization scopes only; it does not prove Real DLC Hardware state,
causality, production performance, or formal model/benchmark/image acceptance.
