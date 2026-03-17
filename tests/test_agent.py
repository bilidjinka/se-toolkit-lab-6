#!/usr/bin/env python3
"""Regression tests for agent.py CLI."""

import json
import subprocess
import sys


def test_agent_basic_question() -> None:
    """Test that agent.py returns valid JSON with answer and tool_calls for a basic question."""
    result = subprocess.run(
        ["uv", "run", "agent.py", "Test question"],
        capture_output=True,
        text=True,
        check=True,
    )

    # Parse stdout as JSON
    output = json.loads(result.stdout)

    # Assert 'answer' key exists and is a string
    assert "answer" in output, "Missing 'answer' key in output"
    assert isinstance(output["answer"], str), "'answer' should be a string"

    # Assert 'tool_calls' key exists and is a list
    assert "tool_calls" in output, "Missing 'tool_calls' key in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' should be a list"

    # Assert no error for successful execution
    assert "error" not in output, "Unexpected 'error' key in successful response"

    # Assert exit code is 0
    assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}"


def test_agent_missing_question() -> None:
    """Test that agent.py exits with error when no question is provided."""
    result = subprocess.run(
        ["uv", "run", "agent.py"],
        capture_output=True,
        text=True,
    )

    # Should exit with non-zero code
    assert result.returncode != 0, "Expected non-zero exit code for missing question"

    # Should print error to stderr
    assert "Error" in result.stderr or "error" in result.stderr.lower(), (
        "Expected error message in stderr"
    )


if __name__ == "__main__":
    print("Running agent.py regression tests...")

    try:
        test_agent_missing_question()
        print("✓ test_agent_missing_question passed")
    except AssertionError as e:
        print(f"✗ test_agent_missing_question failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ test_agent_missing_question error: {e}")
        sys.exit(1)

    try:
        test_agent_basic_question()
        print("✓ test_agent_basic_question passed")
    except AssertionError as e:
        print(f"✗ test_agent_basic_question failed: {e}")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"✗ test_agent_basic_question failed (CalledProcessError): {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ test_agent_basic_question error: {e}")
        sys.exit(1)

    print("\nAll tests passed!")
