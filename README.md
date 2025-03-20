# ODBC MCP Server

An MCP (Model Context Protocol) server that enables LLM tools like Claude Desktop to query databases via ODBC connections. This server allows Claude and other MCP clients to access, analyze, and generate insights from database data while maintaining security and read-only safeguards.

## Features

- Connect to any ODBC-compatible database
- Support for multiple database connections
- Flexible configuration through config files or Claude Desktop settings
- Read-only safeguards to prevent data modification
- Easy installation with UV package manager
- Detailed error reporting and logging

## Prerequisites

- Python 3.10 or higher
- UV package manager
- ODBC drivers for your database(s) installed on your system
- For Sage 100 Advanced: ProvideX ODBC driver

## Installation

```bash
git clone https://github.com/tylerstoltz/mcp-odbc.git
cd mcp-odbc
uv venv
.venv\Scripts\activate # On Mac / Linux: source .venv/bin/activate (untested)
uv pip install -e .
```

## Configuration

The server can be configured through:

1. A dedicated config file
2. Environment variables
3. Claude Desktop configuration

### General Configuration Setup

Create a configuration file (`.ini`) with your database connection details:

```ini
[SERVER]
default_connection = my_database
max_rows = 1000
timeout = 30

[my_database]
dsn = MyDatabaseDSN
username = your_username
password = your_password
readonly = true
```

### SQLite Configuration

For SQLite databases with ODBC:

```ini
[SERVER]
default_connection = sqlite_db
max_rows = 1000
timeout = 30

[sqlite_db]
dsn = SQLite_DSN_Name
readonly = true
```

### Sage 100 ProvideX Configuration

ProvideX requires special configuration for compatibility. Use this minimal configuration for best results:

```ini
[SERVER]
default_connection = sage100
max_rows = 1000
timeout = 60

[sage100]
dsn = YOUR_PROVIDEX_DSN
username = your_username
password = your_password
company = YOUR_COMPANY_CODE
readonly = true
```

**Important notes for ProvideX:**
- Use a minimal configuration - adding extra parameters may cause connection issues
- Always set `readonly = true` for safety
- The `company` parameter is required for Sage 100 connections
- Avoid changing connection attributes after connection is established

### Claude Desktop Integration

To configure the server in Claude Desktop:

1. Open or create `claude_desktop_config.json`:
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

2. Add MCP server configuration:

```json
{
  "mcpServers": {
    "odbc": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\path\\to\\mcp-odbc",
        "run",
        "odbc-mcp-server",
        "--config", 
        "C:\\path\\to\\mcp-odbc\\config\\your_config.ini"
      ]
    }
  }
}
```

## Usage

### Starting the Server Manually

```bash
# Start with default configuration
odbc-mcp-server

# Start with a specific config file
odbc-mcp-server --config path/to/config.ini
```

### Using with Claude Desktop

1. Configure the server in Claude Desktop's config file as shown above
2. Restart Claude Desktop
3. The ODBC tools will automatically appear in the MCP tools list

### Available MCP Tools

The ODBC MCP server provides these tools:

1. **list-connections**: Lists all configured database connections
2. **list-available-dsns**: Lists all available DSNs on the system
3. **test-connection**: Tests a database connection and returns information
4. **list-tables**: Lists all tables in the database
5. **get-table-schema**: Gets schema information for a table
6. **execute-query**: Executes an SQL query and returns results

## Example Queries

Try these prompts in Claude Desktop after connecting the server:

- "Show me all the tables in the database"
- "What's the schema of the Customer table?"
- "Run a query to get the first 10 customers"
- "Find all orders placed in the last 30 days"
- "Analyze the sales data by region and provide insights"

## Troubleshooting

### Connection Issues

If you encounter connection problems:

1. Verify your ODBC drivers are installed correctly
2. Test your DSN using the ODBC Data Source Administrator
3. Check connection parameters in your config file
4. Look for detailed error messages in Claude Desktop logs

### ProvideX-Specific Issues

For Sage 100/ProvideX:
1. Use minimal connection configuration (DSN, username, password, company)
2. Make sure the Company parameter is correct
3. Use the special ProvideX configuration template
4. If you encounter `Driver not capable` errors, check that autocommit is being set at connection time

### Missing Tables

If tables aren't showing up:

1. Verify user permissions for the database account
2. Check if the company code is correct (for Sage 100)
3. Try using fully qualified table names (schema.table)

## License

MIT License - Copyright (c) 2024