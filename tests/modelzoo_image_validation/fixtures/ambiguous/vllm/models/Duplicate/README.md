## Weights
/models/Duplicate
## Software
**dlc-thunk**: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
**LLVM**: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
**DLCsim**: cccccccccccccccccccccccccccccccccccccccc
**DLCSynapse**: dddddddddddddddddddddddddddddddddddddddd
**DLC_CL**: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
**DLC_Custom_Kernel**: ffffffffffffffffffffffffffffffffffffffff
**pytorch**: 1111111111111111111111111111111111111111
**vllm**: 2222222222222222222222222222222222222222
## Start Service
```bash
python -m vllm.entrypoints.openai.api_server --model /models/Duplicate --device dlc
```
## Request
```bash
curl http://127.0.0.1:8000/v1/completions
```
