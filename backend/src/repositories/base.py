import json
from typing import Any, Optional

from src.database import get_db_connection


class BaseRepository:
    @staticmethod
    def period_interval_clause(period: str, column: str = "created_at") -> str:
        intervals = {
            "today": "1 day",
            "week": "7 days",
            "month": "30 days",
        }
        interval = intervals.get(period, "7 days")
        return f"AND {column} >= NOW() - INTERVAL '{interval}'"

    def _insert_and_return(self, table: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f"%({key})s" for key in data.keys())
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, data)
                row = cur.fetchone()
                return dict(row) if row else None

    def _get_by_id(self, table: str, row_id: str) -> Optional[dict[str, Any]]:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {table} WHERE id = %s", (row_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def _delete_by_id(self, table: str, row_id: str) -> bool:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {table} WHERE id = %s", (row_id,))
                return cur.rowcount > 0

    def _list(
        self,
        table: str,
        conditions: list[str],
        params: list[Any],
        order_by: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        sql = f"SELECT * FROM {table} WHERE {where_clause} ORDER BY {order_by} LIMIT %s OFFSET %s"
        query_params = [*params, limit, offset]
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, query_params)
                return [dict(row) for row in cur.fetchall()]

    def _update_and_return(
        self,
        table: str,
        row_id: str,
        updates: dict[str, Any],
        extra_set_sql: str = "",
    ) -> Optional[dict[str, Any]]:
        if not updates and not extra_set_sql:
            return self._get_by_id(table, row_id)
        set_parts = [f"{key} = %({key})s" for key in updates.keys()]
        if extra_set_sql:
            set_parts.append(extra_set_sql)
        set_clause = ", ".join(set_parts)
        sql = f"UPDATE {table} SET {set_clause} WHERE id = %(id)s RETURNING *"
        params = {**updates, "id": row_id}
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return dict(row) if row else None

    @staticmethod
    def parse_json_fields(payload: dict[str, Any], fields: list[str]) -> None:
        for field in fields:
            value = payload.get(field)
            if isinstance(value, str):
                try:
                    payload[field] = json.loads(value)
                except json.JSONDecodeError:
                    continue
