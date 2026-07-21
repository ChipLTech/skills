# Complete-7B
## Software
**dlc-thunk**: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
**LLVM**: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
**DLCsim**: cccccccccccccccccccccccccccccccccccccccc
**DLCSynapse**: dddddddddddddddddddddddddddddddddddddddd
**DLC_CL**: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
**DLC_Custom_Kernel**: ffffffffffffffffffffffffffffffffffffffff
**pytorch**: 1111111111111111111111111111111111111111
**vllm**: 2222222222222222222222222222222222222222
## Environment Variables
```bash
export DLC_SYN_URING=1
export VLLM_USE_V1=1
```
## Weights
/models/Complete-7B
## Start Service
```bash
python -m vllm.entrypoints.openai.api_server --model /models/Complete-7B --device dlc --port 8000 -tp 1
```
## Request
```bash
curl http://127.0.0.1:8000/v1/completions
```
