#!/usr/bin/env python3
"""Documentation agent that calls an LLM with function calling support.

This script provides a CLI interface to query an LLM (Qwen Code API)
with tool support for list_files, read_file, and query_api operations.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

# Maximum number of tool calls allowed per request
MAX_TOOL_CALLS = 10


def load_env_from_file(env_path: Path) -> dict[str, str]:
    """Load environment variables from a .env file (KEY=VALUE format)."""
    env_vars: dict[str, str] = {}
    if not env_path.exists():
        return env_vars

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key:
                    env_vars[key] = value
    return env_vars


def ensure_env_vars() -> None:
    """Ensure required LLM environment variables are set.

    Loads from .env.agent.secret if not already in os.environ.
    Does not overwrite existing environment variables.
    """
    env_path = Path(__file__).parent / ".env.agent.secret"
    file_env = load_env_from_file(env_path)

    for key in ("LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL"):
        if key not in os.environ and key in file_env:
            os.environ[key] = file_env[key]

    # Also load LMS_API_KEY and AGENT_API_BASE_URL from .env.docker.secret
    docker_env_path = Path(__file__).parent / ".env.docker.secret"
    docker_env = load_env_from_file(docker_env_path)

    for key in ("LMS_API_KEY", "AGENT_API_BASE_URL"):
        if key not in os.environ and key in docker_env:
            os.environ[key] = docker_env[key]


def validate_env_vars() -> None:
    """Validate that required environment variables are present."""
    missing = []
    for key in ("LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL"):
        if key not in os.environ:
            missing.append(key)

    if missing:
        print(
            f"Error: Missing required environment variables: {', '.join(missing)}",
            file=sys.stderr,
        )
        print(
            "Please ensure .env.agent.secret exists with LLM_API_BASE, LLM_API_KEY, and LLM_MODEL.",
            file=sys.stderr,
        )
        sys.exit(1)


def get_project_root() -> Path:
    """Get the project root directory (parent of agent.py)."""
    return Path(__file__).parent


def validate_path(path_str: str) -> tuple[bool, str]:
    """Validate that a path is safe and within the project root.

    Args:
        path_str: The path string to validate.

    Returns:
        A tuple of (is_valid, error_message).
        If valid, error_message is empty.
    """
    # Reject absolute paths
    if os.path.isabs(path_str):
        return False, "Absolute paths are not allowed"

    # Reject paths containing .. segments
    if ".." in path_str.split(os.sep):
        return False, "Path traversal (..) is not allowed"

    # Resolve the path and check it's within project root
    project_root = get_project_root()
    try:
        candidate = project_root / path_str
        resolved = candidate.resolve()
        if not resolved.is_relative_to(project_root.resolve()):
            return False, "Path is outside the project root"
    except (ValueError, OSError) as e:
        return False, f"Invalid path: {e}"

    return True, ""


def tool_list_files(args: dict[str, Any]) -> str:
    """List files in a directory.

    Args:
        args: Dictionary with 'path' key (e.g., 'wiki' or '<relative-dir>').

    Returns:
        Newline-separated directory entries or an error string.
    """
    path = args.get("path", "")

    # Validate the path
    is_valid, error_msg = validate_path(path)
    if not is_valid:
        return f"Error: {error_msg}"

    project_root = get_project_root()
    target_path = project_root / path

    # Check if path exists
    if not target_path.exists():
        return f"Error: Path does not exist: {path}"

    # Check if it's a directory
    if not target_path.is_dir():
        return f"Error: Path is not a directory: {path}"

    # List directory contents
    try:
        entries = []
        for entry in sorted(target_path.iterdir()):
            suffix = "/" if entry.is_dir() else ""
            entries.append(f"{entry.name}{suffix}")
        return "\n".join(entries)
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except OSError as e:
        return f"Error: {e}"


def tool_read_file(args: dict[str, Any]) -> str:
    """Read the contents of a file.

    Args:
        args: Dictionary with 'path' key (relative file path).

    Returns:
        File contents or an error string.
    """
    path = args.get("path", "")

    # Validate the path
    is_valid, error_msg = validate_path(path)
    if not is_valid:
        return f"Error: {error_msg}"

    project_root = get_project_root()
    target_path = project_root / path

    # Check if path exists
    if not target_path.exists():
        return f"Error: File does not exist: {path}"

    # Check if it's a file
    if not target_path.is_file():
        return f"Error: Path is not a file: {path}"

    # Read the file
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except UnicodeDecodeError:
        return f"Error: Unable to decode file (not UTF-8): {path}"
    except OSError as e:
        return f"Error: {e}"


def tool_query_api(args: dict[str, Any]) -> str:
    """Query the backend API.

    Args:
        args: Dictionary with 'method', 'path', and optional 'body' and 'auth' keys.

    Returns:
        JSON string with status_code and body, or an error string.
    """
    method = args.get("method", "GET").upper()
    path = args.get("path", "")
    body_str = args.get("body")
    use_auth = args.get("auth", True)

    if not path:
        return json.dumps({"error": "Missing 'path' parameter"})

    # Get API base URL from environment, default to localhost
    api_base = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")
    lms_api_key = os.environ.get("LMS_API_KEY", "")

    url = f"{api_base}{path}"

    headers = {}
    if use_auth and lms_api_key:
        headers["Authorization"] = f"Bearer {lms_api_key}"
    headers["Content-Type"] = "application/json"

    # Parse body if provided
    json_body = None
    if body_str:
        try:
            json_body = json.loads(body_str)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON in body parameter"})

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, url, headers=headers, json=json_body)
            result = {
                "status_code": response.status_code,
                "body": response.text,
            }
            # Try to parse body as JSON
            try:
                result["body"] = response.json()
            except (json.JSONDecodeError, ValueError):
                pass
            return json.dumps(result)
    except httpx.TimeoutException:
        return json.dumps({"error": "Request timed out"})
    except httpx.RequestError as e:
        return json.dumps({"error": f"Request failed: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {e}"})


# Map of tool names to implementations
TOOLS_IMPL: dict[str, callable] = {
    "list_files": tool_list_files,
    "read_file": tool_read_file,
    "query_api": tool_query_api,
}


def get_tool_schemas() -> list[dict[str, Any]]:
    """Get the OpenAI-compatible tool schemas for function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories in a given path within the repository. Use this to discover wiki documentation files or backend source code structure.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to a directory (e.g., 'wiki', 'backend/app/routers').",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file within the repository. Use this to read wiki documentation for conceptual questions or backend source code for implementation details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to a file (e.g., 'wiki/git.md', 'backend/app/main.py').",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Query the running backend API to get live system data, item counts, analytics, or test authentication behavior. Use this for data-dependent questions (counts, scores) or to check HTTP status codes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method (GET, POST, etc.). Default: GET",
                        },
                        "path": {
                            "type": "string",
                            "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate').",
                        },
                        "body": {
                            "type": "string",
                            "description": "JSON string for request body (optional, for POST/PUT).",
                        },
                        "auth": {
                            "type": "boolean",
                            "description": "Whether to send authentication header. Default: true. Set to false to test unauthenticated access.",
                        },
                    },
                    "required": ["method", "path"],
                },
            },
        },
    ]


