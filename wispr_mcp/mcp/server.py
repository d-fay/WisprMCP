"""
MCP server implementation for WisprMCP.
"""

import json
import sys
import asyncio
from typing import Dict, Any, List, Optional
import argparse

try:
    from .tools import WisprTools
    from .apps import list_ui_resources, read_ui_resource
except ImportError:
    # Handle running as standalone script
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from wispr_mcp.mcp.tools import WisprTools
    from wispr_mcp.mcp.apps import list_ui_resources, read_ui_resource


#: A host may append control metadata to the END of the FIRST text content
#: block and then scan only a truncated prefix of the joined content for it.
#: Kiro Crew does exactly that: its MCP-Apps host appends a render marker to
#: the first text block (``mcp_gateway/apps.py: append_marker``) while its ACP
#: layer caps each block at 4000 characters before the dashboard looks for the
#: marker (``acp/_dispatch.py: _build_tool_result_event``). One large block
#: therefore pushes the marker past the cut and the ui:// view silently never
#: mounts -- no error, no log. Leading with a short digest block keeps any such
#: appended marker well inside the prefix. The full payload follows in a second
#: block and still reaches the model intact over the MCP pipe, because the cut
#: applies to the host's display event, not to the tool result itself.
LEAD_BLOCK_THRESHOLD = 3000

#: Hard cap on the digest block, so the lead can never itself overrun a
#: prefix-scanning host.
LEAD_BLOCK_MAX = 900

#: Scalar string values longer than this are summarised by length instead of
#: being inlined into the digest.
_LEAD_SCALAR_MAX = 120


def _digest_line(tool_name: str, result: Dict[str, Any]) -> str:
    """One-line digest of ``result``'s scalar shape, for the lead block.

    Only cheap, self-describing fields are inlined: short strings, numbers,
    booleans and ``None``. Long strings and containers are reported by size so
    the digest stays bounded regardless of payload.
    """
    parts: List[str] = []
    for key, value in result.items():
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            parts.append(f"{key}={value}")
        elif isinstance(value, str):
            if len(value) <= _LEAD_SCALAR_MAX:
                parts.append(f"{key}={value!r}")
            else:
                parts.append(f"{key}=<{len(value)} chars>")
        elif isinstance(value, (list, tuple)):
            parts.append(f"{key}=<{len(value)} items>")
        elif isinstance(value, dict):
            parts.append(f"{key}=<{len(value)} keys>")
        else:
            parts.append(f"{key}=<{type(value).__name__}>")
    line = f"{tool_name}: " + ", ".join(parts)
    if len(line) > LEAD_BLOCK_MAX:
        line = line[:LEAD_BLOCK_MAX - 1] + "…"
    return line


