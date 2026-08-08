# Trace-Track Performance Breakdown

Use `scripts/analyze-dlc-profile.py` only after the R1 validator passes the
requested scope. V1 selects one parent instance and computes direct-child
interval union, overlap, unmatched intervals/events, coverage, and residual.
Parent and child inclusive durations are never added as if disjoint.

`residual = parent inclusive duration - non-overlapping covered duration`.
Residual is unattributed time, not evidence of duplicate execution. Events on
other trace tracks are preserved as unmatched. Request scope requires a
validated, digest-bound `dlc-profile-semantic-artifact/v1` companion linked to
the exact trace, workload, full subject identity, and diagnostic epoch;
otherwise analysis remains trace-track-bound. Scope names are derived only from
the validated companion semantic producer contents.

`dlc-perf-breakdown/v1` is a closed-world
`qualification-artifact-envelope/v1` artifact with explicit breakdown extension
fields. It inherits shared producer policy, canonical blockers/status/digest,
full identity, and stale-evidence boundaries from the passed R1 result.

Claim Boundary: the breakdown is deterministic diagnostic interval accounting.
It does not infer OS PID, rank, device, request, root cause, optimization gain,
or formal benchmark acceptance.
