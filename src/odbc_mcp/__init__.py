"""
ODBC MCP Server package.
Provides MCP tools for querying databases via ODBC.
"""

import asyncio
import argparse
import sys
from pathlib import Path
from .server import ODBCMCPServer


def main():
    """Main entry point for the package."""
    parser = argparse.ArgumentParser(description="ODBC MCP Server")
    parser.add_argument(
        "--config", "-c",
        help="Path to configuration file", 
        type=str
    )
    args = parser.parse_args()
    
    try:
        server = ODBCMCPServer(args.config)
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("Server shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


# Expose key classes at package level
from .config import ServerConfig, ODBCConnection
from .odbc import ODBCHandler

__all__ = ['ODBCMCPServer', 'ServerConfig', 'ODBCConnection', 'ODBCHandler', 'main']