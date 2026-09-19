"""
PyPer MCP Base Framework

Shared MCP protocol handler for all PyPer MCP servers.
Provides: JSON-RPC loop, tool registration, response building.
"""
import sys
import json
import logging
from typing import Dict, Any, List, Callable, Optional

logger = logging.getLogger(__name__)


class MCPTool:
    """Represents a single MCP tool definition."""
    def __init__(self, name: str, description: str, input_schema: dict, handler: Callable):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.input_schema.get("properties", {}),
                "required": self.input_schema.get("required", []),
            }
        }


class MCPServer:
    """Base MCP server implementing JSON-RPC protocol over stdio."""

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools: Dict[str, MCPTool] = {}
        self.initialized = False

    def register_tool(self, name: str, description: str,
                      input_schema: dict, handler: Callable):
        """Register a tool with its handler."""
        self.tools[name] = MCPTool(name, description, input_schema, handler)

    def register_tools(self, tools: List[MCPTool]):
        """Register multiple tools at once."""
        for tool in tools:
            self.tools[tool.name] = tool

    def send_response(self, resp: dict):
        """Send JSON-RPC response to stdout."""
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def handle_tool_call(self, tool_name: str, args: dict) -> dict:
        """Execute a tool and return result."""
        tool = self.tools.get(tool_name)
        if not tool:
            return {"error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}
        try:
            result = tool.handler(**args)
            if isinstance(result, str):
                return {"content": [{"type": "text", "text": result}]}
            elif isinstance(result, dict):
                return result
            elif isinstance(result, list):
                return {"content": [{"type": "text", "text": "\n".join(str(r) for r in result)}]}
            else:
                return {"content": [{"type": "text", "text": str(result)}]}
        except Exception as e:
            logger.error(f"Tool {tool_name} error: {e}")
            return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}

    def handle_request(self, req: dict) -> Optional[dict]:
        """Handle a single JSON-RPC request."""
        method = req.get("method", "")
        req_id = req.get("id", 0)
        params = req.get("params", {})

        if method == "initialize":
            self.initialized = False
            return {
                "jsonrpc": "2.0", "id": req_id, "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version}
                }
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"tools": [t.to_dict() for t in self.tools.values()]}
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})
            result = self.handle_tool_call(tool_name, args)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        elif method == "initialized":
            self.initialized = True
            return None

        return None

    def run(self):
        """Main MCP stdio loop."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue

            resp = self.handle_request(req)
            if resp:
                self.send_response(resp)
