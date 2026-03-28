"""
backend/scripts/init_tables.py
----------------------------
初始化核心数据库表（简化版）
"""
import os
import sys
from dotenv import load_dotenv

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.append(BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, "..", ".env"))

import psycopg2
from src.config import settings


def init_tables():
    sql = """
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";

    -- ============================================================
    -- Users Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS users (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        name            TEXT            NOT NULL,
        email           TEXT            NOT NULL UNIQUE,
        avatar          TEXT,
        password_hash   TEXT            NOT NULL,
        role            TEXT            NOT NULL DEFAULT 'user',
        status          TEXT            NOT NULL DEFAULT 'active',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        last_login      TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_users_email     ON users (email);
    CREATE INDEX IF NOT EXISTS idx_users_role      ON users (role);
    CREATE INDEX IF NOT EXISTS idx_users_status    ON users (status);
    """
    
    try:
        conn = psycopg2.connect(settings.database_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
            print("Core tables initialized successfully.")
    except Exception as e:
        print(f"Error during table creation: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()


if __name__ == "__main__":
    init_tables()
