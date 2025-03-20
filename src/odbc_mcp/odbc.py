"""
ODBC connection and query management.
Handles database connections and provides methods for executing queries.
"""

import pyodbc
import re
from typing import List, Dict, Any, Optional, Tuple, Union
from .config import ODBCConnection, ServerConfig


class ODBCHandler:
    """Handles ODBC connections and query execution."""
    
    def __init__(self, config: ServerConfig):
        """Initialize with server configuration."""
        self.config = config
        self.connections = config.connections
        self.default_connection = config.default_connection
        self.max_rows = config.max_rows
        self.timeout = config.timeout
        self.active_connections: Dict[str, pyodbc.Connection] = {}
        
    def __del__(self):
        """Ensure all connections are closed on deletion."""
        self.close_all_connections()
        
    def close_all_connections(self):
        """Close all active database connections."""
        for conn_name, conn in self.active_connections.items():
            try:
                conn.close()
            except Exception:
                pass
        self.active_connections = {}
        
    def get_connection(self, connection_name: Optional[str] = None) -> pyodbc.Connection:
        """
        Get a database connection by name or use the default.
        
        Args:
            connection_name: Name of the connection to use, or None for default
            
        Returns:
            pyodbc.Connection: Active database connection
            
        Raises:
            ValueError: If connection name doesn't exist
            ConnectionError: If connection fails
        """
        # Use default if not specified
        if connection_name is None:
            if self.default_connection is None:
                if len(self.connections) == 1:
                    # If only one connection is defined, use it
                    connection_name = list(self.connections.keys())[0]
                else:
                    raise ValueError("No default connection specified and multiple connections exist")
            else:
                connection_name = self.default_connection
                
        # Check if connection exists
        if connection_name not in self.connections:
            raise ValueError(f"Connection '{connection_name}' not found in configuration")
            
        # Return existing connection if available
        if connection_name in self.active_connections:
            try:
                # Test the connection with a simple query
                self.active_connections[connection_name].cursor().execute("SELECT 1")
                return self.active_connections[connection_name]
            except Exception:
                # Connection is stale, close it
                try:
                    self.active_connections[connection_name].close()
                except Exception:
                    pass
                del self.active_connections[connection_name]
                
        # Create new connection
        connection_config = self.connections[connection_name]
        conn_str = connection_config.get_connection_string()
        
        try:
            # Detect if this is ProvideX or has ProvideX in the connection string
            is_providex = "PROVIDEX" in conn_str.upper() or connection_name.upper() == "SAGE100"
            
            # Special handling for ProvideX
            if is_providex:
                # For ProvideX, explicitly set autocommit at connection time
                connection = pyodbc.connect(conn_str, timeout=self.timeout, autocommit=True)
            else:
                # For other drivers, use the standard connection approach
                connection = pyodbc.connect(conn_str, timeout=self.timeout)
                
            # Set encoding options
            connection.setdecoding(pyodbc.SQL_CHAR, encoding='utf-8')
            connection.setdecoding(pyodbc.SQL_WCHAR, encoding='utf-8')
            connection.setencoding(encoding='utf-8')
                
            self.active_connections[connection_name] = connection
            return connection
        except Exception as e:
            raise ConnectionError(f"Failed to connect to '{connection_name}': {str(e)}")
            
    def list_connections(self) -> List[str]:
        """List all available connection names."""
        return list(self.connections.keys())
        
    def get_available_dsns(self) -> List[Dict[str, str]]:
        """
        Get a list of all available DSNs on the system.
        
        Returns:
            List of dictionaries containing DSN information
        """
        dsns = []
        for dsn_info in pyodbc.dataSources().items():
            dsns.append({
                "name": dsn_info[0],
                "driver": dsn_info[1]
            })
        return dsns
        
    def list_tables(self, connection_name: Optional[str] = None) -> List[Dict[str, str]]:
        """
        List all tables in the database.
        
        Args:
            connection_name: Name of the connection to use, or None for default
            
        Returns:
            List of dictionaries with table information
        """
        connection = self.get_connection(connection_name)
        cursor = connection.cursor()
        
        tables = []
        try:
            for table_info in cursor.tables():
                if table_info.table_type == 'TABLE':
                    tables.append({
                        "catalog": table_info.table_cat or "",
                        "schema": table_info.table_schem or "",
                        "name": table_info.table_name,
                        "type": table_info.table_type
                    })
            return tables
        except Exception as e:
            # For some ODBC drivers that don't support table enumeration,
            # fallback to a SQL query if possible
            try:
                sql_tables = []
                cursor.execute("SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
                for row in cursor.fetchall():
                    sql_tables.append({
                        "catalog": row[0] or "",
                        "schema": row[1] or "",
                        "name": row[2],
                        "type": row[3]
                    })
                return sql_tables
            except Exception:
                # If everything fails, raise the original error
                raise ConnectionError(f"Failed to list tables: {str(e)}")
                
    def get_table_schema(self, table_name: str, connection_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get schema information for a table.
        
        Args:
            table_name: Name of the table
            connection_name: Name of the connection to use, or None for default
            
        Returns:
            List of dictionaries with column information
        """
        connection = self.get_connection(connection_name)
        cursor = connection.cursor()
        
        # Try to extract schema and table name
        schema_parts = table_name.split('.')
        if len(schema_parts) > 1:
            schema_name = schema_parts[0]
            table_name = schema_parts[1]
        else:
            schema_name = None
            
        columns = []
        try:
            # Use metadata API if available
            column_metadata = cursor.columns(table=table_name, schema=schema_name)
            for column in column_metadata:
                columns.append({
                    "name": column.column_name,
                    "type": column.type_name,
                    "size": column.column_size,
                    "nullable": column.nullable == 1,
                    "position": column.ordinal_position
                })
                
            # If we got column info, return it
            if columns:
                return columns
                
            # Otherwise, try SQL approach
            raise Exception("No columns found")
        except Exception:
            # Try SQL approach for drivers that don't support metadata
            try:
                sql = f"SELECT * FROM {table_name} WHERE 1=0"
                cursor.execute(sql)
                
                columns = []
                for i, column in enumerate(cursor.description):
                    columns.append({
                        "name": column[0],
                        "type": self._get_type_name(column[1]),
                        "size": column[3],
                        "nullable": column[6] == 1,
                        "position": i+1
                    })
                return columns
            except Exception as e:
                raise ValueError(f"Failed to get schema for table '{table_name}': {str(e)}")
                
    def _get_type_name(self, type_code: int) -> str:
        """Convert ODBC type code to type name."""
        type_map = {
            pyodbc.SQL_CHAR: "CHAR",
            pyodbc.SQL_VARCHAR: "VARCHAR",
            pyodbc.SQL_LONGVARCHAR: "LONGVARCHAR",
            pyodbc.SQL_WCHAR: "WCHAR",
            pyodbc.SQL_WVARCHAR: "WVARCHAR",
            pyodbc.SQL_WLONGVARCHAR: "WLONGVARCHAR",
            pyodbc.SQL_DECIMAL: "DECIMAL",
            pyodbc.SQL_NUMERIC: "NUMERIC",
            pyodbc.SQL_SMALLINT: "SMALLINT",
            pyodbc.SQL_INTEGER: "INTEGER",
            pyodbc.SQL_REAL: "REAL",
            pyodbc.SQL_FLOAT: "FLOAT",
            pyodbc.SQL_DOUBLE: "DOUBLE",
            pyodbc.SQL_BIT: "BIT",
            pyodbc.SQL_TINYINT: "TINYINT",
            pyodbc.SQL_BIGINT: "BIGINT",
            pyodbc.SQL_BINARY: "BINARY",
            pyodbc.SQL_VARBINARY: "VARBINARY",
            pyodbc.SQL_LONGVARBINARY: "LONGVARBINARY",
            pyodbc.SQL_TYPE_DATE: "DATE",
            pyodbc.SQL_TYPE_TIME: "TIME",
            pyodbc.SQL_TYPE_TIMESTAMP: "TIMESTAMP",
            pyodbc.SQL_SS_VARIANT: "SQL_VARIANT",
            pyodbc.SQL_SS_UDT: "UDT",
            pyodbc.SQL_SS_XML: "XML",
            pyodbc.SQL_SS_TIME2: "TIME",
            pyodbc.SQL_SS_TIMESTAMPOFFSET: "TIMESTAMPOFFSET",
        }
        return type_map.get(type_code, f"UNKNOWN({type_code})")
        
    def is_read_only_query(self, sql: str) -> bool:
        """
        Check if an SQL query is read-only.
        
        Args:
            sql: SQL query to check
            
        Returns:
            bool: True if the query is read-only, False otherwise
        """
        # Remove comments and normalize whitespace
        sql = re.sub(r'--.*?(\n|$)', ' ', sql)
        sql = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.DOTALL)
        sql = ' '.join(sql.split()).strip().upper()
        
        # Check for data modification statements
        data_modification_patterns = [
            r'^\s*INSERT\s+INTO',
            r'^\s*UPDATE\s+',
            r'^\s*DELETE\s+FROM',
            r'^\s*DROP\s+',
            r'^\s*CREATE\s+',
            r'^\s*ALTER\s+',
            r'^\s*TRUNCATE\s+',
            r'^\s*GRANT\s+',
            r'^\s*REVOKE\s+',
            r'^\s*MERGE\s+',
            r'^\s*EXEC\s+',
            r'^\s*EXECUTE\s+',
            r'^\s*CALL\s+',
            r'^\s*SET\s+',
            r'^\s*USE\s+',
        ]
        
        for pattern in data_modification_patterns:
            if re.search(pattern, sql):
                return False
                
        # If no modification patterns are found, it's likely read-only
        return True
        
    def execute_query(self, sql: str, connection_name: Optional[str] = None, 
                     max_rows: Optional[int] = None) -> Tuple[List[str], List[List[Any]]]:
        """
        Execute an SQL query and return results.
        
        Args:
            sql: SQL query to execute
            connection_name: Name of the connection to use, or None for default
            max_rows: Maximum number of rows to return, or None for default
            
        Returns:
            Tuple of column names and result rows
        """
        # Check if query is read-only for connections with readonly flag
        connection = self.get_connection(connection_name)
        connection_config = self.connections[connection_name or self.default_connection]
        
        if connection_config.readonly and not self.is_read_only_query(sql):
            raise ValueError("Write operations are not allowed on read-only connections")
            
        # Set max rows limit
        if max_rows is None:
            max_rows = self.max_rows
            
        # Execute the query
        cursor = connection.cursor()
        cursor.execute(sql)
        
        # Get column names
        column_names = [column[0] for column in cursor.description] if cursor.description else []
        
        # Fetch results with row limit
        results = []
        row_count = 0
        
        for row in cursor:
            formatted_row = []
            for value in row:
                # Convert specific ODBC types to strings for JSON compatibility
                if isinstance(value, (bytearray, bytes)):
                    formatted_row.append(str(value))
                else:
                    formatted_row.append(value)
            results.append(formatted_row)
            
            row_count += 1
            if row_count >= max_rows:
                break
                
        return column_names, results
        
    def test_connection(self, connection_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Test a database connection and return information.
        
        Args:
            connection_name: Name of the connection to use, or None for default
            
        Returns:
            Dictionary with connection status and info
        """
        try:
            # Get connection
            conn = self.get_connection(connection_name)
            cursor = conn.cursor()
            
            # Get database info
            database_info = {}
            
            try:
                cursor.execute("SELECT @@version")
                version = cursor.fetchone()
                if version:
                    database_info["version"] = version[0]
            except Exception:
                # Some databases don't support @@version
                pass
                
            # Get connection info
            conn_info = {
                "driver_name": conn.getinfo(pyodbc.SQL_DRIVER_NAME) if hasattr(conn, 'getinfo') else "Unknown",
                "driver_version": conn.getinfo(pyodbc.SQL_DRIVER_VER) if hasattr(conn, 'getinfo') else "Unknown",
                "database_name": conn.getinfo(pyodbc.SQL_DATABASE_NAME) if hasattr(conn, 'getinfo') else "Unknown",
                "dbms_name": conn.getinfo(pyodbc.SQL_DBMS_NAME) if hasattr(conn, 'getinfo') else "Unknown",
                "dbms_version": conn.getinfo(pyodbc.SQL_DBMS_VER) if hasattr(conn, 'getinfo') else "Unknown",
            }
            
            return {
                "status": "connected",
                "connection_name": connection_name or self.default_connection,
                "connection_info": conn_info,
                "database_info": database_info
            }
            
        except Exception as e:
            return {
                "status": "error",
                "connection_name": connection_name or self.default_connection,
                "error": str(e)
            }