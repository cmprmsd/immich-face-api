import logging
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import get_config

logger = logging.getLogger(__name__)

# Schema from Immich GitHub repo (server/src/schema/tables/):
# - face_search: embedding (vector), faceId -> asset_face.id
# - asset_face: id, personId -> person.id, deletedAt, isVisible
# - person: id, name, isHidden
# See: asset-face.table.ts, face-search.table.ts, person.table.ts
_schema: dict[str, Any] | None = None

# Try Immich v2 schema first: face_search (embedding) -> asset_face (personId) -> person (name).
# Column names are camelCase in the repo (faceId, personId, isHidden).
FIND_PERSON_IMMICH_V2_SQL = """
SELECT p.name, (fs.embedding <=> %s::vector) AS dist
FROM face_search fs
JOIN asset_face af ON af.id = fs."faceId"
JOIN person p ON p.id = af."personId"
WHERE af."deletedAt" IS NULL AND af."isVisible" IS TRUE
  AND (p."isHidden" IS NULL OR p."isHidden" = false)
ORDER BY fs.embedding <=> %s::vector
LIMIT 1
"""

# Fallback: discover any table that has both embedding and person_id/personId (legacy or custom).
DISCOVER_FACE_TABLE_SQL = """
SELECT c.table_schema, c.table_name
FROM information_schema.columns c
WHERE c.column_name = 'embedding'
  AND c.table_schema NOT IN ('pg_catalog', 'information_schema')
  AND EXISTS (
    SELECT 1 FROM information_schema.columns c2
    WHERE c2.table_schema = c.table_schema AND c2.table_name = c.table_name
      AND c2.column_name IN ('person_id', 'personId')
  )
ORDER BY c.table_schema, c.table_name
LIMIT 1
"""
DISCOVER_PERSON_COLUMN_SQL = """
SELECT column_name FROM information_schema.columns
WHERE table_schema = %s AND table_name = %s AND column_name IN ('person_id', 'personId')
LIMIT 1
"""
DISCOVER_HIDDEN_COLUMN_SQL = """
SELECT column_name FROM information_schema.columns
WHERE table_schema = %s AND table_name = 'person' AND column_name IN ('is_hidden', 'isHidden')
LIMIT 1
"""


@contextmanager
def get_connection():
    cfg = get_config()["db"]
    conn = psycopg.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
        row_factory=dict_row,
    )
    try:
        yield conn
    finally:
        conn.close()


def _discover_schema() -> dict[str, Any]:
    """Find face table and column names for fallback when Immich v2 schema does not exist."""
    global _schema
    if _schema is not None:
        return _schema
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(DISCOVER_FACE_TABLE_SQL)
            row = cur.fetchone()
            if not row:
                raise RuntimeError(
                    "No table with both 'embedding' and person_id/personId found. "
                    "Ensure Immich has run face detection and the DB has the face table."
                )
            schema_name = row["table_schema"]
            table_name = row["table_name"]
            cur.execute(DISCOVER_PERSON_COLUMN_SQL, (schema_name, table_name))
            person_col_row = cur.fetchone()
            person_col = (person_col_row["column_name"] if person_col_row else "person_id")
            cur.execute(DISCOVER_HIDDEN_COLUMN_SQL, (schema_name,))
            hidden_row = cur.fetchone()
            hidden_col = (hidden_row["column_name"] if hidden_row else "is_hidden")
    person_col_quoted = f'"{person_col}"' if person_col == "personId" else person_col
    hidden_col_quoted = f'"{hidden_col}"' if hidden_col == "isHidden" else hidden_col
    qual = f'"{schema_name}"."{table_name}"' if schema_name != "public" else table_name
    _schema = {
        "face_table": qual,
        "person_col": person_col_quoted,
        "hidden_col": hidden_col_quoted,
    }
    logger.info("db: fallback schema face_table=%s", qual)
    return _schema


def embedding_to_vector_literal(embedding: list[float]) -> str:
    """Format embedding list as PostgreSQL vector literal for parameter binding."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _find_person_sql_fallback() -> str:
    s = _discover_schema()
    return f"""
SELECT p.name, (af.embedding <=> %s::vector) AS dist
FROM {s["face_table"]} af
JOIN person p ON p.id = af.{s["person_col"]}
WHERE af.embedding IS NOT NULL
  AND (p.{s["hidden_col"]} IS NULL OR p.{s["hidden_col"]} = false)
ORDER BY af.embedding <=> %s::vector
LIMIT 1
"""


def find_person_name_for_embedding(embedding: list[float], max_distance: float) -> tuple[str | None, str]:
    """
    Return (name, reason) for the closest person, or (None, reason) if no match.
    Tries Immich v2 schema (face_search -> asset_face -> person) then discovery fallback.
    """
    vec = embedding_to_vector_literal(embedding)
    row = None
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(FIND_PERSON_IMMICH_V2_SQL, (vec, vec))
                row = cur.fetchone()
            except psycopg.Error:
                conn.rollback()
                try:
                    sql = _find_person_sql_fallback()
                    cur.execute(sql, (vec, vec))
                    row = cur.fetchone()
                except psycopg.Error as e:
                    raise RuntimeError(
                        "Face lookup failed (tried Immich v2 schema and discovery). "
                        "Check that face_search, asset_face, and person tables exist."
                    ) from e
    if not row or row["dist"] is None:
        return (None, "no row (no faces in DB with personId set?)")
    dist = float(row["dist"])
    name = row["name"]
    if dist > max_distance:
        return (None, f"closest {name!r} dist={dist:.2f} > threshold {max_distance:.2f}")
    return (name, f"dist={dist:.2f}")
