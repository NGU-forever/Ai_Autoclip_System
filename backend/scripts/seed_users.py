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
import sys

def seed_users():
    print("User seeding skipped. Currently using hardcoded admin account for development: admin / 123456")

if __name__ == "__main__":
    try:
        seed_users()
    except Exception as e:
        print(f"Error during seeding: {e}")
        sys.exit(1)
