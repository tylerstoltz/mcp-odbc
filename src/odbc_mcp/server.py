"""
MCP Server implementation for ODBC connections.
Provides tools for database querying via the Model Context Protocol.
"""

import asyncio
import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
import mcp.types as types

from .config import load_config, ServerConfig
from .odbc import ODBCHandler


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)

logger = logging.getLogger("odbc-mcp-server")


class ODBCMCPServer:
    """
    MCP Server that provides tools for ODBC database connectivity.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the server with configuration."""
        try:
            self.config = load_config(config_path)
            self.odbc = ODBCHandler(self.config)
            self.server = Server("odbc-mcp-server")
            
            # Register tool handlers
            self._register_tools()
            
            logger.info(f"Initialized ODBC MCP Server with {len(self.config.connections)} connections")
        except Exception as e:
            logger.error(f"Failed to initialize server: {e}")
            raise
            
    def _register_tools(self):
        """Register all MCP tools."""
        @self.server.list_tools()
        async def list_tools() -> List[types.Tool]:
            """List available tools for the MCP client."""
            return [
                types.Tool(
                    name="list-connections",
                    description="List all configured database connections",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="list-available-dsns",
                    description="List all available DSNs on the system",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="test-connection",
                    description="Test a database connection and return information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "connection_name": {
                                "type": "string",
                                "description": "Name of the connection to test (optional, uses default if not specified)"
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="list-tables",
                    description="List all tables in the database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "connection_name": {
                                "type": "string",
                                "description": "Name of the connection to use (optional, uses default if not specified)"
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="get-table-schema",
                    description="Get schema information for a table",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to describe (required)"
                            },
                            "connection_name": {
                                "type": "string",
                                "description": "Name of the connection to use (optional, uses default if not specified)"
                            }
                        },
                        "required": ["table_name"]
                    }
                ),
                types.Tool(
                    name="execute-query",
                    description="Execute an SQL query and return results",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "SQL query to execute (required)"
                            },
                            "connection_name": {
                                "type": "string",
                                "description": "Name of the connection to use (optional, uses default if not specified)"
                            },
                            "max_rows": {
                                "type": "integer",
                                "description": "Maximum number of rows to return (optional, uses default if not specified)"
                            }
                        },
                        "required": ["sql"]
                    }
                )
            ]
            
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            """Handle tool execution requests."""
            arguments = arguments or {}
            
            try:
                if name == "list-connections":
                    connections = self.odbc.list_connections()
                    result = {
                        "connections": connections,
                        "default_connection": self.config.default_connection
                    }
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                    
                elif name == "list-available-dsns":
                    dsns = self.odbc.get_available_dsns()
                    return [types.TextContent(type="text", text=json.dumps(dsns, indent=2))]
                    
                elif name == "test-connection":
                    connection_name = arguments.get("connection_name")
                    result = self.odbc.test_connection(connection_name)
                    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
                    
                elif name == "list-tables":
                    connection_name = arguments.get("connection_name")
                    tables = self.odbc.list_tables(connection_name)
                    
                    # Format the results for better readability
                    result_text = "### Tables:\n\n"
                    for table in tables:
                        schema_prefix = f"{table['schema']}." if table['schema'] else ""
                        result_text += f"- {schema_prefix}{table['name']}\n"
                        
                    return [types.TextContent(type="text", text=result_text)]
                    
                elif name == "get-table-schema":
                    table_name = arguments.get("table_name")
                    if not table_name:
                        raise ValueError("Table name is required")
                        
                    connection_name = arguments.get("connection_name")
                    columns = self.odbc.get_table_schema(table_name, connection_name)
                    
                    # Format the results for better readability
                    result_text = f"### Schema for table {table_name}:\n\n"
                    result_text += "| Column | Type | Size | Nullable |\n"
                    result_text += "| ------ | ---- | ---- | -------- |\n"
                    
                    for column in columns:
                        result_text += f"| {column['name']} | {column['type']} | {column['size']} | {'Yes' if column['nullable'] else 'No'} |\n"
                        
                    return [types.TextContent(type="text", text=result_text)]
                    
                elif name == "execute-query":
                    sql = arguments.get("sql")
                    if not sql:
                        raise ValueError("SQL query is required")
                        
                    connection_name = arguments.get("connection_name")
                    max_rows = arguments.get("max_rows")
                    
                    column_names, rows = self.odbc.execute_query(sql, connection_name, max_rows)
                    
                    # Format the results as a markdown table
                    if not column_names:
                        return [types.TextContent(type="text", text="Query executed successfully, but no results were returned.")]
                        
                    # Create the results table
                    result_text = "### Query Results:\n\n"
                    
                    # Add the header row
                    result_text += "| " + " | ".join(column_names) + " |\n"
                    
                    # Add the separator row
                    result_text += "| " + " | ".join(["---"] * len(column_names)) + " |\n"
                    
                    # Add the data rows
                    for row in rows:
                        result_text += "| " + " | ".join(str(value) if value is not None else "NULL" for value in row) + " |\n"
                        
                    # Add the row count
                    result_text += f"\n\n_Returned {len(rows)} rows_"
                    
                    # Check if we hit the row limit
                    if max_rows and len(rows) >= max_rows:
                        result_text += f" _(limited to {max_rows} rows)_"
                        
                    return [types.TextContent(type="text", text=result_text)]
                    
                else:
                    raise ValueError(f"Unknown tool: {name}")
                    
            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}")
                error_message = f"Error executing {name}: {str(e)}"
                return [types.TextContent(type="text", text=error_message)]
                
    async def run(self):
        """Run the MCP server."""
        try:
            initialization_options = InitializationOptions(
                server_name="odbc-mcp-server",
                server_version="0.1.0",
                capabilities=self.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            )
            
            async with stdio_server() as (read_stream, write_stream):
                logger.info("Starting ODBC MCP Server")
                await self.server.run(
                    read_stream,
                    write_stream,
                    initialization_options,
                )
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
        finally:
            # Clean up connections
            self.odbc.close_all_connections()