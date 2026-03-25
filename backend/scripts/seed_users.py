"""
backend/scripts/seed_users.py
----------------------------
Seed initial users with RBAC-friendly accounts.

Notes:
- Roles align with current backend schema: admin / user / viewer.
- Passwords can be overridden via environment variables.
- Default passwords are stronger than legacy demo credentials and should be
  changed immediately after first login.
- Password is only written on first creation; reruns will not overwrite
  existing user passwords.
"""
import os
import sys

# Allow importing from the backend src package
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BASE_DIR)

from src.auth.utils import get_password_hash
from src.database import get_db_connection


def _get_password(env_key: str, fallback: str) -> str:
    value = os.getenv(env_key, "").strip()
    return value if value else fallback


def seed_users():
    # You can override any password via:
    # SEED_SUPER_ADMIN_PASSWORD / SEED_ADMIN_PASSWORD / SEED_USER_PASSWORD / SEED_VIEWER_PASSWORD
    users = [
        {
            "name": "Super Administrator",
            "email": "root@agentos.io",
            "password": _get_password("SEED_SUPER_ADMIN_PASSWORD", "ChangeMe!Root@2026"),
            "role": "admin",
            "status": "active",
        },
        {
            "name": "System Administrator",
            "email": "admin@agentos.io",
            "password": _get_password("SEED_ADMIN_PASSWORD", "ChangeMe!Admin@2026"),
            "role": "admin",
            "status": "active",
        },
        {
            "name": "Operations User",
            "email": "user@agentos.io",
            "password": _get_password("SEED_USER_PASSWORD", "ChangeMe!User@2026"),
            "role": "user",
            "status": "active",
        },
        {
            "name": "ReadOnly Auditor",
            "email": "viewer@agentos.io",
            "password": _get_password("SEED_VIEWER_PASSWORD", "ChangeMe!Viewer@2026"),
            "role": "viewer",
            "status": "active",
        },
    ]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for user in users:
                cur.execute("SELECT id FROM users WHERE email = %s", (user["email"],))
                password_hash = get_password_hash(user["password"])
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        "UPDATE users SET name = %s, role = %s, status = %s WHERE email = %s",
                        (user["name"], user["role"], user["status"], user["email"]),
                    )
                    print(f"User {user['email']} updated successfully (password preserved).")
                    continue

                cur.execute(
                    "INSERT INTO users (name, email, password_hash, role, status) VALUES (%s, %s, %s, %s, %s)",
                    (user["name"], user["email"], password_hash, user["role"], user["status"]),
                )
                print(f"User {user['email']} created successfully.")
        conn.commit()

    print("\nSeeded account plan:")
    print("- root@agentos.io      (admin)")
    print("- admin@agentos.io     (admin)")
    print("- user@agentos.io      (user)")
    print("- viewer@agentos.io    (viewer)")
    print("Tip: set SEED_*_PASSWORD env vars to customize credentials.")
    print("Password policy: written only when user is first created.")

if __name__ == "__main__":
    try:
        seed_users()
        print("Seeding completed.")
    except Exception as e:
        print(f"Error during seeding: {e}")
        sys.exit(1)
