---
name: modelzoo-image-validation
description: Resolve a named ModelZoo entry into an auditable read-only manifest and drive guarded DLC Chip and TYD Chip image workflows. Use when a model name must select ModelZoo evidence, detect framework ambiguity, or prepare generation-correct image build and validation contracts without guessing assets, refs, hardware, or authorization.
---

# ModelZoo Image Validation

Use this skill to turn one exact ModelZoo model name into a source-bound manifest before any build or validation action. ModelZoo metadata and README prose are historical declarations, not current Host, asset, image, or hardware facts.

## Inputs

- Exact model name.
- Optional exact framework selector. Require it when the name exists in more than one framework.
- Optional ModelZoo root; default to `/home/xuansun/ModelZoo`.
- Optional approved preflight contract for action intents. Absence means `resolve_only`, never implicit authorization.

The optional `--preflight <json>` document contains `intent`, absolute `weight_path`, per-component `component_sources`, and `base_image`, `framework_package`, `hardware`, and `authorization` observations. Each observation payload and detached signature carries a SHA-256 and must verify against the protected local public key at `/etc/chipltech/modelzoo-observation.pub`; ordinary caller-created JSON and hashes are never current Host facts. The signed JSON must exactly bind the asserted identity, hardware generation/availability/occupancy, or authorization intent. A production `weight_path` is a discovery hint only until the later sealed action record binds its asset identity. Production component sources must be exact entries in the root-owned, non-writable per-component allowlist at `/etc/chipltech/modelzoo-component-roots.json`, and exact 40-character refs must resolve with `git cat-file`; model assets must include `config.json`. Sensitive path segments are redacted before serialization. Supported intents are `prepare_dlc`, `prepare_tyd`, `prepare_both`, `validate_dlc`, `validate_tyd`, and `validate_both`. Missing, mismatched, unsigned, or unsealed evidence fails closed, and the manifest retains effective observations for audit.

The hidden fixture-only public-key input exists solely for deterministic repository tests. Its manifests carry `current_observations.trust_class: fixture_diagnostic` and `action_eligible: false`; they may prove resolver behavior but cannot authorize a build, export, package validation, or device operation. Resolver manifests are qualification-only even with a production observer: the later action workflow must seal its own asset, component, authorization, and execution evidence. Production callers must not supply a signing key through CLI input.

## Workflow

1. Run `scripts/resolve-modelzoo.py --model <name> [--framework <framework>] [--modelzoo-root <root>]`. Complete when it emits deterministic JSON with source-relative paths, byte hashes, ModelZoo Git identity when available, and no ModelZoo changes.
2. Stop on every structured blocker. Never choose among duplicate names, repair ModelZoo, substitute an asset, resolve a movable component ref, or turn `Infer: false` into support.
3. Audit `source_claims`, `current_observations`, `resolved`, `missing_fields`, and `conflicts` separately. Resolver output is qualification-only: an action workflow must independently seal its action-eligible evidence. README hosts, benchmark values, commands, and paths remain historical ModelZoo declarations until independently checked. Credentials, URL userinfo, secret-bearing environment values, and sensitive CLI flags are excluded rather than copied to a manifest. A final validation report uses `modelzoo_claims`, `current_observations`, `inferences`, `execution_evidence`, and `unverified_scope`.
4. For a supported `vllm/v1` manifest, resolve approved fixed component commits and model assets. Delegate workstation package/import and layered Runtime checks to `dlc-env-setup`; delegate model compatibility, TP derivation, and model-run evidence to `model-adaptation`. Do not reproduce either skill's smoke or adaptation logic.
5. Build the DLC image only with explicit authorization and fixed inputs. Run C1a package/import, then fresh-process C1b and the minimum model smoke only when qualified DLC hardware and device-execution authorization exist. Require liveness, non-empty output, observable correctness, precise service cleanup, port closure, and return to the pre-task process/HBM baseline.
6. Export the DLC image as a fixed tag, Image ID, independent tar, tar SHA-256, and attestation. A mutable alias is not delivery identity.
7. Build TYD as a separate image and tar. The actual compile process for every full-stack component must inherit `DLC_TPU_VERSION=2`: dlc-thunk, LLVM, DLCsim, DLCSynapse, DLC_CL, DLC_Custom_Kernel Repository, PyTorch DLC Backend, and vLLM. Image `ENV` alone is insufficient; retain process-environment evidence for each component. Build epochs are append-only: preserve failed epochs and completed-component provenance, and use a new epoch with an explicit supersession reference for every retry.
8. Perform TYD static/package/import, hash, label, and attestation checks. On DLC Gen1, record device execution, C1b, DLCCL, model loading, serving, and benchmark as `intentionally_not_executed_on_dlc_gen1`; never attempt them. TYD functional smoke requires a separately qualified TYD Host and explicit authorization.
9. Export independent TYD fixed tag, Image ID, tar, tar SHA-256, and attestation, then clean only resources created by this workflow. Complete when delivery identities, validation statuses, blockers, not-verified claims, prohibited claims, and cleanup evidence are all explicit.

## Block Contract

- `blocked_model_not_found`: no exact model name exists in the authoritative root.
- `blocked_ambiguous_model`: the exact-name candidates remain non-unique, including selector misses.
- `blocked_malformed_metadata`: YAML, mapping, duplicate-key, or field-type validation failed; `blocked.details` retains the precise diagnostic.
- `blocked_missing_required_field`: the supported adapter lacks required weight, component, serve, smoke, provenance, or current Host preflight evidence.
- `blocked_conflicting_source_claims`: critical declarations conflict without a safe priority decision.
- `blocked_missing_asset`: the effective approved model asset does not exist on the current Host.
- `blocked_unresolved_component_ref`: a declared full ref cannot be fixed from approved local sources.
- `blocked_unsupported_framework`: the entry is parsed and hashed, but no execution adapter exists. Only vLLM is implemented.
- `blocked_missing_hardware`: an action requires hardware that is not qualified and available.
- `blocked_missing_authorization`: an action lacks explicit authorization.
- `blocked_cleanup_incomplete`: task-owned resources did not return to the sealed cleanup contract; this is a final validation-report state rather than a resolver observation.

## Claim Matrix

| Area | Status |
| --- | --- |
| Exact read-only ModelZoo selection and deterministic manifest | supported |
| vLLM DLC/TYD workflow contract | supported |
| Non-vLLM execution adapter | blocked_unsupported_framework |
| README claims as current environment or validation facts | not verified |
| DLC C1b or model smoke without qualified hardware and authorization | blocked |
| TYD device execution on DLC Gen1 | prohibited; intentionally_not_executed_on_dlc_gen1 |
| Network download, registry push, driver/service/firmware change, reset, or reboot | prohibited |

## Resolver Exit Contract

- Exit `0`: resolved manifest.
- Exit `20`: deterministic blocked manifest; inspect `blocked.code`, `blocked.details`, and `blocked.missing_or_conflicting_fields`.
- The resolver only reads ModelZoo and writes canonical JSON to stdout. It does not build images, load models, contact a network, operate a device, or establish hardware evidence.

The resolver emits `modelzoo-dlc-tyd-resolved-manifest/v1`. Later build and validation stages must emit a distinct `modelzoo-dlc-tyd-validation-report/v1`; resolver status `resolved` never means an image, model, benchmark, or Real DLC Hardware check passed.
