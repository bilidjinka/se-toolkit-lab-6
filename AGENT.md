# Agent Documentation

## Overview

This agent provides a CLI interface to call an LLM (Large Language Model) with function calling support. It can use tools to explore and read documentation files from the local repository, enabling it to answer questions based on the project's wiki.

## Provider and Model

- **Provider**: Qwen Code API (OpenAI-compatible chat completions endpoint)
- **Model**: `qwen3-coder-plus`

The agent uses an OpenAI-compatible API format with function calling (tools) support.

## Configuration

Configuration is loaded from `.env.agent.secret` in the project root. This file uses a simple `KEY=VALUE` format:

```env
LLM_API_KEY=your-api-key-here
LLM_API_BASE=http://<vm-ip>:<port>/v1
LLM_MODEL=qwen3-coder-plus
```

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `gochamp` |
| `LLM_API_BASE` | Base URL of the LLM API endpoint | `http://192.168.1.100:42005/v1` |
| `LLM_MODEL` | Model name to use for completions | `qwen3-coder-plus` |

The agent automatically loads these values from `.env.agent.secret` if they are not already set in the environment. Existing environment variables are not overwritten.

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
    {"tool": "read_file", "args": {"path": "wiki/git.md"}, "result": "...file contents..."}
  ]
}
```

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The agent's answer to the question |
| `source` | string | Source reference in format `wiki/<file>.md#<section-anchor>` |
| `tool_calls` | array | List of tool calls made, each with `tool`, `args`, and `result` |
| `error` | string (optional) | Present only if an error occurred |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing arguments, missing env vars, LLM/HTTP error) |

### Examples

```bash
# Ask about merge conflicts
uv run agent.py "How do I resolve a merge conflict in git?"

# Ask about REST API design
uv run agent.py "What are the principles of REST API design?"
```

## Tools

The agent supports two tools for interacting with the local repository:

### `list_files`

Lists files and directories in a given path.

**Parameters:**

- `path` (string, required): Relative path to a directory (e.g., `"wiki"` or `"wiki/subdir"`)

**Returns:** Newline-separated list of directory entries, or an error string.

**Example:**

```json
{"tool": "list_files", "args": {"path": "wiki"}, "result": "git.md\nhttp.md\nlinux.md"}
```

### `read_file`

Reads the contents of a file.

**Parameters:**

- `path` (string, required): Relative path to a file (e.g., `"wiki/git.md"`)

**Returns:** File contents as a string, or an error string.

**Example:**

```json
{"tool": "read_file", "args": {"path": "wiki/git.md"}, "result": "# Git\n\nGit is a distributed..."}
```

## Path Security

Both tools enforce strict path security to prevent access outside the repository:

1. **No absolute paths**: Paths must be relative to the project root.
2. **No path traversal**: Paths containing `..` segments are rejected.
3. **Root containment**: Resolved paths must be within the project root directory.
4. **Type checking**: `list_files` requires a directory; `read_file` requires a file.

Invalid paths return an error string instead of raising exceptions.

## Agentic Loop

The agent operates in a loop:

1. **Initial request**: Sends the user's question to the LLM with tool schemas.
2. **Tool execution**: If the LLM returns tool calls:
   - Execute each tool and collect results.
   - Append tool results as `tool` role messages.
   - Continue to the next iteration.
3. **Final answer**: When the LLM returns no tool calls, extract the answer.
4. **Limit**: Maximum of **10 tool calls** per request to prevent infinite loops.

### System Prompt Strategy

The system prompt instructs the LLM to:

- Use `list_files` to discover wiki files.
- Use `read_file` to retrieve relevant content.
- Respond with a JSON object containing `answer` and `source`.
- Include a section anchor in the source when applicable (e.g., `wiki/git.md#merge-conflict`).

## Error Handling

The agent handles the following error scenarios:

- **Missing question**: Prints usage help to `stderr`, exits with code 1.
- **Missing environment variables**: Lists missing variables, exits with code 1.
- **Network errors**: Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **HTTP errors** (non-2xx responses): Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **Timeout** (>40 seconds): Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **Malformed JSON response**: Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **Max tool calls reached**: Returns partial results with a message indicating the limit was reached.

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
├── .env.agent.example    # Example configuration template
├── AGENT.md              # This documentation
└── wiki/                 # Documentation files the agent can read
    ├── git.md
    ├── http.md
    └── ...
```
