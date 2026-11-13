"""
provider.py - Standalone function-calling loop provider for promptfoo.

Flow:
1. Load environment (.env file if present).
2. Connect to the MCP server (URL from MCP_URL env var).
3. Fetch the tool schemas from the server.
4. Build a Gemini chat session with the tools.
5. Run the tool-calling loop (up to MAX_STEPS iterations).
6. Return provider output: {"output": answer, "metadata": {"tool_calls": [...]}}.

Fallback: If Gemini fails, falls back to Ollama (llama3).
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
_REPO = Path(__file__).parent
load_dotenv(_REPO / ".env", override=False)

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
EVAL_MODEL: str = os.getenv("EVAL_MODEL", "gemini-2.0-flash")
MCP_URL: str = os.getenv("MCP_URL", "http://localhost:8000/mcp")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = "llama3"
MAX_STEPS: int = 10

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

# ---------------------------------------------------------------------------
# MCP client helpers
# ---------------------------------------------------------------------------

class MCPClient:
    """Session-aware MCP client for FastMCP (handles mcp-session-id & SSE frames)."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.client = httpx.Client(
            timeout=30,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        self.session_id: str | None = None
        self._initialize()

    def _initialize(self) -> None:
        resp = self.client.post(
            self.url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "harness-eval", "version": "1.0"},
                    "capabilities": {},
                },
            },
        )
        sess = resp.headers.get("mcp-session-id")
        if sess:
            self.session_id = sess
            self.client.headers["mcp-session-id"] = sess
        # Notify initialized
        self.client.post(
            self.url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

    def post(self, method: str, params: dict | None = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        resp = self.client.post(self.url, json=payload)
        resp.raise_for_status()
        text = resp.text.strip()
        if text.startswith("data:"):
            text = text.split("data:", 1)[1].strip()
        elif "data: " in text:
            for line in text.splitlines():
                if line.startswith("data:"):
                    text = line.split("data:", 1)[1].strip()
                    break
        if not text:
            return None
        body = json.loads(text)
        if "error" in body:
            raise RuntimeError(f"MCP error: {body['error']}")
        return body.get("result")

    def close(self) -> None:
        self.client.close()


def fetch_mcp_tools() -> list[dict]:
    """Retrieve tool schemas from the MCP server."""
    client = MCPClient(MCP_URL)
    try:
        result = client.post("tools/list", {}) or {}
    finally:
        client.close()
    tools = []
    for t in result.get("tools", []):
        tools.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
        })
    return tools


def call_mcp_tool(tool_name: str, args: dict) -> Any:
    """Invoke a tool on the MCP server and return its result."""
    client = MCPClient(MCP_URL)
    try:
        result = client.post("tools/call", {"name": tool_name, "arguments": args})
    finally:
        client.close()
    if isinstance(result, dict) and "content" in result:
        content = result["content"]
        if content and content[0].get("type") == "text":
            try:
                return json.loads(content[0]["text"])
            except json.JSONDecodeError:
                return content[0]["text"]
    return result


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------

def _schema_to_gemini_params(schema: dict) -> Any:
    """Convert a JSON Schema dict to a Gemini Schema proto."""
    import google.generativeai as genai  # type: ignore

    type_map = {
        "string": genai.protos.Type.STRING,
        "number": genai.protos.Type.NUMBER,
        "integer": genai.protos.Type.INTEGER,
        "boolean": genai.protos.Type.BOOLEAN,
        "array": genai.protos.Type.ARRAY,
        "object": genai.protos.Type.OBJECT,
    }
    props = {}
    for name, prop in schema.get("properties", {}).items():
        prop_type = type_map.get(prop.get("type", "string"), genai.protos.Type.STRING)
        kwargs: dict = {"type_": prop_type}
        if "description" in prop:
            kwargs["description"] = prop["description"]
        if prop.get("type") == "array" and "items" in prop:
            item_type = type_map.get(prop["items"].get("type", "string"), genai.protos.Type.STRING)
            kwargs["items"] = genai.protos.Schema(type_=item_type)
        props[name] = genai.protos.Schema(**kwargs)

    required = schema.get("required", [])
    return genai.protos.Schema(
        type_=genai.protos.Type.OBJECT,
        properties=props,
        required=required,
    )


def _to_json_serializable(val: Any) -> Any:
    """Recursively convert protobuf/RepeatedComposite and mapping types to standard Python primitives."""
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if hasattr(val, "items"):
        return {k: _to_json_serializable(v) for k, v in val.items()}
    if hasattr(val, "__iter__"):
        return [_to_json_serializable(x) for x in val]
    return str(val)


import time

