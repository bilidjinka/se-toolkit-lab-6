# Task 3 Plan – The System Agent

## Goal

Extend the Task 2 documentation agent so it can query the running backend API in addition to reading local files. This enables:

- **Static system facts**: framework, ports, expected status codes (from source or live API).
- **Data-dependent answers**: item counts, analytics outputs (from live API).

The agentic loop remains the same: the model decides which tool(s) to call, the CLI executes them, and the model produces the final answer.

## Tool: `query_api`

### Schema

Register a third function-calling tool alongside `list_files` and `read_file`:

- **Name**: `query_api`
- **Parameters**:
  - `method` (string, required) — e.g. `GET`, `POST`
  - `path` (string, required) — e.g. `/items/`
  - `body` (string, optional) — JSON string for the request body
  - (Optional extension for robustness) `auth` (boolean) — when `false`, do not send auth header (useful for “what happens without auth?” questions)
- **Returns**: a JSON **string** like:
  - `{"status_code": 200, "body": {...}}`

### Configuration and authentication

- Read backend base URL from `AGENT_API_BASE_URL`, defaulting to `http://localhost:42002`.
- Read backend key from `LMS_API_KEY` (environment variable). Do **not** use `LLM_API_KEY`.
- Send authentication as:
  - `Authorization: Bearer <LMS_API_KEY>` (matches backend `HTTPBearer` auth dependency)

### Failure behavior

Never raise uncaught exceptions from the tool; return an error string or a JSON string with an error field so the LLM can react.

## System prompt strategy

Update the system prompt to teach the model when to use which tool:

- **Wiki questions** → `list_files` + `read_file` under `wiki/`.
- **Backend implementation questions** → `read_file` on `backend/` (source of truth).
- **Live system/data questions** (counts, status codes, analytics outputs) → `query_api`.
- Encourage multi-step diagnosis: query an endpoint, read the failing router code, explain the bug.

## Implementation steps

- Update `agent.py`
  - Add `query_api` tool schema.
  - Implement `_tool_query_api` using `httpx` with:
    - base URL: `AGENT_API_BASE_URL` (default localhost)
    - `Authorization` header when `auth` is not explicitly `false`
    - JSON parsing for request `body` when provided
    - JSON parsing for response body when possible, otherwise return text
  - Keep security rules for file tools unchanged.
- Update `AGENT.md`
  - Document `query_api`, auth, and how the model chooses tools.
  - Include benchmark lessons learned and final score (≥ 200 words).

## Benchmark iteration

Run:

```bash
uv run run_eval.py
```

Then iterate:

- Use the failure hint to decide whether to adjust:
  - tool schema descriptions (to steer tool choice),
  - prompt instructions (to encourage chaining tools),
  - `query_api` behavior (auth/base URL/body parsing),
  - or file-reading paths for source-code questions.

### Initial benchmark run (to be filled after first run)

- **Initial score**: 0/10 (runner could not start)
- **First failure**: `run_eval.py` exited early due to missing required environment variables:
  `AUTOCHECKER_API_URL`, `AUTOCHECKER_EMAIL`, `AUTOCHECKER_PASSWORD`.
- **Iteration strategy**:
  - When credentials are available, run `uv run run_eval.py` once to get the first failing question.
  - Fix one failure at a time (tool usage, prompt steering, or tool implementation), then rerun with `--index N` for fast feedback.

### Benchmark iteration log

1. **Issue**: Agent exited with code 1 for all questions
   - **Cause**: `.env.agent.secret` had placeholder values (`<qwen-api-port>`)
   - **Fix**: Set up Qwen Code API on VM and configured `.env.agent.secret` with:
     - `LLM_API_BASE=http://localhost:42005/v1`
     - `LLM_API_KEY=123456789`
     - `LLM_MODEL=coder-model`

2. **Issue**: LLM returned 500 error after first tool call
   - **Cause**: Agent was not appending the assistant message with `tool_calls` before the tool response message
   - **Fix**: Added `messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})` before appending tool results

3. **Issue**: `qwen3-coder-plus` and `qwen3-coder-flash` models didn't support function calling well
   - **Cause**: These models output tool calls as text content instead of using `tool_calls` field
   - **Fix**: Changed to `coder-model` which properly supports function calling

4. **Verified working questions**:
   - ✅ "What is 2+2?" → Returns correct answer
   - ✅ "What files are in the backend directory?" → Uses `list_files`, returns answer
   - ✅ "What Python web framework does this project use?" → Uses `list_files` + `read_file`, returns "FastAPI" with source
   - ✅ "According to the project wiki, what steps are needed to protect a branch?" → Uses `list_files` + `read_file`, returns detailed steps
   - ✅ "What HTTP status code does /items/ return without auth?" → Uses `query_api` with `auth=false`, reads source code, returns "401"

5. **Known limitation**: Questions requiring a running backend API (item count, completion-rate) will work when the autochecker runs with its backend, but fail locally because the backend is not running.
