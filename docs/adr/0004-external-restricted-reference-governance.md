# External Restricted Reference Governance

## Status

Approved as the Stage A R0-A governance contract on 2026-08-08. Legal use of
each external restricted source remains source-specific. An entry without a
completed disposition is `blocked_legal_boundary`; this ADR is not legal advice
and does not approve any external source by category.

## Context

Engineering work may receive general questions, target behavior, Chipltech-owned
source and knowledge, independently authored DLC-native specifications, and
public references whose license permits the intended use. It may also encounter
external material whose license, access terms, or redistribution rights are
restricted or unknown. Repository-wide keyword similarity cannot establish
provenance or a legal conclusion, while an unrestricted copy into an installed
Skill would create an avoidable publication risk.

## Decision

`config/restricted-reference-governance.json` is the machine-readable source
register and legal/governance authority. Every source entry records its locator,
revision or SHA-256 identity, license metadata, classification, permitted and
prohibited uses, reviewer, review date, and disposition. Unknown or unresolved
legal status fails closed as `blocked_legal_boundary`.

External restricted references are review-only inputs. CANNBot Skill prose,
scripts, templates, eval prompts, profile schemas, and fixed performance-gain
claims must not be directly imported into Skills, scripts, templates, agent
prompts, knowledge documents, schemas, or bundled references. The same boundary
applies to restricted code, translations, mechanical rewrites, and format-only
transformations. Restricted content must not be linked, copied, or otherwise
caused to enter an installable or publishable package.

The register's RACI names an accountable governance owner, legal reviewer,
restricted-reference reviewer, independent specification author, implementation
author, and publication reviewer. Legal and restricted-reference reviewers are
consulted; the independent specification and implementation authors are
responsible for their artifacts; the governance owner is accountable; the
publication reviewer verifies the distribution boundary. A restricted-reference
reviewer may not also be the implementation author for the same source. Legal
review may require further role separation.

Internal governance records may identify and discuss restricted sources for
review. Externally distributable artifacts may contain only independently
authored DLC-native requirements and implementation whose publication is
approved. General engineering vocabulary and the review terms `torch_npu`,
`msprof`, `npugraph_ex`, `PA_NZ`, `AIC`, and `AIV` are triage signals only; their
presence is not a copying, infringement, license, or provenance conclusion.

Allowlist entries are exact exceptions and contain exactly a package-relative
`path`, exact `match`, `reason`, `owner`, and ISO review date. Glob paths and
partial exemptions are invalid. An allowlist suppresses only the matching
finding at the matching path; it does not change source classification or legal
status.

## Enforcement Boundary

The validator derives exact manifests from the actual default Kilo linker,
`link-skills.sh`, plugin manifest, and SkillHub manifest. It classifies package
members before content scanning. Skill and agent instructions, executable
scripts, templates, schemas, and bundled references are failure-bearing roles.
Installation metadata, governance records, investigation records, and negative
fixtures are not execution assets unless an actual package/install manifest
includes them in a failure-bearing role.

Findings are deterministic and sorted. Review keywords produce
`review_required`, never a legal conclusion. A registered exact restricted
marker or digest in a distributed execution asset produces `prohibited_import`.
An unresolved source or legal decision produces `blocked_legal_boundary`
independently of content findings.

## Consequences

Governance evidence can name restricted material without being mistaken for an
execution asset. Packaging changes are audited against their real distribution
surface, and future implementation work cannot proceed from a restricted source
until its source-specific boundary is resolved.
