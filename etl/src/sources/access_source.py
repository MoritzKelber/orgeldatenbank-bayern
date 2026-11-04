"""Read raw table rows from the legacy bayern.accdb via ODBC.

Only does plain SELECT * extraction - all cleaning/joining happens in
etl/src/transform, so this module can be swapped for a SQL Server source
without touching any transform code.
"""
from __future__ import annotations

import pyodbc

TABLES = (
    "Bydaten",
    "Bybauer",
    "Literatur",
    "Byliteratur",
    "Bylkr",
    "Bystichworte",
)


def connect(db_path: str) -> pyodbc.Connection:
    conn_str = (
        r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"Dbq={db_path};"
    )
    return pyodbc.connect(conn_str)


def fetch_all(conn: pyodbc.Connection, table: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM [{table}]")
    columns = [col[0] for col in cur.description]
    rows = []
    for row in cur.fetchall():
        rows.append({col: row[i] for i, col in enumerate(columns)})
    return rows


def fetch_source(db_path: str) -> dict[str, list[dict]]:
    conn = connect(db_path)
    try:
        return {table: fetch_all(conn, table) for table in TABLES}
    finally:
        conn.close()
