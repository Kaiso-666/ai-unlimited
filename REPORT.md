# Survey — "free AI chat, no login" sites

Date: 2026-11-07. Method: load each page in a real Firefox session, extract script
bundles and inline JS, drive the composer if one exists, replay the generation
endpoint with a canary prompt (`Reply with exactly: OK`) from the page origin, then
vary payload shapes. No credentials were guessed, bought, or brute-forced — only
what the sites hand to anonymous visitors is reported.

`AUTH` = what the endpoint actually checks. `KEYLESS` = reachable without an
account; `yes*` = no account, but a client-side challenge must be solved.

| site | endpoint | auth | upstream | keyless | status |
|---|---|---|---|---|---|
| flatai.org | `POST /wp-admin/admin-ajax.php?action=my_chatbot` | account session | ? | no | 403 `signup_required` |
| freeaichat.app | — | — | — | n/a | static Android landing page |
| pixeldojo.ai | `POST /api/help-system/chat` | none | ? | yes | 200 — support bot, not the advertised chat |
| app.unlimitedai.chat | `POST /api/chat` | device id | ? | yes | 200 NDJSON deltas |
| theturbochat.com | `POST /api/chat/message` | none (guest 15/day) | `openai / gpt-4o-mini` | yes | 200 JSON |
| minitoolai.com | `POST /gpt-ai/chatgpt_stream.php` → `GET …?streamtoken=` | hardcoded `utoken` + Turnstile | `gpt-6-luna` | yes* | 200 SSE |
| aitools.aiting.com | directory → free-ai-chat.com `POST /api/chat` | guest session | `openai/gpt-6-luna`, `gemini-3.8-flash`, `claude-opus-5.5` | unknown | 400 `bad_request:api` |
| writecream.com | `POST /api/generate` | `X-Recaptcha-Token` + `wc_sid` | ? | no | 400/403 captcha |
| free.ai | `POST api.free.ai/v1/chat/` | none | `Qwen/Qwen3-30B-A3B-Instruct` | yes | 200 JSON |
| askai.free | `POST /api/chat/stream` | CSRF/Origin | ? | no | 403 for guests |
| notegpt.io | sign-in wall ("15 free quotas/month") | account | ? | no | modal on send |
| perchance.org | generator iframe `3ed577a8…perchance.org/ai-chat` | ? | ? | unknown | plugin framework, not a REST chat |
| nation.ai | botnation messenger iframe (`appKey`, `website_id`) | appKey | ? | unknown | third-party widget |
| zalt.me | — | — | — | n/a | client-side tools directory |
| feelbetterbot.com | `/api/status`, `/api/tts`, `/api/memory` | anonymous | ? | unknown | no generation call observed |
| atale.ai | `POST /chat-stream` | guest token in localStorage | ? | yes | 200 SSE `content` |
| askaichat.app | — | account | ? | no | blog CTA → /signup |
| talkai.info | `POST /api/sse/` | Cloudflare + 10 req/IP | `gpt-4o-mini` (default) | unknown | 403 challenge |
| surfsense.com | — | — | — | n/a | hosted chat shut down |
| aichatting.net | `POST aga-api.aichatting.net/aigc/v1/chat/completions` | `vToken` visitor cookie | `azure/gpt-5.6-luna` | yes | 200 SSE |
| plai.chat | `POST /api/web/chat/send` | anon session via Turnstile | `NEMOTRON-3.5-SUPER`, `DOTS-3-NOTE`, `NEMOTRON-3-ULTRA` | yes* | 200, answer rendered |
| notrack.ai | `POST /api/dispatch` | same-origin cookie | `notrack-uncensored` | yes | 200 |
| ask-me-ai.app | — | — | — | n/a | static landing page |
| easemate.ai | `POST api.easemate.ai/api2/stream/exec_operation` | anonymous `identity_id` | ? | yes | 200 after `create_pure_session` |
| rewind.ai | — | login required | `qwen/qwen3-30b-a3b` | no | redirect to `/login` |

## Details

### flatai.org/free-ai-chatbot-no-registration
- `POST /wp-admin/admin-ajax.php` `action=my_chatbot`, public `chatbot_nonce=3f1a0e091f`.
- Guest send: `403 {"success":false,"data":{"signup_required":true,"code":"signup_required"}}`;
  the UI opens a signup modal without firing a request.

### freeaichat.app
- 47 KB static marketing page for an Android app; no composer, no app JS, no `/api`.
  `/chat`, `/app`, `/chat/` all serve the same landing page.

### pixeldojo.ai/free-ai-chat-no-login
- `POST /api/help-system/chat` `{messages:[{role,content}], userId}` → `200 text/plain`.
- This is the support bot, not the advertised general chat: no composer on the page,
  "Chat Now" points at `/subscribe`.

