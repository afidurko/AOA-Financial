# Local WASTE LLM for faster opportunity decisions

AOA’s opportunity path (Tom → Julie → Morgan → Hailey → Alan) and the trading
swarm all call a single `LLMClient`. By default that is Anthropic. Point the
same client at a local [WASTE](https://github.com/sqliteai/waste) server to keep
decision-making on-machine and cut round-trip latency for opportunity sweeps.

WASTE streams MoE experts from NVMe so large models can run without fitting
entirely in RAM. AOA talks to it only through the OpenAI chat-completions API
(`python3 -m serve`).

## 1. Build and serve WASTE

On a machine with enough RAM/NVMe (see upstream README — Kimi-Linear is the
practical starting point; full K3 needs ~64 GB + ~1 TB):

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

## 2. Point AOA at the server

In `.env`:

```bash
AOA_LLM_PROVIDER=openai_compatible
AOA_LLM_BASE_URL=http://127.0.0.1:8000/v1
AOA_LLM_API_KEY=local
AOA_MODEL=kimi-linear
# AOA_EFFORT is forwarded as thinking_effort when the server supports it
AOA_EFFORT=high
```

`ANTHROPIC_API_KEY` is not required for this provider.

## 3. Verify

```bash
python3 -m aoa.cli doctor
python3 -m aoa.cli team brief
```

Doctor should report `provider=openai_compatible` and a successful LLM ping.
`team brief` runs the opportunity decision aggregation (Alan) against the local
model.

## Notes

- Structured agent outputs use `response_format.json_schema` when the server
  supports it (WASTE does); otherwise AOA falls back to a schema-in-prompt path.
- Risk and fund-manager stages use the same client. Keep Anthropic if you need
  frontier judgment there and only want local speed for briefs — switch
  `AOA_LLM_PROVIDER` per process, or run two environments/profiles.
- This VM/cloud agent does not ship model weights; serve WASTE on hardware that
  holds the container, then set `AOA_LLM_BASE_URL` to that host.
