"""
Configuration management for ODBC MCP Server.
Handles loading and validating ODBC connection settings.
"""

import os
import json
from pathlib import Path
from typing import Dict, Optional, List, Any
import configparser
from pydantic import BaseModel, Field, validator


class ODBCConnection(BaseModel):
    """ODBC connection configuration model."""
    name: str
    connection_string: Optional[str] = None
    dsn: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    driver: Optional[str] = None
    server: Optional[str] = None
    database: Optional[str] = None
    additional_params: Dict[str, str] = Field(default_factory=dict)
    readonly: bool = True  # Enforce read-only mode
    
    @validator('connection_string', 'dsn', 'username', 'password', 'driver', 'server', 'database', pre=True)
    def empty_str_to_none(cls, v):
        """Convert empty strings to None."""
        if v == "":
            return None
        return v
    
    def get_connection_string(self) -> str:
        """Generate complete connection string for pyodbc."""
        # If a full connection string is provided, use it
        if self.connection_string:
            return self.connection_string
        
        # Otherwise build from components
        parts = []
        
        if self.dsn:
            parts.append(f"DSN={self.dsn}")
        if self.driver:
            parts.append(f"Driver={{{self.driver}}}")
        if self.server:
            parts.append(f"Server={self.server}")
        if self.database:
            parts.append(f"Database={self.database}")
        if self.username:
            parts.append(f"UID={self.username}")
        if self.password:
            parts.append(f"PWD={self.password}")
            
        # Add any additional parameters
        for key, value in self.additional_params.items():
            parts.append(f"{key}={value}")
        
        return ";".join(parts)


class ServerConfig(BaseModel):
    """Main server configuration."""
    connections: Dict[str, ODBCConnection] = Field(default_factory=dict)
    default_connection: Optional[str] = None
    max_rows: int = 1000  # Default limit for query results
    timeout: int = 30  # Default timeout in seconds
    
    @validator('default_connection')
    def check_default_connection(cls, v, values):
        """Ensure default_connection references a valid connection."""
        if v is not None and v not in values.get('connections', {}):
            raise ValueError(f"Default connection '{v}' not found in configured connections")
        return v


def load_from_ini(file_path: str) -> ServerConfig:
    """Load configuration from an INI file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    
    config = configparser.ConfigParser()
    config.read(file_path)
    
    connections = {}
    default_connection = None
    max_rows = 1000
    timeout = 30
    
    # Extract server config
    if 'SERVER' in config:
        server_config = config['SERVER']
        default_connection = server_config.get('default_connection')
        max_rows = server_config.getint('max_rows', 1000)
        timeout = server_config.getint('timeout', 30)
    
    # Extract connection configs
    for section in config.sections():
        if section == 'SERVER':
            continue
            
        # This is a connection section
        connection_config = dict(config[section])
        
        # Handle additional parameters (anything not specifically processed)
        additional_params = {}
        for key, value in connection_config.items():
            if key not in ['connection_string', 'dsn', 'username', 'password', 
                          'driver', 'server', 'database', 'readonly']:
                additional_params[key] = value
                
        # Create the connection object
        readonly = connection_config.get('readonly', 'true').lower() in ['true', 'yes', '1', 'on']
        connection = ODBCConnection(
            name=section,
            connection_string=connection_config.get('connection_string'),
            dsn=connection_config.get('dsn'),
            username=connection_config.get('username'),
            password=connection_config.get('password'),
            driver=connection_config.get('driver'),
            server=connection_config.get('server'),
            database=connection_config.get('database'),
            additional_params=additional_params,
            readonly=readonly
        )
        
        connections[section] = connection
    
    return ServerConfig(
        connections=connections,
        default_connection=default_connection,
        max_rows=max_rows,
        timeout=timeout
    )


def load_from_claude_config(claude_config_path: Optional[str] = None) -> Optional[ServerConfig]:
    """
    Load configuration from Claude Desktop's config file.
    
    Looks for a configuration section under mcpServerEnv.odbc_mcp_server
    """
    if claude_config_path is None:
        # Default paths for Claude Desktop config
        if os.name == 'nt':  # Windows
            claude_config_path = os.path.join(os.environ.get('APPDATA', ''), 'Claude', 'claude_desktop_config.json')
        else:  # macOS
            claude_config_path = os.path.expanduser('~/Library/Application Support/Claude/claude_desktop_config.json')
    
    if not os.path.exists(claude_config_path):
        return None
        
    try:
        with open(claude_config_path, 'r') as f:
            claude_config = json.load(f)
            
        # Check if our server config exists
        if 'mcpServerEnv' not in claude_config or 'odbc_mcp_server' not in claude_config['mcpServerEnv']:
            return None
            
        odbc_config = claude_config['mcpServerEnv']['odbc_mcp_server']
        
        # Process connections
        connections = {}
        for conn_name, conn_config in odbc_config.get('connections', {}).items():
            connections[conn_name] = ODBCConnection(
                name=conn_name,
                **conn_config
            )
            
        return ServerConfig(
            connections=connections,
            default_connection=odbc_config.get('default_connection'),
            max_rows=odbc_config.get('max_rows', 1000),
            timeout=odbc_config.get('timeout', 30)
        )
    except Exception as e:
        print(f"Error loading Claude config: {e}")
        return None


def load_config(config_path: Optional[str] = None) -> ServerConfig:
    """
    Load configuration from file or Claude Desktop config.
    
    Order of precedence:
    1. Specified config file path
    2. ENV variable ODBC_MCP_CONFIG
    3. Claude Desktop config
    4. Default config path (./config/config.ini)
    """
    # Check specified path
    if config_path and os.path.exists(config_path):
        return load_from_ini(config_path)
    
    # Check environment variable
    env_config_path = os.environ.get('ODBC_MCP_CONFIG')
    if env_config_path and os.path.exists(env_config_path):
        return load_from_ini(env_config_path)
    
    # Try Claude Desktop config
    claude_config = load_from_claude_config()
    if claude_config:
        return claude_config
    
    # Try default path
    default_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.ini')
    if os.path.exists(default_path):
        return load_from_ini(default_path)
    
    # If no config found, raise error
    raise FileNotFoundError(
        "No configuration found. Please provide a config file or set the ODBC_MCP_CONFIG environment variable."
    )