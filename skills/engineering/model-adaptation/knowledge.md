# Model Adaptation Stable Decisions

shared_contract: vllm-dlc-contract/v1

Model Adaptation owns capability analysis and the smallest traceable compatibility decision for one explicit model. Main-to-Main owns upstream alignment, baseline recovery, global impact analysis, and finalization. Delegation flows from Main-to-Main to Model Adaptation and sealed evidence flows back; the child never invokes or assumes parent ownership.

TP is a model-specific deployment decision derived from approved weights, model configuration, dtype, quantization, capacity, and the target profile. Fixed regression TP values are not defaults for arbitrary models.

The shared contract owns API, lifecycle, Chunked Prefill, and DLC Runtime behavior evidence. This package names their evidence states but does not reproduce their executable assertions. Dummy is available only after sealed real-weight failure and explicit approval, remains diagnostic-only, and cannot contribute to acceptance.

Exact Ticket 06 v12 Model Adaptation completed operational regression with `authoritativeness: operational_only`, `acceptance_eligible: false`, alignment unchanged, and finalization `none`. That evidence does not establish Real DLC Hardware acceptance, Verified vLLM Alignment, request-correlated Chunked Prefill, DLC Runtime dispatch, DLCCL/LYP execution, a specific Attention implementation, Triton non-execution, compile/Dynamo non-execution, or rank-to-device allocation. New targets require their own sealed evidence. Model Adaptation does not recover, update, finalize, or claim Verified vLLM Alignment.
