"""
notebook_setup.py — Helper for running this framework inside a Jupyter notebook.

Provides two public functions:

    prepare() -> bool
        Loads .env, validates API keys, starts the MCP server as a background
        subprocess if it isn't already reachable, and returns RUN_LIVE (True if
        the Gemini key is present and the server is reachable).

    stop_server()
        Gracefully terminates the MCP server process started by prepare().

Typical notebook usage
----------------------

    from notebook_setup import prepare, stop_server

    RUN_LIVE = prepare()   # call once at the top of your notebook

    # ... your eval cells ...

    stop_server()          # call in the last cell (or register with atexit)

If RUN_LIVE is False the notebook should fall back to replaying recorded data
via replay.py instead of making live API calls.
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent
ENV_PATH = REPO_ROOT / ".env"
SERVER_SCRIPT = REPO_ROOT / "server.py"

# ---------------------------------------------------------------------------
# Module-level process handle (singleton)
# ---------------------------------------------------------------------------
_server_proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prepare(
    mcp_url: str | None = None,
    startup_timeout: float = 10.0,
    verbose: bool = True,
) -> bool:
    """
    Prepare the evaluation environment.

    1. Load .env file (silently skipped if absent).
    2. Check for GEMINI_API_KEY.
    3. Start the MCP server if it isn't already reachable.
    4. Return RUN_LIVE flag.

    Parameters
    ----------
    mcp_url:
        Override the MCP server URL (default: MCP_URL env var or
        ``http://localhost:8000/mcp``).
    startup_timeout:
        Seconds to wait for the MCP server to become reachable.
    verbose:
        Print status messages.

    Returns
    -------
    bool
        True if Gemini API key is present AND MCP server is reachable.
    """
    global _server_proc

    # 1. Load environment
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)
        _log(verbose, f"✓ Loaded environment from {ENV_PATH}")
    else:
        _log(verbose, f"⚠ .env not found at {ENV_PATH} — using existing environment variables.")

    mcp_url = mcp_url or os.getenv("MCP_URL", "http://localhost:8000/mcp")
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    # 2. API key check
    if gemini_key:
        _log(verbose, "✓ GEMINI_API_KEY is set.")
    else:
        _log(
            verbose,
            "⚠ GEMINI_API_KEY not found.  Set it in .env or as an environment variable.\n"
            "  Provider will fall back to Ollama (llama3) if available, or replay mode.",
        )

    # 3. Start MCP server if needed
    if _is_server_reachable(mcp_url):
        _log(verbose, f"✓ MCP server already reachable at {mcp_url}")
    else:
        _log(verbose, f"→ Starting MCP server: python {SERVER_SCRIPT.name} ...")
        _server_proc = _start_server()
        atexit.register(stop_server)

        deadline = time.monotonic() + startup_timeout
        while time.monotonic() < deadline:
            if _is_server_reachable(mcp_url):
                _log(verbose, f"✓ MCP server is up at {mcp_url}")
                break
            time.sleep(0.5)
        else:
            _log(
                verbose,
                f"✗ MCP server did not become reachable within {startup_timeout}s.\n"
                "  Check server.py for errors.  Falling back to replay mode.",
            )
            return False

    run_live = bool(gemini_key) and _is_server_reachable(mcp_url)
    mode = "LIVE (Gemini + MCP)" if run_live else "REPLAY (no live calls)"
    _log(verbose, f"\n▶ Evaluation mode: {mode}\n")
    return run_live


def stop_server() -> None:
    """
    Stop the MCP server process started by prepare().

    Safe to call multiple times or when the server was never started.
    """
    global _server_proc
    if _server_proc is None:
        return
    try:
        if sys.platform == "win32":
            _server_proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            _server_proc.terminate()
        _server_proc.wait(timeout=5)
    except Exception:
        try:
            _server_proc.kill()
        except Exception:
            pass
    _server_proc = None
    print("[notebook_setup] MCP server stopped.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _start_server() -> subprocess.Popen:  # type: ignore[type-arg]
    """Launch server.py as a background subprocess."""
    kwargs: dict = {
        "args": [sys.executable, str(SERVER_SCRIPT)],
        "cwd": str(REPO_ROOT),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(**kwargs)


def _is_server_reachable(url: str, timeout: float = 2.0) -> bool:
    """Return True if the MCP server responds to a lightweight ping."""
    # We try a JSON-RPC ping (initialize handshake or tools/list)
    ping_url = url.rstrip("/")
    payload = {"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(ping_url, json=payload)
            return resp.status_code < 500
    except Exception:
        return False


def _log(verbose: bool, msg: str) -> None:
    if verbose:
        print(f"[notebook_setup] {msg}")
