# Happy · Personal intelligence

A Python, local-first personal workspace with an original JARVIS-inspired dashboard, **100 AI instruction presets**, **12 executable offline utilities**, public-web tools, persistent conversations, a knowledge library, and background research workflows.

**No model is installed or required for the offline features.** The existing TinyLlama integration remains optional. Without a model, Happy returns retrieved source excerpts, not pretend AI responses. Skills are instructions for a model, not 100 separately trained experts.

## Start

Requires Python 3.10+ (tested with 3.11).

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
python -m happy
```

Open **http://localhost:8000**. The launcher binds to localhost by default. For a container, LAN, or Arena preview:

```bash
python -m happy --host 0.0.0.0 --port 8000
```

`pip install -r requirements.txt` also works when running from this repository. API reference: `/docs`. Health endpoint: `/healthz`. Run **one server worker**: research scheduling and password sessions are process-local.

## Features

| Area | Implemented behavior |
| --- | --- |
| Dashboard | Responsive holographic core, navigation, real backend/model state, saved-memory count, UTC clock, reduced-motion support |
| Skills | 100 searchable instruction presets in 10 categories; select a preset to open chat |
| Conversation | SQLite persistence, reload restore, export, clear, optional web search and saved-note context |
| Offline tools | Safe arithmetic, JSON formatting, CSV → JSON, text statistics, keyword extraction, extractive summary, text diff, Base64 encode/decode, SHA-256, URL inspection, line deduplication |
| Knowledge | Create, edit, delete, search, source provenance, `.txt`/`.md` loading, JSON export/import with duplicate skipping |
| Agents | Web or saved-knowledge research, up to two simultaneous runs, progress, cancellation, retry, delete, persistent history, restart recovery |
| Web explorer | Live search, public HTML/text page reading, links and source saving |
| Access | Optional password gate, 8-hour HTTP-only sessions, logout, login throttling, same-origin mutation checks, request-size caps, security headers |

The offline tool engine uses deterministic Python functions, not `eval`, arbitrary code execution, or a language model. Extractive summaries select sentences from the input; they do not create new claims. URL inspection does not contact websites. Decorative signal bars are artwork, not CPU telemetry.

### Try a complete workflow without a model or internet

1. In **Knowledge**, save a note titled “Solar energy” containing facts about solar panels.
2. In **Agents**, select **Saved knowledge · offline** and research “solar energy”.
3. Review the matching source excerpts, then explicitly save the brief if useful.
4. Ask a question containing “solar energy” in **Conversation** to retrieve the saved context.
5. Reload or restart: notes, chat, and research history remain.
6. In **Offline tools**, run the calculator, format JSON, or summarize pasted text; copy, download, or save the result.

Text/Markdown document loading fills the editor for review and never saves automatically. Notes are limited to 30,000 characters. Knowledge imports accept Happy JSON backups (version 1), up to 1,000 notes and 32 MB per request. Other request bodies are capped at 128 KB. Exact duplicate imports are skipped; existing notes are not overwritten.

## Password protection

By default, local mode has **no password**. Anyone who can reach the server can access its data. Set a strong password before sharing access:

```bash
# Set HAPPY_PASSWORD in your shell or secret manager, then start Happy.
export HAPPY_PASSWORD='replace-with-a-long-unique-password'
python -m happy --host 0.0.0.0
```

Do not commit a real password. `.env` is ignored; `.env.example` is a template. The Python launcher reads environment variables, **not** `.env` automatically. Docker Compose reads `.env`.

The password is checked on the server and is never sent back to the browser. Session tokens are random, stored hashed in server memory, expire after eight hours, and are invalidated by restart or a password change. Cookies are HTTP-only, SameSite Strict, and Secure when the app sees HTTPS. Use a properly configured HTTPS reverse proxy for remote deployment, and only trust forwarding headers from that proxy. Login throttling is process-local, not a replacement for edge protection. This remains a **single-user app**, not a production multi-tenant identity system.

Do not open unauthenticated LAN/public deployments. The Arena preview stays in local mode unless you configure a password. An embedded preview may have browser-specific cookie restrictions; open its direct URL if sign-in cannot persist.

## Docker

```bash
cp .env.example .env
# Edit .env and set HAPPY_PASSWORD before sharing the server.
docker compose up --build -d
```

Compose binds to `127.0.0.1:8000`, runs the app as a non-root user, and keeps SQLite data in the `happy-data` named volume. The image intentionally does not install or download a language model. Stop with `docker compose down`; **do not add `-v` unless you intend to delete your data**. Docker configuration is included; a Docker daemon was not available for a runtime test in the development sandbox.

## Persistence and backups

- `HAPPY_DB` selects the SQLite file; default: `happy.sqlite3` in the working directory.
- Chat, notes, and research history are persisted; session tokens are not.
- Knowledge export is JSON. Conversation export is a readable text transcript. Keep exports private.
- For a full workspace backup, stop the server and copy the SQLite database. Restore it to the `HAPPY_DB` path before startup.
- Interrupted research is marked on restart, not silently resumed. Retry creates a new run and preserves the old one.
- Cancellation is cooperative: it takes effect after the current network/inference operation returns.
- Only finished runs can be deleted. Deleting research does not delete knowledge saved from it.

## Optional TinyLlama integration (left separate)

The app supports `tinyllama-1.1b-chat-v1.0.Q2_K.gguf` through `llama-cpp-python`. No cloud API key is used. The existing setup commands are available in Settings:

```bash
pip install llama-cpp-python
python scripts/download_model.py
# Restart Happy afterward.
```

The downloader explicitly fetches approximately 480 MB from TheBloke's TinyLlama-1.1B-Chat-v1.0-GGUF Hugging Face repository. See its model card/license. It validates the GGUF header, not a cryptographic checksum. Native installation may require CMake and a C++ compiler or a platform-specific wheel. Allow roughly 1–2 GB free RAM. Set `HAPPY_MODEL` to an alternative GGUF path. Binaries are ignored by Git.

Model loading uses a background thread. CPU inference is serialized with a 2048-token context and Zephyr chat format. TinyLlama is small and can hallucinate or perform poorly on reasoning, coding, math, and citations. **Model execution was not validated in this sandbox; the model remains uninstalled.**

## Browsing, privacy, and limits

Web search uses DDGS; pages use HTTPX and BeautifulSoup. Search engines/websites can block or throttle requests. Errors are visible; Happy does not substitute fictional results. Live outbound requests failed TLS negotiation in the development sandbox, so live external search/page availability remains environment-dependent. Backend tests cover mocked successful and failed fetches.

Page fetching permits only public HTTP(S) on standard ports, rejects private/reserved addresses and credentials, pins the validated IP, rechecks every redirect, limits response size, and applies timeouts. For exposed installations, also restrict outbound traffic with a firewall. Research tools are read-only: no purchases, shell access, account login, arbitrary filesystem writes, or autonomous actions. Retrieved content can contain prompt injection; verify outputs and sources.

“Learning” means storing and retrieving knowledge, **not** retraining model weights or guaranteeing universal expertise. AI skill responses require a functioning model; the offline tools do not. Web requests leave the device when explicitly requested. Fonts load from Google Fonts with local fallbacks. Inference, notes, chat, and tool processing remain local.

## Tests

```bash
python -m pytest -q
npm install --prefix .cache/ui-tests --no-audit --no-fund jsdom
NODE_PATH=.cache/ui-tests/node_modules node scripts/test_ui.cjs
```

Backend tests cover persistence, tool results and invalid input, note editing/import, conversation, URL guards and DNS pinning, research cancellation/retry/delete, restart recovery, password protection, rate limits, origin checks, and request limits. DOM tests exercise UI wiring with mocked API results.

A real Chromium test is included in `scripts/test_browser.cjs`. It must target a **disposable**, password-protected workspace because it creates and edits data:

```bash
npm install --prefix .cache/ui-tests --no-audit --no-fund playwright-core
# Start a separate test server in another terminal with a temporary HAPPY_DB and HAPPY_PASSWORD.
HAPPY_TEST_URL=http://127.0.0.1:8001 HAPPY_TEST_PASSWORD='your-test-password' \
  CHROME_PATH=/path/to/chromium NODE_PATH=.cache/ui-tests/node_modules \
  node scripts/test_browser.cjs
```

Without `CHROME_PATH`, the script can use the optional `@sparticuz/chromium` package; its shared-library prerequisites must be present. The test checks desktop/mobile layout, login/logout, tools, note editing, backup/import, offline research, retry/delete, and persisted chat against the real backend. Screenshots are scratch artifacts under `.cache/screenshots`, not tracked assets. GitHub Actions runs the backend and DOM suites.
