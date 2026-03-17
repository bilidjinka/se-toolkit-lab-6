#!/usr/bin/env python3
"""Agent that calls an LLM to answer user questions.

This script provides a CLI interface to query an LLM (Qwen Code API)
and returns the answer as a JSON object.
"""

import json
import os
import sys
from pathlib import Path

import httpx


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


def call_llm(question: str) -> dict:
    """Call the LLM API and return the response.

    Args:
        question: The user's question to ask the LLM.

    Returns:
        A dict with 'answer' and 'tool_calls' keys.
        On error, includes an 'error' key.
    """
    api_base = os.environ["LLM_API_BASE"]
    api_key = os.environ["LLM_API_KEY"]
    model = os.environ["LLM_MODEL"]

    system_prompt = (
        "Answer the question concisely. Tools are disabled. Respond in plain text."
    )

    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    }

    try:
        with httpx.Client(timeout=40.0) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as e:
        error_msg = "LLM request timed out"
        print(f"Error: {error_msg}", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        return {"answer": "", "tool_calls": [], "error": error_msg}
    except httpx.InvalidURL as e:
        error_msg = f"Invalid URL: {e}"
        print(f"Error: {error_msg}", file=sys.stderr)
        return {"answer": "", "tool_calls": [], "error": error_msg}
    except httpx.RequestError as e:
        error_msg = f"Network error: {e}"
        print(f"Error: {error_msg}", file=sys.stderr)
        return {"answer": "", "tool_calls": [], "error": error_msg}
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP error: {e.response.status_code}"
        print(f"Error: {error_msg}", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        return {"answer": "", "tool_calls": [], "error": error_msg}
    except json.JSONDecodeError as e:
        error_msg = "Malformed JSON response from LLM"
        print(f"Error: {error_msg}", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        return {"answer": "", "tool_calls": [], "error": error_msg}

    # Extract answer from response
    try:
        content = data["choices"][0]["message"]["content"]
        answer = content if content else "No answer provided by the model."
    except (KeyError, IndexError, TypeError) as e:
        error_msg = "Unexpected response format from LLM"
        print(f"Error: {error_msg}", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        print(f"Response: {data}", file=sys.stderr)
        return {"answer": "", "tool_calls": [], "error": error_msg}

    return {"answer": answer, "tool_calls": []}


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

    # Call the LLM
    result = call_llm(question)

    # Output result as JSON
    print(json.dumps(result, ensure_ascii=False))

    # Exit with appropriate code
    if "error" in result:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
