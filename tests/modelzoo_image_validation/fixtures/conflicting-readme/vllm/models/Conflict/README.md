## Software
**dlc-thunk**: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
**LLVM**: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
**DLCsim**: cccccccccccccccccccccccccccccccccccccccc
**DLCSynapse**: dddddddddddddddddddddddddddddddddddddddd
**DLC_CL**: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
**DLC_Custom_Kernel**: ffffffffffffffffffffffffffffffffffffffff
**pytorch**: 1111111111111111111111111111111111111111
**vllm**: 2222222222222222222222222222222222222222
## Weights
/models/Conflict
## Start Service
```bash
python -m vllm.entrypoints.openai.api_server --model /models/Conflict --device dlc --port 8000
```
```bash
python -m vllm.entrypoints.openai.api_server --model /models/Conflict --device dlc --port 9000
```
## Request
```bash
curl http://127.0.0.1:8000/v1/completions
```
