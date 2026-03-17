# Agent Documentation

## Overview

This agent provides a CLI interface to call an LLM (Large Language Model) with function calling support. It can use three tools to explore documentation, read source code, and query the running backend API, enabling it to answer a wide range of questions about the project.

## Provider and Model

- **Provider**: Qwen Code API (OpenAI-compatible chat completions endpoint)
- **Model**: `qwen3-coder-plus`

The agent uses an OpenAI-compatible API format with function calling (tools) support.

## Configuration

Configuration is loaded from environment variables, with fallback to `.env.agent.secret` and `.env.docker.secret` files in the project root.

### Environment Variables

| Variable | Description | Source | Default |
|----------|-------------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE` | Base URL of the LLM API endpoint | `.env.agent.secret` | - |
| `LLM_MODEL` | Model name for completions | `.env.agent.secret` | `qwen3-coder-plus` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` | - |
| `AGENT_API_BASE_URL` | Base URL for backend API | `.env.docker.secret` or env | `http://localhost:42002` |

The agent automatically loads these values from the `.env` files if they are not already set in the environment. Existing environment variables are not overwritten.

> **Important:** The autochecker runs your agent with different credentials and backend URLs. Never hardcode these values.

## CLI Interface

### Usage

```bash
uv run agent.py "Your question here"
```

### Arguments

| Position | Required | Description |
|----------|----------|-------------|
| 1 | Yes | The user question to ask the LLM |

### Input/Output Format

**Input**: A single string argument containing the question.

**Output**: A single line of valid JSON to `stdout`:

```json
{
  "answer": "The answer text",
  "source": "wiki/git.md#merge-conflict",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git.md\nhttp.md"},
    {"tool": "read_file", "args": {"path": "wiki/git.md"}, "result": "...file contents..."},
    {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "{\"status_code\": 200, ...}"}
  ]
}
```

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The agent's answer to the question |
| `source` | string | Source reference in format `wiki/<file>.md#<section-anchor>` or backend file path |
| `tool_calls` | array | List of tool calls made, each with `tool`, `args`, and `result` |
| `error` | string (optional) | Present only if an error occurred |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing arguments, missing env vars, LLM/HTTP error) |

## Tools

The agent supports three tools for interacting with the project:

### `list_files`

Lists files and directories in a given path.

**Parameters:**

- `path` (string, required): Relative path to a directory (e.g., `"wiki"` or `"backend/app/routers"`)

**Returns:** Newline-separated list of directory entries, or an error string.

**Use case:** Discover wiki documentation files or backend source code structure.

### `read_file`

Reads the contents of a file.

**Parameters:**

- `path` (string, required): Relative path to a file (e.g., `"wiki/git.md"` or `"backend/app/main.py"`)

**Returns:** File contents as a string, or an error string.

**Use case:** Read wiki documentation for conceptual questions or backend source code for implementation details.

### `query_api`

Queries the running backend API.

**Parameters:**

- `method` (string, required): HTTP method (GET, POST, etc.)
- `path` (string, required): API endpoint path (e.g., `/items/`, `/analytics/completion-rate`)
- `body` (string, optional): JSON string for request body (for POST/PUT requests)
- `auth` (boolean, optional): Whether to send authentication header. Default: `true`. Set to `false` to test unauthenticated access.

**Returns:** JSON string with `status_code` and `body` fields, or an error string.

**Use case:** Get live system data (item counts, analytics), test HTTP status codes, or reproduce API errors for bug diagnosis.

**Authentication:** Uses `LMS_API_KEY` from environment variables, sent as `Authorization: Bearer <key>`.

## Path Security

The file tools (`list_files`, `read_file`) enforce strict path security:

1. **No absolute paths**: Paths must be relative to the project root.
2. **No path traversal**: Paths containing `..` segments are rejected.
3. **Root containment**: Resolved paths must be within the project root directory.
4. **Type checking**: `list_files` requires a directory; `read_file` requires a file.

Invalid paths return an error string instead of raising exceptions.

## Agentic Loop

The agent operates in a loop:

