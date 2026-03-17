#!/usr/bin/env python3
"""Regression tests for agent.py with HTTP stub server.

These tests use a local HTTP stub server that mimics the Chat Completions API
to test tool calling behavior without requiring a real LLM.
"""

import json
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any


class StubHandler(BaseHTTPRequestHandler):
    """HTTP request handler that simulates LLM API responses."""

    # Class-level state for controlling responses
    response_sequence: list[dict[str, Any]] = []
    response_index: int = 0

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass

    def do_POST(self) -> None:
        """Handle POST requests to /chat/completions."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            request_data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Get the next response in the sequence
        if StubHandler.response_index < len(StubHandler.response_sequence):
            response_data = StubHandler.response_sequence[StubHandler.response_index]
            StubHandler.response_index += 1
        else:
            # Default response if sequence is exhausted
            response_data = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({
                            "answer": "Default answer",
                            "source": ""
                        })
                    }
                }]
            }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode("utf-8"))


def start_stub_server(port: int) -> HTTPServer:
    """Start the stub server on the given port."""
    server = HTTPServer(("127.0.0.1", port), StubHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    return server


def run_stub_server_once(port: int, responses: list[dict[str, Any]]) -> None:
    """Run stub server for a single request with given responses."""
    StubHandler.response_sequence = responses
    StubHandler.response_index = 0

    server = HTTPServer(("127.0.0.1", port), StubHandler)
    server.handle_request()
    server.server_close()


class MultiRequestStubHandler(BaseHTTPRequestHandler):
    """HTTP request handler that simulates LLM API responses for multiple requests."""

    response_sequence: list[dict[str, Any]] = []
    response_index: int = 0

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass

    def do_POST(self) -> None:
        """Handle POST requests to /chat/completions."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            request_data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Get the next response in the sequence
        if MultiRequestStubHandler.response_index < len(MultiRequestStubHandler.response_sequence):
            response_data = MultiRequestStubHandler.response_sequence[MultiRequestStubHandler.response_index]
            MultiRequestStubHandler.response_index += 1
        else:
            # Default response if sequence is exhausted
            response_data = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({
                            "answer": "Default answer",
                            "source": ""
                        })
                    }
                }]
            }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode("utf-8"))


def test_merge_conflict_question() -> None:
    """Test agent with merge conflict question.

    Stub returns tool calls: list_files wiki, then read_file wiki/git.md,
    then final JSON content with source: wiki/git.md#merge-conflict.
    """
    import socket

    # Find an available port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    # Define response sequence
    responses = [
        # First call: return tool calls for list_files
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "list_files",
                            "arguments": json.dumps({"path": "wiki"})
                        }
                    }]
                }
            }]
        },
        # Second call: return tool calls for read_file
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "wiki/git.md"})
                        }
                    }]
                }
            }]
        },
        # Third call: return final answer
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "answer": "To resolve a merge conflict, open the conflicted file and edit the conflict markers.",
                        "source": "wiki/git.md#merge-conflict"
                    })
                }
            }]
        }
    ]

    # Start stub server that handles multiple requests
    server = HTTPServer(("127.0.0.1", port), MultiRequestStubHandler)
    MultiRequestStubHandler.response_sequence = responses
    MultiRequestStubHandler.response_index = 0
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Give server time to start
    time.sleep(0.1)

    # Run agent with stub server
    env = {
        "LLM_API_BASE": f"http://127.0.0.1:{port}",
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "test-model"
    }

    import os
    env.update(os.environ)

    result = subprocess.run(
        [".venv/bin/python", "agent.py", "How do I resolve a merge conflict?"],
        capture_output=True,
        text=True,
        env=env,
    )

    server.shutdown()

    # Parse output
    output = json.loads(result.stdout)

    # Assertions
    assert "answer" in output, "Missing 'answer' key in output"
    assert isinstance(output["answer"], str), "'answer' should be a string"
    assert "source" in output, "Missing 'source' key in output"
    assert isinstance(output["source"], str), "'source' should be a string"
    assert "tool_calls" in output, "Missing 'tool_calls' key in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' should be a list"

    # Check tool_calls contains expected tools
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "list_files" in tool_names, "Expected 'list_files' in tool_calls"
    assert "read_file" in tool_names, "Expected 'read_file' in tool_calls"

    # Check source contains expected anchor
    assert "wiki/git.md#merge-conflict" in output["source"], \
        f"Expected 'wiki/git.md#merge-conflict' in source, got: {output['source']}"


def test_wiki_listing_question() -> None:
    """Test agent with wiki listing question.

    Stub returns one tool call: list_files wiki, then final JSON.
    """
    import socket

    # Find an available port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    # Define response sequence
    responses = [
        # First call: return tool call for list_files
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "list_files",
                            "arguments": json.dumps({"path": "wiki"})
                        }
                    }]
                }
            }]
        },
        # Second call: return final answer
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "answer": "The wiki contains documentation files including git.md, http.md, and linux.md.",
                        "source": "wiki/"
                    })
                }
            }]
        }
    ]

    # Start stub server that handles multiple requests
    server = HTTPServer(("127.0.0.1", port), MultiRequestStubHandler)
    MultiRequestStubHandler.response_sequence = responses
    MultiRequestStubHandler.response_index = 0
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Give server time to start
    time.sleep(0.1)

    # Run agent with stub server
    env = {
        "LLM_API_BASE": f"http://127.0.0.1:{port}",
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "test-model"
    }

    import os
    env.update(os.environ)

    result = subprocess.run(
        [".venv/bin/python", "agent.py", "What files are in the wiki?"],
        capture_output=True,
        text=True,
        env=env,
    )

    server.shutdown()

    # Parse output
    output = json.loads(result.stdout)

    # Assertions
    assert "answer" in output, "Missing 'answer' key in output"
    assert isinstance(output["answer"], str), "'answer' should be a string"
    assert "source" in output, "Missing 'source' key in output"
    assert isinstance(output["source"], str), "'source' should be a string"
    assert "tool_calls" in output, "Missing 'tool_calls' key in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' should be a list"

    # Check tool_calls contains list_files
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "list_files" in tool_names, "Expected 'list_files' in tool_calls"


if __name__ == "__main__":
    print("Running agent.py regression tests with HTTP stub server...")

    try:
        test_merge_conflict_question()
        print("✓ test_merge_conflict_question passed")
    except AssertionError as e:
        print(f"✗ test_merge_conflict_question failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ test_merge_conflict_question error: {e}")
        sys.exit(1)

    try:
        test_wiki_listing_question()
        print("✓ test_wiki_listing_question passed")
    except AssertionError as e:
        print(f"✗ test_wiki_listing_question failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ test_wiki_listing_question error: {e}")
        sys.exit(1)

    print("\nAll tests passed!")
