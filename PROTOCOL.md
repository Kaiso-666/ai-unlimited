# Protocol notes

Observed 2026-11-07 against the live sites. Everything below was verified by replaying requests outside the browser.

---

## 1. DeepAI chat

### Generation

```
POST https://api.deepai.org/hacking_is_a_serious_crime
Content-Type: multipart/form-data
Origin: https://deepai.org
Referer: https://deepai.org/chat
Cookie: deepai_device_id=<43 base62 chars>
api-key: tryit-<random int>-<32 hex>
```

Fields (all strings):

| field | value |
|---|---|
| `chat_style` | `chat` |
| `language` | `en` |
| `chatHistory` | JSON array of `{role, content}` |
| `model` | model id, see table |
| `session_uuid` | random UUID |
| `sensitivity_request_id` | random UUID (same UUID the page uses for the sensitivity check) |
| `tool_activity_support` | `1` |
| `thinking_image_tool_support` | `1` |
| `hacker_is_stinky` | `very_stinky` |
| `enabled_tools` | `["image_generator","image_editor"]` |
| `memory_enabled` | `true`/`false` |
| `web_access_enabled` | `true`/`false` |
| `sandbox_enabled` | `true`/`false` |
| `thinking_support` | `1` for thinking-capable models |

Response:

* normal models → `200 text/plain`, raw UTF-8 deltas of the answer (not SSE).
* thinking models → `200 application/json {"task_id": "...", "thinking_category": "hidden"}`.
* the POST also sets `sessionid=<...>; Domain=.deepai.org; HttpOnly` — **the task is keyed to that cookie**. A client without a cookie jar gets `404 {"error": "Task not found"}` when polling.

### Thinking task polling

```
GET https://api.deepai.org/check_chat_task_status?type=thinking-task&task_id=<uuid>
Cookie: sessionid=...; deepai_device_id=...
```

```json
{"task_id":"...","status":"PROCESSING","thinking_text":"","answer_text":"",
 "thinking_done":false,"tool_activity":"Thinking…"}
```

Poll ~1.2 s until `status == "COMPLETED"`. `thinking_text` / `answer_text` are cumulative; emit the deltas. `type=thinking_task` is rejected (`400 Unknown task type`).

### Quota and gating

| condition | server answer |
|---|---|
| anonymous allowance spent | `{"status": "anonymous try it exceeded"}` → rotate `deepai_device_id` |
| signed-in free allowance spent | `{"status": "signed in try-it quota exceeded"}` |
| any locked model | `401 {"status": "Only paid accounts can use genius"}` |
| pro account out of credits | `{"status": "pro user out of credits", "credits_remaining": n}` |

Aliases exist: `online → standard`, `onlinegenius → genius`.

### Models (live picker, 2026-11-07)

Free: `standard`, `claude-haiku-5-5`, `deepseek-v4.1-flash`, `gpt-6-luna`, `gemma-4`, `glm-5.3-flash`, `qwen3.8-flash`, `tencent-hy3`, `gpt-oss-120b`, `llama-3.3-70b-instruct`, `llama-3.1-8b-instant`.

Pro (401 anonymously): `genius`, `supergenius`, `claude-opus-5-5`, `gemini-4-argon`, `gpt-6-astra`, `claude-fable-5`, `gpt-6.1-sol`, `gemini-3.8-flash`, `gpt-5.2`, `grok-4.3`, `gpt-4.1`, `chatgpt-4o-latest`, `llama-4-scout`.

Thinking-capable: `supergenius`, `gpt-6.1-sol`, `gpt-6-astra`, `gpt-oss-120b`, `gemini-4-argon`, `claude-opus-5-5`, `claude-fable-5`, `glm-5.3-flash`, `grok-4.3`, `gpt-5.2`.

### Island key

```js
function generateIslandKey() {
  let myrandomstr = Math.round(Math.random() * 1e11) + "";
  const H = /* custom MD5-shaped hash, 64-entry K table = 2^32*sin(i % pi) */;
  return "tryit-" + myrandomstr + "-" + H(
    navigator.userAgent + H(
      navigator.userAgent + H(
        navigator.userAgent + myrandomstr +
        "hackers_become_a_little_stinkier_every_time_they_hack"
      )
    )
  );
}
```

The hash is MD5's structure with a different constant table, `| 15` word-count rounding, length word `8*(len-1)`, and a nibble-reversed hex output. Ported in `providers._hash()`; verified against the page:

| input | page | python |
|---|---|---|
| `test-input` | `b1b4823eb59196bed817194e3b2f7f5b` | same |
| UA (Firefox 160 win64) | `a8ef35c8a2af3caebcd9129932826abc` | same |
| UA+`12345678901`+canary | `9bf97473ee2a5e4a72e8d49db961b05a` | same |

---

## 2. FreeAnonymousAI

```
POST https://www.freeanonymousai.com/api/generate
Content-Type: application/json

{"prompt":"...","tool":"chat","attachments":[],
 "history":[{"role":"user","content":"..."}],
 "selectedModel":"fast|smart|<anything>","thinking":false,"search":false,"stream":true}
```

* `200 text/plain` stream + `X-Model` header with the upstream id.
* `selectedModel` is ignored. Arbitrary values fall back to `pollinations-text/openai` (`gpt-oss-20b`) and return JSON `{"output":...,"type":"text","model":"pollinations-text/openai","creditsUsed":1}`.
* The page's own modes (`auto` / `fast` / `smart` / `✦ Think`) all resolved to `X-Model: gemini/gemini-3.5-flash-lite` in testing. No premium tier is reachable through the API.

---

## 3. Pollinations

```
GET  https://text.pollinations.ai/models
POST https://text.pollinations.ai/openai      # OpenAI chat-completions schema
GET  https://text.pollinations.ai/<prompt>?model=openai
```

Anonymous tier (2026-11-07) exposes exactly one model:

```json
[{"name":"openai-fast","description":"GPT-OSS 20B Reasoning LLM (OVH)",
  "reasoning":true,"tier":"anonymous","tools":true,
  "aliases":["openai","gpt-oss","gpt-oss-20b","ovh-reasoning"]}]
```

Response includes `message.reasoning`; `stream:true` gives SSE.

---

## 4. Site survey

See `REPORT.md`.
