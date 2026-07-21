## Environment Variables
```bash
export API_TOKEN=super-secret
```
## Weights
/models/Sensitive
## Start Service
```bash
python -m vllm.entrypoints.openai.api_server --model /models/Sensitive --host 192.168.1.20
```
