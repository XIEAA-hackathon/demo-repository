"""One-time, count-verified SQLite -> PostgreSQL data transfer.

Run Alembic against an empty PostgreSQL database first. This tool never changes
the SQLite source and refuses to write if any application table in PostgreSQL
already contains rows.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, MetaData, Table, create_engine, func, inspect, select, text
from sqlalchemy.engine import Connection, Engine, make_url

from app.core.database import Base
from app.models import models  # noqa: F401 - registers every mapped table


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-url", required=True, help="Source URL, e.g. sqlite:////absolute/casino_hackathon.db")
    parser.add_argument("--postgres-url", required=True, help="Destination postgresql+psycopg URL")
    parser.add_argument("--dry-run", action="store_true", help="Validate schemas and print counts without writing")
    return parser.parse_args()


def _validate_backends(sqlite_url: str, postgres_url: str) -> None:
    if make_url(sqlite_url).get_backend_name() != "sqlite":
        raise ValueError("--sqlite-url must use the SQLite backend")
    if make_url(postgres_url).get_backend_name() != "postgresql":
        raise ValueError("--postgres-url must use the PostgreSQL backend")


def _model_tables() -> dict[str, Table]:
    # The users <-> teams FK cycle is handled explicitly by _insertion_plan.
    return {table.name: table for table in Base.metadata.tables.values()}


def _validate_schema(engine: Engine, table_names: set[str], label: str) -> None:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing_tables = table_names - existing
    if missing_tables:
        raise RuntimeError(f"{label} is missing tables: {sorted(missing_tables)}")
    for table_name in sorted(table_names):
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        expected = {column.name for column in Base.metadata.tables[table_name].columns}
        missing_columns = expected - actual
        if missing_columns:
            raise RuntimeError(f"{label}.{table_name} is missing columns: {sorted(missing_columns)}")


def _counts(connection: Connection, tables: dict[str, Table]) -> dict[str, int]:
    return {
        name: int(connection.execute(select(func.count()).select_from(table)).scalar_one())
        for name, table in sorted(tables.items())
    }


def _print_counts(label: str, counts: dict[str, int]) -> None:
    print(label)
    for table_name, count in counts.items():
        print(f"  {table_name}: {count}")


def _strongly_connected_components(tables: dict[str, Table]) -> list[set[str]]:
    graph = {
        name: {fk.column.table.name for fk in table.foreign_keys if fk.column.table.name in tables}
        for name, table in tables.items()
    }
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for dependency in graph[node]:
            if dependency not in indices:
                visit(dependency)
                lowlinks[node] = min(lowlinks[node], lowlinks[dependency])
            elif dependency in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[dependency])
        if lowlinks[node] == indices[node]:
            component: set[str] = set()
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.add(member)
                if member == node:
                    break
            components.append(component)

    for table_name in sorted(tables):
        if table_name not in indices:
            visit(table_name)
    return components


def _insertion_plan(tables: dict[str, Table]) -> tuple[list[str], dict[str, set[str]]]:
    deferred: dict[str, set[str]] = defaultdict(set)
    for component in _strongly_connected_components(tables):
        cyclic = len(component) > 1 or any(
            fk.column.table.name == table_name
            for table_name in component
            for fk in tables[table_name].foreign_keys
        )
        if not cyclic:
            continue
        for table_name in component:
            for fk in tables[table_name].foreign_keys:
                if fk.column.table.name in component:
                    if not fk.parent.nullable:
                        raise RuntimeError(
                            f"Cannot safely migrate non-null cyclic FK {table_name}.{fk.parent.name}"
                        )
                    deferred[table_name].add(fk.parent.name)

    dependencies: dict[str, set[str]] = {}
    dependents: dict[str, set[str]] = defaultdict(set)
    for name, table in tables.items():
        dependencies[name] = {
            fk.column.table.name
            for fk in table.foreign_keys
            if fk.column.table.name in tables and fk.parent.name not in deferred[name]
        }
        dependencies[name].discard(name)
        for dependency in dependencies[name]:
            dependents[dependency].add(name)

    queue = deque(sorted(name for name, deps in dependencies.items() if not deps))
    order: list[str] = []
    while queue:
        name = queue.popleft()
        order.append(name)
        for dependent in sorted(dependents[name]):
            dependencies[dependent].discard(name)
            if not dependencies[dependent]:
                queue.append(dependent)
    if len(order) != len(tables):
        unresolved = sorted(set(tables) - set(order))
        raise RuntimeError(f"Could not determine FK insertion order: {unresolved}")
    return order, deferred


def _coerce_value(value: Any, column) -> Any:
    if value is None:
        return None
    if isinstance(column.type, Boolean):
        return bool(value)
    if isinstance(column.type, DateTime):
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if column.type.timezone and isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
    return value


def _source_tables(engine: Engine, names: set[str]) -> dict[str, Table]:
    metadata = MetaData()
    metadata.reflect(bind=engine, only=sorted(names))
    return {name: metadata.tables[name] for name in names}


def _reset_postgres_sequences(connection: Connection, tables: dict[str, Table]) -> None:
    for table in tables.values():
        for column in table.primary_key.columns:
            if not isinstance(column.type, sa.Integer):
                continue
            sequence_name = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": table.name, "column_name": column.name},
            ).scalar_one_or_none()
            if not sequence_name:
                continue
            maximum = connection.execute(select(func.max(column))).scalar_one()
            connection.execute(
                text("SELECT setval(CAST(:sequence_name AS regclass), :value, :is_called)"),
                {
                    "sequence_name": sequence_name,
                    "value": maximum if maximum is not None else 1,
                    "is_called": maximum is not None,
                },
            )


def migrate(sqlite_url: str, postgres_url: str, *, dry_run: bool = False) -> None:
    _validate_backends(sqlite_url, postgres_url)
    source_engine = create_engine(sqlite_url)
    destination_engine = create_engine(postgres_url, pool_pre_ping=True)
    destination_tables = _model_tables()
    table_names = set(destination_tables)

    _validate_schema(source_engine, table_names, "SQLite source")
    _validate_schema(destination_engine, table_names, "PostgreSQL destination")
    source_tables = _source_tables(source_engine, table_names)

    with source_engine.connect() as source, destination_engine.connect() as destination:
        source_counts = _counts(source, source_tables)
        destination_counts = _counts(destination, destination_tables)
    _print_counts("SQLite source row counts:", source_counts)
    _print_counts("PostgreSQL destination row counts before migration:", destination_counts)
    nonempty = {name: count for name, count in destination_counts.items() if count}
    if nonempty:
        raise RuntimeError(f"Destination is not empty; refusing to migrate: {nonempty}")

    order, deferred_columns = _insertion_plan(destination_tables)
    print("Insertion order: " + " -> ".join(order))
    if dry_run:
        print("Dry run successful; no destination rows were written.")
        return

    deferred_updates: list[tuple[Table, dict[str, Any], dict[str, Any]]] = []
    with source_engine.connect() as source, destination_engine.begin() as destination:
        for table_name in order:
            source_table = source_tables[table_name]
            destination_table = destination_tables[table_name]
            rows = [dict(row) for row in source.execute(select(source_table)).mappings()]
            converted_rows: list[dict[str, Any]] = []
            for source_row in rows:
                converted = {
                    column.name: _coerce_value(source_row[column.name], column)
                    for column in destination_table.columns
                }
                deferred_values = {
                    name: converted[name]
                    for name in deferred_columns[table_name]
                    if converted[name] is not None
                }
                if deferred_values:
                    primary_key = {
                        column.name: converted[column.name]
                        for column in destination_table.primary_key.columns
                    }
                    deferred_updates.append((destination_table, primary_key, deferred_values))
                    for name in deferred_values:
                        converted[name] = None
                converted_rows.append(converted)
            if converted_rows:
                destination.execute(destination_table.insert(), converted_rows)

        for table, primary_key, values in deferred_updates:
            predicate = sa.and_(*(table.c[name] == value for name, value in primary_key.items()))
            destination.execute(table.update().where(predicate).values(**values))

        _reset_postgres_sequences(destination, destination_tables)
        destination_counts = _counts(destination, destination_tables)
        mismatches = {
            name: (source_counts[name], destination_counts[name])
            for name in sorted(table_names)
            if source_counts[name] != destination_counts[name]
        }
        if mismatches:
            raise RuntimeError(f"Row-count validation failed; transaction will roll back: {mismatches}")

    with destination_engine.connect() as destination:
        final_counts = _counts(destination, destination_tables)
    _print_counts("PostgreSQL destination row counts after migration:", final_counts)
    print("Migration successful: every table count matches the SQLite source.")


def main() -> None:
    args = _arguments()
    migrate(args.sqlite_url, args.postgres_url, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
