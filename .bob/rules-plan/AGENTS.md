# Project Architecture Rules (Non-Obvious Only)

- Stack is Google ADK v2 (Agent Development Kit) — agents are defined as Python classes/functions registered with the ADK runtime, not plain FastAPI routes.
- The ADK dev server (`adk web`) wraps FastAPI/Uvicorn internally — do NOT add a separate FastAPI app unless intentionally extending the ADK server.
- `google-genai` 2.19 is the Gemini client; `google-adk` wraps it for agent tool-calling — use ADK's model abstraction rather than calling `google-genai` directly inside agents.
- `authlib` + `joserfc` are installed, suggesting OAuth2/JWT-based auth will be needed (likely for the ADK web UI or API layer).
- `aiohttp` + `aiosqlite` point to an async-first architecture — plan all I/O-bound operations as async from the start.
- No database migrations tool is installed (no Alembic) — if SQLite schema evolves, plan a migration strategy early.
