"""POST /api/ask — text-to-SQL over data/analytics.db."""

import json
import re
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from app.llm.resolver import resolve_llm_provider
from app.llm.schema_card import build_schema_card
from app.llm.sql_guard import UnsafeSQLError, run_readonly_query

router = APIRouter()

SQL_PROMPT_TEMPLATE = """You are a SQL analyst for a SQLite database called Kestrel Provisions Control Tower.

Schema (table_name(column_name type, ...)):
{schema_card}

Write exactly one read-only SQL SELECT statement that answers this question:
"{question}"

Rules:
- Output ONLY the SQL statement — no markdown fences, no explanation, no trailing semicolon commentary.
- A single SELECT statement only (a WITH ... SELECT CTE is fine).
- Never use INSERT, UPDATE, DELETE, DROP, ALTER, ATTACH, PRAGMA, or any statement that writes.
- Add a LIMIT clause unless the question calls for a single aggregate value.
"""

ANSWER_PROMPT_TEMPLATE = """Question: "{question}"

SQL used: {sql}

Result rows (JSON): {rows_json}

In 1-3 sentences, answer the question in plain English using these results. Be specific with numbers.
"""


class AskRequest(BaseModel):
    question: str


FENCE_RE = re.compile(r"```(?:sql)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_sql(text: str) -> str:
    """Pull the SQL out of a raw LLM response.

    Despite the prompt's "output ONLY the SQL statement" instruction, weaker
    models (observed with a local Ollama model) routinely wrap the query in
    explanatory prose before and after a fenced code block rather than
    returning bare SQL — so search for a fence anywhere in the response
    instead of assuming the whole reply is (at most) one fenced block.
    """
    match = FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


@router.post("/api/ask")
def ask(body: AskRequest) -> dict:
    provider = resolve_llm_provider()
    if provider is None:
        return {"error": "no_llm_configured"}

    schema_card = build_schema_card()
    sql_prompt = SQL_PROMPT_TEMPLATE.format(schema_card=schema_card, question=body.question)
    sql = _extract_sql(provider.ask(sql_prompt))

    try:
        columns, rows = run_readonly_query(sql)
    except UnsafeSQLError as exc:
        return {"error": "unsafe_sql_rejected", "sql": sql, "detail": str(exc)}

    answer_prompt = ANSWER_PROMPT_TEMPLATE.format(
        question=body.question, sql=sql, rows_json=json.dumps(rows, default=str)[:4000]
    )
    natural_language_answer = provider.ask(answer_prompt)

    return {
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "natural_language_answer": natural_language_answer,
    }
