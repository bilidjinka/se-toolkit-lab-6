# Agent Documentation

## Overview

This agent provides a CLI interface to call an LLM (Large Language Model) and get answers to user questions. It is designed for Task 1 of the software engineering toolkit lab, which focuses on making basic LLM calls from code.

## Provider and Model

- **Provider**: Qwen Code API (OpenAI-compatible chat completions endpoint)
- **Model**: `qwen3-coder-plus`

The agent uses an OpenAI-compatible API format, making it compatible with various LLM providers that support this standard.

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
{"answer": "The answer text", "tool_calls": []}
```

On error, the output includes an `error` field:

```json
{"answer": "", "tool_calls": [], "error": "Error description"}
```

Error details are also printed to `stderr` for debugging.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing arguments, missing env vars, LLM/HTTP error) |

### Examples

```bash
# Ask a simple question
uv run agent.py "What does REST stand for?"

# Ask a coding question
uv run agent.py "How do I reverse a string in Python?"
```

## Limitations (Task 1)

This implementation has the following limitations:

1. **No tools**: The `tool_calls` field is always an empty list. Tool use is not implemented.
2. **Single-turn**: Each invocation is independent. There is no conversation state or memory between calls.
3. **No streaming**: Responses are received and printed in full after the LLM completes generation.
4. **No conversation history**: Only the current question is sent to the LLM, along with a system prompt.

## Error Handling

The agent handles the following error scenarios:

- **Missing question**: Prints usage help to `stderr`, exits with code 1.
- **Missing environment variables**: Lists missing variables, exits with code 1.
- **Network errors**: Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **HTTP errors** (non-2xx responses): Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **Timeout** (>40 seconds): Returns JSON with `error` field, logs details to `stderr`, exits with code 1.
- **Malformed JSON response**: Returns JSON with `error` field, logs details to `stderr`, exits with code 1.

## File Structure

```
.
├── agent.py              # Main agent script
├── .env.agent.secret     # LLM configuration (not versioned)
├── .env.agent.example    # Example configuration template
└── AGENT.md              # This documentation
```
