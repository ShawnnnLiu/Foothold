"""Canonical text dump of a SQLite artifact.

`canonical_dump` is the single definition of SQLite artifact identity:
build tooling's `--check` modes compare `canonical_dump(committed)` to
`canonical_dump(regenerated)` to prove byte-identical regeneration.

The `schema_version` table is deliberately included so component-version
drift fails the check. Virtual-table shadow tables (FTS5 internals, names
containing `_fts`) are excluded from row dumps, but declared
`CREATE VIRTUAL TABLE` statements are included.
"""

import json
import sqlite3
from pathlib import Path


def canonical_dump(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        lines: list[str] = []
        for name, create_sql in tables:
            lines.append(" ".join(create_sql.split()))
            if "_fts" not in name:
                probe = connection.execute(f'SELECT * FROM "{name}" LIMIT 0')
                column_count = len(probe.description)
                order_by = ", ".join(str(i) for i in range(1, column_count + 1))
                rows = connection.execute(f'SELECT * FROM "{name}" ORDER BY {order_by}')
                lines.extend(json.dumps(list(row), sort_keys=True) for row in rows)
            lines.append("")
        return "\n".join(lines)
    finally:
        connection.close()
