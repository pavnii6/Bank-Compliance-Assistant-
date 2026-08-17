"""Configuration settings for the chatbot application."""
import os
from pathlib import Path

# Database settings
DB_FILE = os.environ.get("CHATBOT_DB_FILE", "bank.db")
DB_INIT_SQL = Path(__file__).parent / "init.sql"

# Account number mappings (for client-side account name resolution)
ACCOUNT_MAPPINGS = {
    "checking": "1234567890",
    "chequing": "1234567890",
    "cheque": "1234567890",
    "saving": "2345678901",
    "savings": "2345678901",
    "credit": "3456789012",
    "credit card": "3456789012"
}

# Default user for testing
DEFAULT_USER_ID = "test1"

# Vector database settings
VECTOR_DB_DIR = os.environ.get("VECTOR_DB_DIR", "./chroma_db")
DOCS_DIRECTORY = os.environ.get("DOCS_DIRECTORY", "./rbc_documents")

# MCP server settings
# MCP_HOST / MCP_PORT control what address the MCP *server* binds to.
# On Render, MCP_HOST must be 0.0.0.0 and PORT is injected automatically.
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("PORT", os.environ.get("MCP_PORT", "8050")))
MCP_NAME = os.environ.get("MCP_NAME", "RBC-RAG-MCP")

# Full SSE URL the Flask client connects to.
# In production set MCP_URL to the public URL of your Render MCP service, e.g.:
#   https://bank-mcp-server.onrender.com/sse
# Locally it falls back to localhost.
MCP_URL = os.environ.get("MCP_URL", f"http://127.0.0.1:{MCP_PORT}/sse")
