# Independent Implementation Boundary

## Status

Approved for Stage A R0-A on 2026-08-08, subject to every source-specific legal
disposition in `config/restricted-reference-governance.json`.

## Context

External restricted references can help a reviewer identify behavior questions,
but exposing their expression or structure to an implementation author defeats
an auditable independent-implementation boundary. Similar feature names or
general engineering terms are too weak to establish copying and must not replace
source identity, license, package role, or distribution evidence.

## Decision

Downstream implementers consume only an independently authored DLC-native
specification. That specification may state target behavior, interfaces,
constraints, and independently derived acceptance criteria. It must not preserve
restricted expression, organization, code, scripts, templates, eval prompts,
profile schemas, translations, mechanical rewrites, or fixed gain claims.

The restricted-reference reviewer records the source and allowed use, then gives
the independent specification author only the legally permitted behavior-level
input. The implementation author receives the DLC-native specification, not the
restricted reference. The publication reviewer verifies both the source register
disposition and exact package/install manifest before release. For a given
source, the restricted-reference reviewer and implementation author must be
different people; any stricter legal separation controls.

If provenance, license, permitted use, role separation, or publication status is
missing or unresolved, work stops with `blocked_legal_boundary`. Investigation
may continue inside governance records, but no affected implementation or
publishable artifact is produced. Fixed performance claims require independent
DLC evidence and publication approval.

## Consequences

The implementation lineage is auditable from source review through an
independent DLC-native specification to packaged output. Keyword hits remain
review-only, while exact source identity and distribution evidence determine
enforcement.