def call_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call the LLM API and return the response.

    Args:
        messages: List of message dicts for the conversation.
        tools: Optional list of tool schemas for function calling.

    Returns:
        The parsed response data from the LLM.
    """
    api_base = os.environ["LLM_API_BASE"]
    api_key = os.environ["LLM_API_KEY"]
    model = os.environ["LLM_MODEL"]

    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    try:
        with httpx.Client(timeout=40.0) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as e:
        print(f"Error: LLM request timed out", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        raise
    except httpx.InvalidURL as e:
        print(f"Error: Invalid URL: {e}", file=sys.stderr)
        raise
    except httpx.RequestError as e:
        print(f"Error: Network error: {e}", file=sys.stderr)
        raise
    except httpx.HTTPStatusError as e:
        print(f"Error: HTTP error: {e.response.status_code}", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        raise
    except json.JSONDecodeError as e:
        print(f"Error: Malformed JSON response from LLM", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        raise


def execute_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    """Execute a single tool call and return the result.

    Args:
        tool_call: The tool call dict from the LLM response.

    Returns:
        A dict with 'tool', 'args', and 'result' keys.
    """
    function = tool_call.get("function", {})
    tool_name = function.get("name", "unknown")
    args_str = function.get("arguments", "{}")

    try:
        args = json.loads(args_str)
    except json.JSONDecodeError:
        args = {}

    # Execute the tool
    tool_impl = TOOLS_IMPL.get(tool_name)
    if tool_impl:
        try:
            result = tool_impl(args)
        except Exception as e:
            result = f"Error executing tool: {e}"
    else:
        result = f"Error: Unknown tool: {tool_name}"

    return {
        "tool": tool_name,
        "args": args,
        "result": result,
    }


def run_agent(question: str) -> dict[str, Any]:
    """Run the agentic loop to answer a question.

    Args:
        question: The user's question.

    Returns:
        A dict with 'answer', 'source', and 'tool_calls' keys.
    """
    # Build initial messages
    system_prompt = (
        "You are a documentation and system agent that helps answer questions about this software engineering project.\n"
        "You have three tools available:\n"
        "- list_files: Discover files in directories like 'wiki/' for documentation or 'backend/' for source code.\n"
        "- read_file: Read file contents to find answers in documentation or source code.\n"
        "- query_api: Query the running backend API for live data (item counts, analytics) or to test HTTP behavior.\n"
        "\n"
        "Tool selection guide:\n"
        "- Wiki/documentation questions → use list_files on 'wiki/', then read_file on relevant .md files.\n"
        "- Backend implementation questions → use list_files on 'backend/app/', then read_file on relevant .py files.\n"
        "- Live data questions (counts, scores, analytics) → use query_api.\n"
        "- HTTP status code questions → use query_api (set auth=false to test unauthenticated access).\n"
        "- Bug diagnosis questions → use query_api to reproduce the error, then read_file on the failing source code.\n"
        "\n"
        "When you have enough information, respond with a JSON object containing:\n"
        "- 'answer': Your answer to the question (be specific and include relevant details)\n"
        "- 'source': The file path and optional section anchor (e.g., 'wiki/git.md#merge-conflict' or 'backend/app/main.py')\n"
        "For wiki questions, include the wiki file path in source.\n"
        "For source code questions, include the backend file path in source.\n"
        "For API data questions, source is optional."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    tool_schemas = get_tool_schemas()
    output_tool_calls: list[dict[str, Any]] = []
    tool_call_count = 0

    while tool_call_count < MAX_TOOL_CALLS:
        # Call the LLM
        try:
            response_data = call_llm(messages, tools=tool_schemas)
        except Exception:
            # Return error response
            return {
                "answer": "",
                "source": "",
                "tool_calls": output_tool_calls,
                "error": "LLM call failed",
            }

        # Extract the assistant message
        try:
            assistant_message = response_data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error: Unexpected response format from LLM: {e}", file=sys.stderr)
            return {
                "answer": "",
                "source": "",
                "tool_calls": output_tool_calls,
                "error": "Unexpected response format",
            }

        # Check for tool calls - handle content being None
        tool_calls = assistant_message.get("tool_calls") or []
        content = assistant_message.get("content") or ""

        if not tool_calls:
            # No tool calls - extract final answer
            if not content:
                content = "No answer provided by the model."

            # Try to parse as JSON
            try:
                parsed = json.loads(content)
                answer = parsed.get("answer", content.strip())
                source = parsed.get("source", "")
            except json.JSONDecodeError:
                answer = content.strip()
                source = ""

            return {
                "answer": answer,
                "source": source if isinstance(source, str) else "",
                "tool_calls": output_tool_calls,
            }

        # Process tool calls
        for tool_call in tool_calls:
            if tool_call_count >= MAX_TOOL_CALLS:
                break

            # Execute the tool
            result = execute_tool_call(tool_call)
            output_tool_calls.append(result)
            tool_call_count += 1

            # Append tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id", ""),
                "content": result["result"],
            })

        # Continue loop to get next LLM response

    # Hit max tool calls - return what we have
    return {
        "answer": "Reached maximum tool call limit.",
        "source": "",
        "tool_calls": output_tool_calls,
    }


def main() -> None:
    """Main entry point for the agent CLI."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print(
            "Error: Missing required argument: question",
            file=sys.stderr,
        )
        print(
            "Usage: uv run agent.py \"<your question>\"",
            file=sys.stderr,
        )
        sys.exit(1)

    question = sys.argv[1]

    # Load and validate environment variables
    ensure_env_vars()
    validate_env_vars()

    # Run the agent
    result = run_agent(question)

    # Output result as JSON
    print(json.dumps(result, ensure_ascii=False))

    # Exit with appropriate code
    if "error" in result:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