### app.unlimitedai.chat
- `POST /api/chat` `{chatId, messages:[{id,role,content,parts}], selectedChatModel,
  turnstileToken, deviceId, locale}`; anonymous `u_device_id` cookie.
- `200 application/x-ndjson`; `{"type":"delta","delta":"…"}` … `{"type":"complete"}`.
- Fabricated `chatId`/`deviceId` accepted; turns are character-streamed.

### theturbochat.com/chatgpt-free-online
- `POST /api/chat/message` `{runtime:"chatgpt", message, language, sourcePage, history}`.
- Guest plan: `plan:"guest"`, `dailyChatLimit:15`; no key, no captcha.
- `{"outputText":"OK","provider":"openai","model":"gpt-4o-mini","fallback":false}`
  plus entitlements/featureFlags.
- Server checks the request principal: content-script XHR → `403 Forbidden origin`,
  page-context `fetch` → 200.

### minitoolai.com/gpt-ai
- Form-encoded fields: `message`, `utoken` (hardcoded
  `5ae2e5fa6651c823d80abfd134a3fa4cedffcc4602b78b7678e38c559b1676ac`),
  `select_model`, `temperature`, `reasoning_effort`, `cft` (Turnstile response).
- Returns a 64-hex `streamtoken`; the answer arrives on
  `EventSource /gpt-ai/chatgpt_stream.php?streamtoken=<token>` using OpenAI
  Responses-style events; `response.created.model` = `gpt-6-luna`.
- Turnstile token is auto-solved and readable from `cf-chl-widget-l3s98_response`.

### aitools.aiting.com/ai/free-ai-chat
- Directory row, not a chat app. Outbound `https://free-ai-chat.com/` (Next.js):
  `POST /api/chat`, guest session from `/api/auth/guest`.
- Bundle constants: `openai/gpt-6-luna`, `google/gemini-3.8-flash`,
  `spacexai/grok-4.7`, `anthropic/claude-opus-5.5`, default `alibaba/qwen3.7-flash`.
- Hand-built AI-SDK bodies → `400 bad_request:api`; exact client body not reproduced.

### writecream.com/ai-chatbot-with-no-sign-up
- `POST /api/generate` `{text, country, user_id}` → `{result}`.
- Requires `X-Recaptcha-Token` (invisible reCAPTCHA
  `6Le4vhosAAAAAJdqA2IOrs-0t0-BDnYOc1gD0rrO`) minted by `/js/recaptcha-inject.js`;
  `/session/init` sets httpOnly `wc_sid`.
- `grecaptcha` never initialized in the test profile; UI shows ~2 results then walls.

### free.ai
- `POST https://api.free.ai/v1/chat/` `{messages, model, stream, lang,
  work_session_id, work_mode}`; anonymous needs no Authorization header.
- `stream:false` → OpenAI `chat.completion` JSON; `stream:true` → SSE.
- `model:"qwen7b"` resolves to `Qwen/Qwen3-30B-A3B-Instruct`.
- `OPTIONS` → 405 (no CORS), so same-origin/server-side only.

### askai.free
- `POST /api/chat/stream` `{messages, modelName, currentPagePath}`, `Accept:
  text/event-stream`; events `delta`/`error`.
- Rejects without `X-CSRF-Token` or matching Origin; guest meta token is empty and
  real UI sends produced no answer. Marketed as no-signup, 403 for guests.

### notegpt.io/ai-chat
- Full Nuxt chat app; on send it opens "Sign In to get 15 free quotas per month".
- Quota plumbing visible: `/api/v2/user/quota?features=ai_chat`, `/api/v2/user/quota-usage`,
  `/api/v2/plan-quota`, `/api/v1/userinfo`.

### perchance.org/ai-chat
- Chat lives in a generator iframe (`3ed577a8ef2db1575c94395be05e8192.perchance.org/ai-chat`)
  driven by perchance's generator/template engine, not a single REST endpoint.
  Static scan only found the platform API (`/api/cv`, `/api/ce`, `/api/alc`) which
  are page/render calls, not inference.

### nation.ai/free-ai
- The "chat" is the Botnation messenger plugin:
  `chatbox.botnation.ai/plugins/messenger?appKey=e9f7a4c2-…&website_id=mi6aYtriOMtio0s2auZc6`.
  Inference happens inside Botnation's platform behind that app key.

### zalt.me/tools
- 64 client-side tools, no composer, no inference calls. Not an AI chat.

### feelbetterbot.com
- Real composer (`textarea` with `@keydown.enter.prevent="send"`), but sends did not
  produce an inference request; visible APIs are `/api/status`, `/api/tts`,
  `/api/memory`, `/api/conversations`, `/api/checkin`.
