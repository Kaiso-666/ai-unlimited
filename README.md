# ai-unlimited

Direct-API clients for the **DeepAI** chat backend, **FreeAnonymousAI**, and **Pollinations** — no browser, no ads, no analytics, no client-side model pickers. Plus a survey of ~25 "free AI, no login" wrapper sites and what their generation endpoints actually are.

```
python ai_unlimited.py models
python ai_unlimited.py deepai "explain QUIC in 3 lines"
python ai_unlimited.py deepai -i -m deepseek-v4.1-flash
python ai_unlimited.py anon "hello"
python ai_unlimited.py pollinations "hello" -m openai-fast
```

Python 3.10+, standard library only.

## What works

| Provider | Endpoint | Auth | Notes |
|---|---|---|---|
| DeepAI (free models) | `POST api.deepai.org/hacking_is_a_serious_crime` | none (self-rotating device id) | multipart, client-side "island key", streams UTF-8 |
| DeepAI (thinking models) | same + `GET check_chat_task_status` | none | returns `task_id`, poll until `COMPLETED` |
| DeepAI (Pro models) | same | **paid session** | server answers `401 {"status": "Only paid accounts can use genius"}` |
| FreeAnonymousAI | `POST www.freeanonymousai.com/api/generate` | none | JSON, text/plain stream, `X-Model` leaks upstream |
| Pollinations | `POST text.pollinations.ai/openai` | none | OpenAI schema, anonymous tier = `openai-fast` (gpt-oss-20b) |

### DeepAI models

`python ai_unlimited.py models` prints the live table. Free tier (`standard`, `deepseek-v4.1-flash`, `claude-haiku-5-5`, `gpt-6-luna`, `gemma-4`, `glm-5.3-flash`, `qwen3.8-flash`, `tencent-hy3`, `gpt-oss-120b`, `llama-3.3-70b-instruct`, `llama-3.1-8b-instant`) works anonymously.

**Super Genius is not bypassable by request shaping.** `genius`, `supergenius` and every locked frontier entry (`gpt-6-astra`, `claude-opus-5-5`, `claude-fable-5`, `gemini-4-argon`, `gpt-6.1-sol`, `gpt-5.2`, `grok-4.3`, …) return 401 from the server regardless of payload, headers or island key. The check runs on the session, not the form. A paid `Cookie` header is the only way in:

```
python ai_unlimited.py deepai "hi" -m supergenius --cookie "sessionid=...; deepai_device_id=..."
```

## FreeAnonymousAI = Pollinations

`selectedModel` on `/api/generate` is cosmetic: the server ignores it. Custom values fall through to `pollinations-text/openai` (`gpt-oss-20b`) and the response leaks it:

```json
{"output":"OK","type":"text","model":"pollinations-text/openai","creditsUsed":1}
```

Everything else routes to a single upstream (`X-Model: gemini/gemini-3.5-flash-lite`). There is no premium tier reachable through that endpoint. Going straight to Pollinations removes the wrapper and the credit counter.

## Repo layout

```
ai_unlimited.py    CLI (deepai | anon | pollinations | models | -i REPL)
providers.py       clients: DeepAI, FreeAnon, Pollinations + island-key port
PROTOCOL.md        wire format, multipart fields, task polling, hash algorithm
REPORT.md          survey of 25 free-AI-no-login sites: endpoints, auth, upstreams
sites.txt          the surveyed domains
```

## Island key

DeepAI signs each request with `api-key: tryit-<random>-<hash>`, generated in-page by `generateIslandKey()`. It is a client-side obfuscated MD5-shaped hash (custom K table, reversed nibbles) over the user agent and a canary string `hackers_become_a_little_stinkier_every_time_they_hack`. Ported bit-for-bit in `providers._hash()`, verified against the live page on three vectors.

The server does not authenticate the key; it exists to make casual replay annoying. Rotating `deepai_device_id` resets the per-identity message allowance.

## Notes

Not affiliated with DeepAI, FreeAnonymousAI, Pollinations or any surveyed site. Endpoints and model ids drift — `PROTOCOL.md` records what was observed and when.