def _model_content_blocks(tool_name: str, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the ``content`` array for a ``tools/call`` result.

    Small results stay a single text block, which is what every host expects.
    A large result is emitted as a short digest block followed by the full
    payload, so a host that appends control metadata to the first block and
    scans only a prefix still finds it (see :data:`LEAD_BLOCK_THRESHOLD`).
    """
    body = json.dumps(result, indent=2, default=str)
    if len(body) <= LEAD_BLOCK_THRESHOLD:
        return [{"type": "text", "text": body}]
    return [
        {"type": "text", "text": _digest_line(tool_name, result)},
        {"type": "text", "text": body},
    ]


class MCPServer:
    """JSON-RPC 2.0 STDIO server for MCP protocol."""    
    def __init__(self, db_path: Optional[str] = None):
        self.tools = WisprTools(db_path)
        self.request_id = 0
    
    async def handle_request(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle incoming JSON-RPC request."""
        try:
            method = request_data.get("method")
            params = request_data.get("params", {})
            request_id = request_data.get("id")

            if "id" not in request_data:
                # JSON-RPC notification (e.g. notifications/initialized) — no
                # "id" field, no response allowed. Answering it races the
                # client's next read during the initialize ->
                # notifications/initialized -> tools/list handshake: the
                # client ends up reading this stray reply as the answer to
                # tools/list instead, surfacing as "tools/list: Method not
                # found: notifications/initialized".
                return None

            if method == "initialize":
                return self._handle_initialize(request_id, params)
            elif method == "tools/list":
                return self._handle_tools_list(request_id)
            elif method == "tools/call":
                return self._handle_tools_call(request_id, params)
            elif method == "resources/list":
                return self._handle_resources_list(request_id)
            elif method == "resources/read":
                return self._handle_resources_read(request_id, params)
            elif method == "ping":
                return self._handle_ping(request_id)
            else:
                return self._error_response(request_id, -32601, f"Method not found: {method}")
        
        except Exception as e:
            return self._error_response(request_id, -32603, f"Internal error: {str(e)}")
    
    def _handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        try:
            from .. import __version__ as server_version
        except ImportError:
            server_version = "0.0.0"
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    # Declared because resources/list and resources/read are
                    # now implemented; they serve the ui:// app views.
                    "resources": {"listChanged": False},
                    "logging": {}
                },
                "serverInfo": {
                    "name": "wispr-mcp",
                    "version": server_version
                }
            }
        }
    
    def _handle_tools_list(self, request_id: Any) -> Dict[str, Any]:
        """Handle tools/list request."""
        tools_schema = self.tools.get_tools_schema()
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools_schema
            }
        }
    
    def _handle_tools_call(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            return self._error_response(request_id, -32602, "Missing tool name")
        
        result = self.tools.execute_tool(tool_name, arguments)
        
        if "error" in result:
            return self._error_response(request_id, -32603, result["error"])
        
        # A tool may attach data meant for a ui:// view rather than the model.
        # SEP-1865 carries that in structuredContent, which hosts pass to the
        # app and keep out of model context; the text below stays the model's
        # view of the result.
        structured = result.pop("_ui_structured", None)
        
        payload: Dict[str, Any] = {
            "content": _model_content_blocks(tool_name, result)
        }
        if structured is not None:
            payload["structuredContent"] = structured
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": payload
        }
    
    def _handle_resources_list(self, request_id: Any) -> Dict[str, Any]:
        """Handle resources/list request (ui:// app views)."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "resources": list_ui_resources()
            }
        }
    
    def _handle_resources_read(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/read request (ui:// app views)."""
        uri = params.get("uri")
        
        if not uri:
            return self._error_response(request_id, -32602, "Missing resource uri")
        
        try:
            contents = read_ui_resource(uri)
        except OSError as e:
            return self._error_response(
                request_id, -32603, f"Could not read resource {uri}: {e}"
            )
        
        if contents is None:
            return self._error_response(request_id, -32602, f"Unknown resource: {uri}")
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "contents": [contents]
            }
        }
    
    def _handle_ping(self, request_id: Any) -> Dict[str, Any]:
        """Handle ping request."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {}
        }
    
    def _error_response(self, request_id: Any, code: int, message: str) -> Dict[str, Any]:
        """Create error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }
    
    async def run(self) -> None:
        """Run the MCP server."""
        while True:
            try:
                # Read line from stdin
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                # Parse JSON-RPC request
                try:
                    request = json.loads(line)
                except json.JSONDecodeError as e:
                    error_response = self._error_response(None, -32700, f"Parse error: {str(e)}")
                    print(json.dumps(error_response), flush=True)
                    continue
                
                # Handle request
                response = await self.handle_request(request)
                
                if response:
                    print(json.dumps(response), flush=True)
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                error_response = self._error_response(None, -32603, f"Server error: {str(e)}")
                print(json.dumps(error_response), flush=True)


async def main():
    """Main entry point for MCP server."""
    parser = argparse.ArgumentParser(description="WisprMCP JSON-RPC server")
    parser.add_argument("--db-path", help="Path to Wispr Flow database")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()
    
    try:
        server = MCPServer(args.db_path)
        await server.run()
    except FileNotFoundError as e:
        error_msg = f"Database not found: {e}"
        if args.debug:
            import traceback
            error_msg += f"\n{traceback.format_exc()}"
        
        error_response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32603,
                "message": error_msg
            }
        }
        print(json.dumps(error_response), flush=True)
        sys.exit(1)
    except Exception as e:
        error_msg = f"Server startup failed: {e}"
        if args.debug:
            import traceback
            error_msg += f"\n{traceback.format_exc()}"
        
        error_response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32603,
                "message": error_msg
            }
        }
        print(json.dumps(error_response), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())