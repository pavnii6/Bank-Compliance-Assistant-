"""MCP SSE server exposing banking tools and RAG Q&A."""
import os
import sys
import datetime
from decimal import Decimal

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Ensure the project root is on the path so chatbot.* imports work
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Load .env (no-op on Render where vars are set via dashboard)
load_dotenv(os.path.join(_project_root, ".env"))

# ── Database init ────────────────────────────────────────────────────────────
from chatbot.database import init_db
init_db()

# ── RAG chatbot (singleton) ──────────────────────────────────────────────────
from chatbot.rag.rag_chatbot import RBCChatbot
chatbot = RBCChatbot()

# ── Account helpers ──────────────────────────────────────────────────────────
from chatbot.account import (
    list_accounts,
    list_transfer_target_accounts,
    transfer_between_accounts,
)

# ── MCP server ───────────────────────────────────────────────────────────────
from chatbot.config import MCP_NAME, MCP_HOST, MCP_PORT

mcp = FastMCP(name=MCP_NAME, host=MCP_HOST, port=MCP_PORT)


@mcp.tool()
def answer_banking_question(question: str) -> dict:
    """
    Answer a banking question using the RAG system with RBC documentation.
    Only for banking, financial services, or RBC-related questions.
    Returns the answer and sources.
    """
    print(f"[RAG] Processing question: {question}")
    result = chatbot.answer_question(question)
    print(f"[RAG] Found answer with {len(result['sources'])} sources")
    return {"answer": result["answer"], "sources": result["sources"]}


@mcp.tool()
def list_user_accounts(user_id: str) -> list:
    """List all accounts for a given user."""
    accounts = list_accounts(user_id)
    print(f"[DEBUG] list_user_accounts: user_id={user_id}, count={len(accounts)}")
    return [account.__dict__ for account in accounts]


@mcp.tool()
def list_target_accounts(user_id: str, from_account: str) -> list:
    """List all other accounts this user can transfer to."""
    accounts = list_transfer_target_accounts(user_id, from_account)
    print(f"[DEBUG] list_target_accounts: user_id={user_id}, from={from_account}")
    return [account.__dict__ for account in accounts]


@mcp.tool()
def transfer_funds(user_id: str, from_account: str, to_account: str, amount: str) -> str:
    """Transfer funds from one account to another."""
    print(f"[DEBUG] transfer_funds: user_id={user_id}, from={from_account}, to={to_account}, amount={amount}")
    try:
        clean_amount = amount.replace("$", "").replace(",", "").strip()
        decimal_amount = Decimal(clean_amount)
        transfer_between_accounts(user_id, from_account, to_account, decimal_amount)
        return f"Transferred ${clean_amount} from account {from_account} to account {to_account}."
    except Exception as exc:
        print(f"[ERROR] transfer_funds failed: {exc}")
        return f"Transfer failed: {exc}"


@mcp.tool()
def get_account_balance(user_id: str, account_number: str) -> dict:
    """Get the balance of a specific account."""
    print(f"[DEBUG] get_account_balance: user_id={user_id}, account={account_number}")
    for account in list_accounts(user_id):
        if account.account_number == account_number:
            return {
                "account_number": account.account_number,
                "account_name": account.account_name,
                "balance": str(account.balance),
                "currency": "CAD",
            }
    return {"error": f"Account {account_number} not found."}


@mcp.tool()
def get_transaction_history(user_id: str, account_number: str, days: int = 30) -> list:
    """Get the transaction history for a specific account."""
    print(f"[DEBUG] get_transaction_history: user_id={user_id}, account={account_number}, days={days}")

    import sqlite3
    from chatbot.database import DB_FILE

    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()

    cur.execute(
        """
        SELECT
            TransactionNumber,
            TransferDateTime,
            CASE
                WHEN FromAccountNumber = :acct THEN 'debit'
                ELSE 'credit'
            END AS transaction_type,
            CASE
                WHEN FromAccountNumber = :acct THEN -Amount
                ELSE Amount
            END AS amount,
            CASE
                WHEN FromAccountNumber = :acct THEN 'Transfer to ' || ToAccountNumber
                ELSE 'Transfer from ' || FromAccountNumber
            END AS description,
            CASE
                WHEN FromAccountNumber = :acct THEN FromAccountBalance
                ELSE ToAccountBalance
            END AS balance_after
        FROM Transfers
        WHERE (FromAccountNumber = :acct OR ToAccountNumber = :acct)
          AND TransferDateTime >= :start_date
        ORDER BY TransferDateTime DESC
        """,
        {"acct": account_number, "start_date": start_date},
    )

    transactions = []
    for row in cur.fetchall():
        transactions.append({
            "transaction_id": row["TransactionNumber"],
            "date": row["TransferDateTime"].split("T")[0],
            "description": row["description"],
            "amount": str(Decimal(str(row["amount"]))),
            "transaction_type": row["transaction_type"],
            "balance_after": str(row["balance_after"]),
        })

    con.close()
    print(f"[DEBUG] Returning {len(transactions)} transactions")
    return transactions


if __name__ == "__main__":
    print(f"[INFO] Starting MCP server — host={MCP_HOST} port={MCP_PORT}")
    mcp.run(transport="sse")