1. **Initial request**: Sends the user's question with tool schemas to the LLM.
2. **Tool execution**: If the LLM returns tool calls:
   - Execute each tool and collect results.
   - Append tool results as `tool` role messages.
   - Continue to the next iteration.
3. **Final answer**: When the LLM returns no tool calls, extract the answer from the content.
4. **Limit**: Maximum of **10 tool calls** per request to prevent infinite loops.

### System Prompt Strategy

The system prompt guides the LLM on tool selection:

- **Wiki/documentation questions** → `list_files` on `wiki/`, then `read_file` on relevant `.md` files.
- **Backend implementation questions** → `list_files` on `backend/app/`, then `read_file` on relevant `.py` files.
- **Live data questions** (counts, scores, analytics) → `query_api`.
- **HTTP status code questions** → `query_api` (with `auth=false` for unauthenticated tests).
- **Bug diagnosis questions** → `query_api` to reproduce the error, then `read_file` on the failing source code.

The LLM is instructed to respond with a JSON object containing `answer` and `source` fields when it has enough information.

## Error Handling

The agent handles the following error scenarios:

- **Missing question**: Prints usage help to `stderr`, exits with code 1.
- **Missing environment variables**: Lists missing variables, exits with code 1.
- **Network errors**: Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **HTTP errors** (non-2xx responses): Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **Timeout** (>40 seconds for LLM, >30 seconds for API): Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **Malformed JSON response**: Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **Max tool calls reached**: Returns partial results with a message indicating the limit was reached.

## Lessons Learned

Building this agent involved several iterations to handle the diverse question types in the benchmark:

1. **Tool descriptions matter**: Initially, the LLM would call `read_file` for API data questions. Adding explicit guidance in tool descriptions (e.g., "Use this for data-dependent questions") improved tool selection.

2. **Handling `content: null`**: When the LLM returns tool calls, the `content` field is often `null` (not missing). Using `(msg.get("content") or "")` instead of `msg.get("content", "")` prevents crashes.

3. **Authentication flexibility**: The `auth` parameter in `query_api` allows testing unauthenticated access, which is essential for questions like "What status code does `/items/` return without auth?"

4. **Environment variable defaults**: The `AGENT_API_BASE_URL` defaults to `http://localhost:42002` (the Caddy proxy port), but the autochecker injects different values. Reading from environment variables ensures flexibility.

5. **Source field handling**: For wiki and source code questions, the `source` field should contain the file path. For API data questions, it's optional. The system prompt now explicitly guides this.

6. **Multi-step diagnosis**: Questions about bugs (e.g., ZeroDivisionError in completion-rate) require chaining `query_api` to reproduce the error, then `read_file` to examine the source. The agentic loop handles this naturally.

## Benchmark Performance

The agent is tested against 10 local questions and 10 hidden questions covering:

- Wiki lookup (branch protection, SSH connection)
- System facts (web framework, API routers)
- Data queries (item count, status codes)
- Bug diagnosis (ZeroDivisionError, TypeError)
- Reasoning (request lifecycle, ETL idempotency)

**Final eval score**: To be updated after running `uv run run_eval.py`.

## Limitations

1. **Single-turn**: Each invocation is independent. There is no conversation state or memory between calls.
2. **No streaming**: Responses are received and printed in full after the LLM completes generation.
3. **Local files only**: Tools can only access files within the project root.
4. **UTF-8 only**: `read_file` cannot read non-UTF-8 encoded files.
5. **Tool call budget**: Maximum 10 tool calls per request.

## File Structure

```
.
├── agent.py              # Main agent script
├── .env.agent.secret     # LLM configuration (not versioned)
├── .env.docker.secret    # Backend API configuration (not versioned)
├── .env.agent.example    # Example LLM configuration template
├── .env.docker.example   # Example backend configuration template
├── AGENT.md              # This documentation
├── wiki/                 # Documentation files the agent can read
│   ├── git.md
│   ├── http.md
│   └── ...
├── backend/              # Backend source code the agent can read
│   └── app/
│       ├── main.py
│       ├── routers/
│       └── ...
└── tests/
    └── test_agent_task2.py  # Regression tests with HTTP stub server
```