- Memory is keyed by a client-side word key (`jolly-root-9075`).

### atale.ai
- `POST /chat-stream` `{message, sessionId, conversationHistory, userToken, userLocale}`;
  session from `POST /api/msg/createSession?botId=<id>`, no auth.
- Guest token auto-issued into localStorage `x-auth-token`; `200 text/event-stream`,
  frames `data:{"type":"content","content":"…"}`.
- Roleplay bots override instructions (canary ignored); no model leak.

### askaichat.app/blog/ai-chat-no-sign-up
- Nuxt SEO article. The composer's "Send Prompt" navigates to `/signup`; the
  product itself redirects `/chat` → `/signin`. No generation API on the page.

### talkai.info
- `POST /api/sse/` `{type:"chat", messagesHistory:[{from:"you",content}], settings:{model,temperature}}`.
- Cloudflare 403 ("Attention Required") before inference; UI also reports 10 free
  requests/IP. Default model `gpt-4o-mini`; list includes gpt-5, o3, gemini-2.5-pro,
  claude-4-5-sonnet, deepseek.

### surfsense.com/free
- Hosted anonymous chat is shut down; page says "Gemini 3 free chat has moved to a
  free desktop app". No composer, no chat calls.

### aichatting.net
- `POST https://aga-api.aichatting.net/aigc/v1/chat/completions`
  `{model:"gpt-5.6-luna", stream:true, roleId:0, scene:"chatbot", messages:[…]}`.
- Guest `aichatting.website.visitorId` cookie sent as `vToken`; headers `source:web`,
  `lang:en`, `X-Request-ID`; no Authorization for guests.
- `200 text/event-stream`; SSE `model` field leaks `azure/gpt-5.6-luna`.

### plai.chat
- `POST /api/web/chat/send`; the client model list is `/api/web/models/aliases`.
- Anonymous send works after exchanging a Turnstile token for a short-lived
  anon-session cookie (`auth.js`: "When the cookie is present, /api/web/chat/send
  accepts anonymous requests", 30 s verification timeout).
- UI tiers: FREE / BALANCED / PREMIUM; rerun links: `NEMOTRON-3.5-SUPER`,
  `DOTS-3-NOTE`, `NEMOTRON-3-ULTRA`.

### notrack.ai
- `POST /api/dispatch` `{user_input, mode, model, persona, max_turns, chat_id, …}`
  (same-origin cookie, no account); model id `notrack-uncensored`.
- Chat CRUD on `/api/chat?id=…` (`op=instructions`, `op=delete_from`, `op=carry_start`),
  list on `/api/chats`.
- The page ships an anti-tamper check over `fetch`, `XMLHttpRequest`, `EventSource`,
  `MutationObserver`, `attachShadow`, `appendChild` (integrity check, not a gate).

### ask-me-ai.app/free-ai-chat.html
- Static landing page with JSON-LD FAQ; no composer, no inputs, no API calls.

### easemate.ai/chat-gpt-free
- The SEO page hands off to `/webapp/chat`; the app uses
  `api.easemate.ai/api2/task/identity_id`, `api2/task/query_config`,
  `api2/task/create_pure_session`, then
  `POST api.easemate.ai/api2/stream/exec_operation`.
- Config in the bundle: `wsBase: wss://agent.easemate.ai/nanobot-proxy-socket`,
  `loopaApiBase: https://agent.easemate.ai/loopa-proxy-api`.
- Anonymous identity flow; no login for the free chat.

### rewind.ai/free-ai-no-sign-up
- The hero widget posts to the chat app but immediately redirects to
  `/login/?next=/chat/`; `/chat/?new=1&model=qwen/qwen3-30b-a3b` requires an account.
- Model catalog: `https://api.rewind.ai/v1/models`.

## takeaways

- **Actually keyless with a real model behind it:** `free.ai` (Qwen3-30B),
  `aichatting.net` (azure/gpt-5.6-luna), `theturbochat.com` (gpt-4o-mini),
  `app.unlimitedai.chat`, `atale.ai`, `notrack.ai`, `easemate.ai`.
- **Keyless with a solvable client challenge:** `minitoolai.com` (Turnstile token in
  a hidden input → gpt-6-luna), `plai.chat` (Turnstile → anon session cookie →
  Nemotron-3.5-Super).
- **Fake "no login":** `flatai.org`, `askai.free`, `notegpt.io`, `rewind.ai`,
  `askaichat.app`, `writecream.com` (captcha + wall).
- The recurring pattern is a thin proxy in front of one upstream provider; the
  wrapper's model picker is usually cosmetic, and the upstream name leaks either in
  a response header (`X-Model`) or a `model` field in the JSON/SSE payload.
