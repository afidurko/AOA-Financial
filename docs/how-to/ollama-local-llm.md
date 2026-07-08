# Run the swarm on a local LLM (Ollama)

Point the agent swarm at a local [Ollama](https://ollama.com) model so it reasons
with **no API key and no per-token cost**, fully offline. Anthropic remains the
default; this only changes the reasoning backend, not trading logic or guardrails.

## 1. Install Ollama and pull a model

```bash
# Install from https://ollama.com/download, then:
ollama pull llama3.1        # or: qwen2.5, mistral-nemo, gpt-oss, …
ollama serve                # serves the OpenAI-compatible API on :11434
```

A model with solid JSON/instruction following is recommended — the agents request
structured JSON output. `llama3.1` (8B) works; larger models follow the schema
more reliably.

## 2. Install the OpenAI-compatible client

Ollama speaks the OpenAI Chat Completions protocol, so the swarm reaches it
through the `openai` SDK:

```bash
pip install -e ".[openai]"      # add ,dev,web as needed
```

## 3. Configure the provider

In `.env` (or as environment variables):

```bash
AOA_LLM_PROVIDER=ollama
AOA_MODEL=llama3.1
# Optional — only if Ollama runs elsewhere. Defaults to http://localhost:11434/v1
# AOA_LLM_BASE_URL=http://localhost:11434/v1
```

No `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is required for the `ollama` provider.

## 4. Verify

```bash
python3 -m aoa.cli doctor --offline   # confirms provider/model wiring
python3 -m aoa.cli doctor             # pings the model (needs Ollama running)
```

`doctor --offline` should print:

```
✓ LLM provider: ollama | model: llama3.1 | http://localhost:11434/v1
```

With Ollama running, `doctor` adds:

```
✓ LLM reachable (provider=ollama, model=llama3.1).
```

## 5. Run

```bash
python3 -m aoa.cli run          # single team-coordinated cycle
```

The brokerage still needs to be reachable for live data and orders (Moomoo OpenD
or Alpaca) — Ollama only replaces the reasoning engine. Keep `AOA_ENV=paper-dry`
until you deliberately move to live trading.

## Notes

- **`ollama` is the only key-free *and* cost-free provider.** `openai` uses the
  same code path but bills through your chosen vendor/gateway.
- Structured output uses OpenAI JSON mode with an automatic non-JSON-mode retry,
  so smaller local models still work; if a model returns prose, the client
  extracts the first JSON object before failing.
- Any OpenAI-compatible server works the same way (LM Studio, vLLM, a proxy):
  set `AOA_LLM_PROVIDER=openai`, `AOA_LLM_BASE_URL=<url>`, and a token in
  `OPENAI_API_KEY`.
