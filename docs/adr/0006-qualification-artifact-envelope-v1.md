# Qualification Artifact Envelope v1

## Status

Approved for Stage A R0-C on 2026-08-08.

## Context

New DLC qualification artifacts need one byte identity, identity completeness,
status aggregation, freshness, producer authorization, and claim-boundary
contract. Reimplementing those rules in each Skill would allow validator drift
and accidental promotion. SkillHub does not currently declare cross-Skill
dependencies, so consuming Skills must remain independently installable.

The existing `vllm-dlc-run-spec`, `vllm-dlc-result-evidence`,
`vllm-dlc-parent-child-handoff`, and model-adaptation bundle v1 contracts are
already closed-world compatibility surfaces. This decision does not add fields
to them or change their consumers.

## Decision

`qualification-artifact-envelope/v1` is the closed-world common envelope for
new qualification artifacts. Its canonical schema and implementation are:

- `skills/engineering/chipltech-context/contracts/qualification-artifact-envelope-v1.schema.json`
- `skills/engineering/chipltech-context/scripts/qualification_artifact.py`

Every field is required. Nullable fields are explicitly typed. Unknown fields,
unknown major versions, invalid enums or formats, duplicate set-like array
members, incomplete identity, and policy violations fail closed. Topic-specific
schemas retain their own fields and validators; they use the common module for
the envelope rather than extending an old bundle.

## Canonical bytes and digest

Canonical JSON is UTF-8, emits Unicode directly, sorts object keys
lexicographically, and has no insignificant whitespace. Floating-point values
are forbidden by the canonicalizer. The top-level `digest` member alone is
omitted before SHA-256; `created_at` participates. The digest proves byte
identity only. It is not a signature and does not prove provenance, freshness,
trusted execution, or resistance to a malicious same-user producer.

Input artifacts are digest foreign keys. Portable records use artifact URI and
digest in their topic schema; host absolute paths are execution-local and are
not introduced into the common envelope.

## Full identity and freshness

`subject_identity` contains every identity class required by R0-B:

- source full Git SHA, repository identity, and dirty state, or the explicit
  `static_snapshot` alternative with a snapshot digest;
- installed package name, version, absolute path, and digest;
- native binary digest and image ID/digest;
- runtime, driver, and toolchain name/version/digest;
- model ID plus revision or digest, tokenizer revision or digest, and nullable
  processor revision or digest;
- workload digest;
- hardware generation and topology digest;
- versioned capability-policy ID and digest.

Missing classes produce one `missing_identity` blocker at the exact
`$.subject_identity.<class>` path in contract order. Nested omissions point to
the exact nested path. `processor: null` means the workload has no processor; an
unknown processor is missing identity and cannot be represented as null.

`static_snapshot` is permitted only when Git identity cannot be recovered. Its
repository, revision, and dirty fields are null, its snapshot digest is
mandatory, its evidence class is exactly `static_snapshot`, and it is never
acceptance eligible. It proves only facts about the sealed source bytes, not the
installed package or current execution.

Freshness comparison covers every identity class, including capability policy.
Any changed, added, removed, or reordered identity value produces
`stale_identity` for that class and invalidates consumption of the old evidence.

## Evidence and aggregation

Evidence classes, from weakest to strongest, are `static_snapshot`, `fixture`,
`diagnostic`, `operational_only`, `qualification`, and `formal_acceptance`.
Authoritativeness is independently `non_authoritative`, `operational`, or
`authoritative`. `acceptance_eligible` is an independent boolean. Top-level
status is independently `passed`, `failed`, `blocked`, `not_applicable`, or
`not_verified`; a passed status does not imply authority or acceptance.

Blockers contain exactly `status`, `code`, and JSON `path`; blocker status is
limited to `failed`, `blocked`, or `not_verified`. Aggregation precedence is
`failed`, then `blocked`, then `not_verified`. Within one class, the
lexicographically smallest `(code, path)` is the unique `primary_blocker`.
Input order cannot change the aggregate. No blockers permits only `passed` or
`not_applicable`.

## Producer policy

`qualification-artifact-producer-policy/v1` is a closed-world machine policy in
the canonical module. Each producer declares allowed schemas, explicit schema
exclusions, maximum evidence class, maximum authoritativeness, and whether it
may set `acceptance_eligible`. An exclusion overrides an allowlist entry so a
broad future edit cannot silently grant ownership. Unknown producers, unknown
schemas, excluded schemas, and claims above any producer ceiling fail closed.

Acceptance defaults false. `diagnosing-bugs` is limited to non-authoritative
fixture envelope validation. `model-adaptation` may produce bounded operational
or qualification evidence but never formal acceptance or acceptance-eligible
artifacts. Only the versioned `modelzoo-image-validation` formal producer policy
may claim `formal_acceptance`, authoritative evidence, and acceptance
eligibility for its owned model, benchmark, and image schemas. That producer is
policy vocabulary only in R0-C; this change does not modify its Skill package.

## Publication closure

`scripts/sync-qualification-artifact-contracts.py` copies canonical schema and
module bytes to `diagnosing-bugs` and `model-adaptation` under
`scripts/_generated_contracts/`. Generated copies are never edited manually.
`--check` compares SHA-256 digests and fails on missing or drifting copies.
Tests import each generated module in an isolated Python process, so an
installed consumer cannot accidentally depend on `chipltech-context`.

If SkillHub later gains shared dependencies, moving to a shared package requires
a new ADR and must preserve v1 installed artifacts.

## Consequences

All Stage A and later qualification schemas have one fail-closed envelope
implementation and deterministic freshness behavior. Installed consumers carry
duplicate bytes, but digest checks prevent semantic drift. Existing bundle v1
and vLLM-DLC contract v1/v2 behavior remain unchanged.