def _run_gemini(query: str, tools: list[dict]) -> dict:
    """Run the tool-calling loop using the Gemini API with rate-limit retries."""
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=GEMINI_API_KEY)

    function_declarations = [
        genai.protos.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=_schema_to_gemini_params(t["parameters"]),
        )
        for t in tools
    ]

    gemini_tools = [genai.protos.Tool(function_declarations=function_declarations)]
    model = genai.GenerativeModel(model_name=EVAL_MODEL, tools=gemini_tools)

    system_msg = (
        "You are a business-intelligence assistant. "
        "Workflow rules:\n"
        "1. Always call resolve_metric first with the indicator(s).\n"
        "2. If resolve_metric returns no candidates, inform the user that the metric is unavailable. Do NOT call fetch tools.\n"
        "3. If candidates tie with equal confidence, ask the user to clarify between them. Name the candidates and do NOT call fetch tools.\n"
        "4. Otherwise, you MUST continue and call the appropriate domain fetch tools (fetch_finance, fetch_engineering, fetch_support, fetch_ops) with the resolved metric IDs.\n"
        "5. Never invent or guess metric IDs."
    )
    chat = model.start_chat(history=[])

    def _send_with_retry(msg):
        for attempt in range(5):
            try:
                return chat.send_message(msg)
            except Exception as e:
                err_str = str(e).lower()
                if "quota" in err_str or "429" in err_str or "resource_exhausted" in err_str:
                    time.sleep(15 * (attempt + 1))
                else:
                    raise e
        return chat.send_message(msg)

    response = _send_with_retry(f"{system_msg}\n\nUser query: {query}")

    tool_call_trace: list[dict] = []
    answer = ""
    completed = False

    for _step in range(MAX_STEPS):
        fn_calls = [
            part.function_call
            for candidate in response.candidates
            for part in candidate.content.parts
            if hasattr(part, "function_call") and part.function_call.name
        ]

        if not fn_calls:
            for candidate in response.candidates:
                for part in candidate.content.parts:
                    if hasattr(part, "text") and part.text:
                        answer += part.text
            if not answer:
                answer = "[Model returned no text — check tool call trace]"
            completed = True
            break

        function_responses = []
        for fc in fn_calls:
            args = _to_json_serializable(fc.args)
            try:
                result = call_mcp_tool(fc.name, args)
            except Exception as exc:
                result = {"error": str(exc)}

            tool_call_trace.append({"name": fc.name, "arguments": args, "result": result})
            function_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=fc.name,
                        response={"result": _to_json_serializable(result)},
                    )
                )
            )
        response = _send_with_retry(function_responses)

    if not completed:
        answer = f"[Reached {MAX_STEPS}-step limit]"

    return {"answer": answer, "tool_calls": tool_call_trace, "completed": completed, "backend": "gemini"}


# ---------------------------------------------------------------------------
# Ollama fallback provider (OpenAI-compatible endpoint)
# ---------------------------------------------------------------------------

def _run_ollama(query: str, tools: list[dict]) -> dict:
    """Run the tool-calling loop using Ollama OpenAI-compatible API."""
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tools
    ]

    messages = [
        {"role": "system", "content": (
            "You are a business-intelligence assistant. "
            "Always call resolve_metric first. Never fabricate metric IDs."
        )},
        {"role": "user", "content": query},
    ]

    base = OLLAMA_BASE_URL.rstrip("/")
    tool_call_trace: list[dict] = []
    answer = ""
    completed = False

    with httpx.Client(timeout=60) as client:
        for _step in range(MAX_STEPS):
            payload = {
                "model": OLLAMA_MODEL,
                "messages": messages,
                "tools": openai_tools,
                "stream": False,
            }
            resp = client.post(f"{base}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]

            tc = msg.get("tool_calls") or []
            if not tc:
                answer = msg.get("content", "") or "[No response from Ollama]"
                completed = True
                break

            messages.append(msg)
            for call in tc:
                fn = call["function"]
                args = json.loads(fn.get("arguments", "{}"))
                try:
                    result = call_mcp_tool(fn["name"], args)
                except Exception as exc:
                    result = {"error": str(exc)}
                tool_call_trace.append({"name": fn["name"], "arguments": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", "0"),
                    "content": json.dumps(result, default=str),
                })

    return {"answer": answer, "tool_calls": tool_call_trace, "completed": completed, "backend": "ollama"}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_case(query: str) -> dict:
    """Run a single evaluation case end-to-end and return promptfoo provider output."""
    try:
        tools = fetch_mcp_tools()
    except Exception as exc:
        return {
            "output": f"[ERROR] Could not reach MCP server at {MCP_URL}: {exc}",
            "metadata": {"tool_calls": [], "completed": False, "backend": "none"},
        }

    if GEMINI_API_KEY:
        try:
            result = _run_gemini(query, tools)
            _save_trace(result)
            return {
                "output": result["answer"] or "[Gemini: no text output]",
                "metadata": {
                    "tool_calls": result["tool_calls"],
                    "completed": result["completed"],
                    "backend": result["backend"],
                },
            }
        except Exception:
            print("[provider] Gemini failed, falling back to Ollama:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    try:
        result = _run_ollama(query, tools)
        _save_trace(result)
        return {
            "output": result["answer"] or "[Ollama: no text output]",
            "metadata": {
                "tool_calls": result["tool_calls"],
                "completed": result["completed"],
                "backend": result["backend"],
            },
        }
    except Exception as exc:
        return {
            "output": f"[ERROR] Both Gemini and Ollama failed: {exc}",
            "metadata": {"tool_calls": [], "completed": False, "backend": "none"},
        }


def _save_trace(result: dict) -> None:
    """Persist tool-call trace to data/l2-trace.json."""
    trace_path = _REPO / "data" / "l2-trace.json"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if trace_path.exists():
        try:
            existing = json.loads(trace_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    existing.append(result)
    trace_path.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# promptfoo file:// provider interface
# ---------------------------------------------------------------------------

def call_api(
    prompt: str,
    options: dict | None = None,
    context: dict | None = None,
) -> dict:
    """promptfoo entry point."""
    return run_case(prompt)


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What was our revenue last quarter?"
    out = run_case(q)
    print(json.dumps(out, indent=2, default=str))
