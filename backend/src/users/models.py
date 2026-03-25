from typing import Any, List, Optional
from src.database import get_db_connection
from src.repositories.base import BaseRepository

TABLE_USERS = "users"
TABLE_USER_PREFERENCES = "user_preferences"

class UserRepository(BaseRepository):
    """Repository operations for users table."""

    def create_user(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._insert_and_return(TABLE_USERS, data)
        if result:
            result.pop('password_hash', None)
        return result

    def get_user_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        result = self._get_by_id(TABLE_USERS, user_id)
        if result:
            result.pop('password_hash', None)
        return result

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {TABLE_USERS} WHERE email = %s", (email,))
                row = cur.fetchone()
                if row:
                    result = dict(row)
                    result.pop('password_hash', None)
                    return result
                return None

    def get_user_by_email_internal(self, email: str) -> Optional[dict[str, Any]]:
        """Get a user by email including password_hash (internal use only)."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {TABLE_USERS} WHERE email = %s", (email,))
                row = cur.fetchone()
                return dict(row) if row else None

    def list_users(
        self,
        role: Optional[str] = None,
        status: Optional[str] = None,
        name_query: Optional[str] = None,
        email: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[dict[str, Any]], int]:
        conditions: list[str] = []
        params: List[Any] = []

        if role is not None:
            conditions.append("role = %s")
            params.append(role)
        if status is not None:
            conditions.append("status = %s")
            params.append(status)
        if name_query:
            conditions.append("name ILIKE %s")
            params.append(f"%{name_query}%")
        if email:
            conditions.append("LOWER(email) = LOWER(%s)")
            params.append(email)

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        sql = f"""
        SELECT * FROM {TABLE_USERS}
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """
        count_sql = f"SELECT COUNT(*)::int AS total FROM {TABLE_USERS} WHERE {where_clause}"

        query_params = [*params, limit, offset]
        count_params = [*params]
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, query_params)
                results = [dict(row) for row in cur.fetchall()]
                cur.execute(count_sql, count_params)
                total_row = cur.fetchone()
                total = int(total_row["total"]) if total_row else 0

        for result in results:
            result.pop('password_hash', None)
        return results, total

    def update_user(self, user_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_user_by_id(user_id)
        set_clause = ", ".join(f"{k} = %({k})s" for k in updates.keys())
        sql = f"UPDATE {TABLE_USERS} SET {set_clause} WHERE id = %(id)s RETURNING *"
        params = {**updates, "id": user_id}
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                if not row:
                    return None
                result = dict(row)
                result.pop('password_hash', None)
                return result

    def delete_user(self, user_id: str) -> bool:
        return self._delete_by_id(TABLE_USERS, user_id)

    def toggle_user_status(self, user_id: str) -> dict[str, Any]:
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        new_status = 'disabled' if user['status'] == 'active' else 'active'
        return self.update_user(user_id, {"status": new_status})

    def update_last_login(self, user_id: str) -> dict[str, Any]:
        from datetime import datetime
        return self.update_user(user_id, {"last_login": datetime.utcnow()})


class UserPreferencesRepository:
    """Repository for user_preferences table (user_id as PK)."""

    def get_preferences(self, user_id: str) -> Optional[dict[str, Any]]:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM {TABLE_USER_PREFERENCES} WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def upsert_preferences(
        self, user_id: str, theme: Optional[str] = None, preferences: Optional[dict] = None
    ) -> dict[str, Any]:
        from datetime import datetime

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                existing = self.get_preferences(user_id)
                if existing:
                    updates: list[str] = ["updated_at = %(updated_at)s"]
                    params: dict[str, Any] = {"user_id": user_id, "updated_at": datetime.utcnow()}
                    if theme is not None:
                        updates.append("theme = %(theme)s")
                        params["theme"] = theme
                    if preferences is not None:
                        updates.append("preferences = %(preferences)s")
                        params["preferences"] = preferences
                    set_clause = ", ".join(updates)
                    cur.execute(
                        f"UPDATE {TABLE_USER_PREFERENCES} SET {set_clause} WHERE user_id = %(user_id)s RETURNING *",
                        params,
                    )
                else:
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE_USER_PREFERENCES} (user_id, theme, preferences, updated_at)
                        VALUES (%(user_id)s, %(theme)s, %(preferences)s, %(updated_at)s)
                        RETURNING *
                        """,
                        {
                            "user_id": user_id,
                            "theme": theme or "light",
                            "preferences": preferences if preferences is not None else {},
                            "updated_at": datetime.utcnow(),
                        },
                    )
                row = cur.fetchone()
                return dict(row) if row else {}

    def delete_preferences(self, user_id: str) -> bool:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {TABLE_USER_PREFERENCES} WHERE user_id = %s",
                    (user_id,),
                )
                return cur.rowcount > 0
