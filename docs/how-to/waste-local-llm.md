# Local WASTE LLM (default — no Claude)

AOA’s opportunity path (Tom → Julie → Morgan → Hailey → Alan) and the trading
swarm reason through a single `LLMClient`. **By default that is a local
[WASTE](https://github.com/sqliteai/waste) OpenAI-compatible server** — not
Claude. Anthropic is opt-in only (`AOA_LLM_PROVIDER=anthropic`).

WASTE streams MoE experts from NVMe so large models can run without fitting
entirely in RAM. AOA talks to it through `/v1/chat/completions`.

## 1. Build and serve WASTE

On a machine with enough RAM/NVMe (Kimi-Linear is the practical starting
point; full K3 needs ~64 GB + ~1 TB — see upstream README):

```bash
git clone https://github.com/sqliteai/waste
cd waste
make
# after you have a converted container, e.g. ~/models/kimi-linear.waste:
make libwaste.so   # libwaste.dylib on macOS
python3 -m serve ~/models/kimi-linear.waste --port 8000
```

Smoke-test:

```bash
curl -s localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"kimi-linear","messages":[{"role":"user","content":"ping"}]}'
```

Use the model id your server advertises (often `k3` or the container stem).

## 2. AOA defaults (already set)

`.env.example` ships with:

```bash
AOA_LLM_PROVIDER=openai_compatible
AOA_LLM_BASE_URL=http://127.0.0.1:8000/v1
AOA_LLM_API_KEY=local
AOA_MODEL=kimi-linear
AOA_EFFORT=high
```

No `ANTHROPIC_API_KEY` is required. Change `AOA_MODEL` to match the served
container. `AOA_EFFORT` is sent as WASTE `reasoning_effort` (medium→high,
xhigh→max) and dropped automatically if the model rejects it.

## 3. Verify

```bash
python3 -m aoa.cli doctor
python3 -m aoa.cli team brief
```

Doctor should report `provider=openai_compatible` and a successful LLM ping.
`team brief` runs Alan’s opportunity aggregation against the local model.

## Opt-in Claude (not recommended for this project)

```bash
pip install 'aoa-financial[anthropic]'
# in .env:
AOA_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
AOA_MODEL=claude-sonnet-4-6
```

## Notes

- Structured agent outputs use `response_format.json_schema` when the server
  supports it (WASTE does); otherwise AOA falls back to a schema-in-prompt path.
- Serve WASTE on hardware that holds the container, then set `AOA_LLM_BASE_URL`
  if it is not on localhost.
