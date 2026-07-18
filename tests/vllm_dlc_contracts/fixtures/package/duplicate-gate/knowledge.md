# Duplicated Gate

shared_contract: vllm-dlc-contract/v1

Run `curl /v1/models`, then assert `/v1/completions` and `/v1/chat/completions` return HTTP 2xx and non-empty generated text.
