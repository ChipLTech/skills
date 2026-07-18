# 02 — Build the fake-server Smoke Runner seam

**What to build:** Provide the shared run-spec-to-result/evidence behavior seam in the skills repository and verify it through a test-only fake OpenAI-compatible server. The same public runner seam must later drive Real DLC Hardware regression. Fake-server success validates orchestration and API assertions only; it must always remain simulated and acceptance-ineligible.

**Blocked by:** 01 — Build the static workflow contract tool.

**Status:** ready-for-agent

## Inputs

- Ticket 01's versioned run-spec and result/evidence contracts.
- Fake-server scenario identity and deterministic response fixture.
- Temporary host, port, and artifact destination.
- Served model identity and declared response-field assertions.
- Startup, ordinary-request, and long-prefix timeout values.
- Read-only vllm-dlc revision and worktree-state snapshot.

## Public Test Seam

- One public Smoke Runner CLI accepts a versioned run spec and emits a sealed result/evidence JSON reference.
- A test harness starts the fake server at a real socket boundary, invokes the same runner CLI, and asserts only exit codes, result/evidence JSON, and artifacts.
- Neither tests nor fake server call runner internals or independently calculate the overall acceptance status.

## Acceptance Criteria

- [ ] A successful scenario validates live process, reachable endpoint, `/v1/models`, expected served model, completions, chat completions, non-empty generated fields, and post-request liveness.
- [ ] Separate scenarios deterministically cover non-2xx responses, malformed JSON, missing served model, missing completion text, empty completion text, missing chat content, empty chat content, and server death.
- [ ] Startup, ordinary-request, and long-prefix timeouts produce distinct machine-readable outcomes.
- [ ] Server lifecycle, allocated ports, child processes, and temporary artifacts are cleaned reliably after every scenario.
- [ ] Fake runs are marked simulated or diagnostic, are not eligible for acceptance, and never claim Real DLC Hardware, real-weight, Chunked Prefill runtime, or DLC Runtime dispatch validation.
- [ ] The runner preserves all observed gate failures even when one primary exit code is returned.
- [ ] Scenario ordering and result serialization are deterministic.
- [ ] Ticket 01 validates all resulting fixtures and package contracts.
- [ ] No file in the vllm-dlc repository is modified or generated.

## Stop Conditions

- The public runner seam cannot be implemented in the skills repository without changing vllm-dlc.
- A scenario requires fake Real DLC Hardware attestation or fabricated DLC Runtime events.
- The harness starts implementing a second hidden set of HTTP or status-aggregation rules instead of exercising the public runner.
- A required temporary endpoint cannot be isolated from existing user processes.
- The vllm-dlc worktree changes during the ticket for any reason attributable to this work.

## Evidence Requirements

- Scenario matrix mapping each case to exit code and gate status.
- One complete successful fake result/evidence JSON.
- Failure evidence for malformed JSON, empty generated fields, server death, and all three timeout classes.
- Cleanup evidence showing no retained fake-server process or temporary port listener.
- Explicit statement that fake-server evidence is not real-weight or Real DLC Hardware acceptance.
- Ticket 01 validation report.
- Before/after vllm-dlc revision and status showing zero ticket-created changes.
