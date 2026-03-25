"""
backend/scripts/init_system_tables.py
----------------------------
Creates missing system audit and alert tables.
"""
import os
import sys
from dotenv import load_dotenv

# Add backend to path so we can import app modules
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.append(BASE_DIR)

# Load .env from project root
load_dotenv(os.path.join(BASE_DIR, "..", ".env"))

import psycopg2
from src.config import settings

def init_tables():
    sql = """
    -- ============================================================
    -- Audit Logs Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS audit_logs (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        level           TEXT            NOT NULL DEFAULT 'info', -- 'info', 'warning', 'error', 'success'
        source          TEXT            NOT NULL,                -- 'agent', 'workflow', 'system', 'auth'
        message         TEXT            NOT NULL,
        details         JSONB           DEFAULT '{}',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_audit_logs_level      ON audit_logs (level);
    CREATE INDEX IF NOT EXISTS idx_audit_logs_source     ON audit_logs (source);
    CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at DESC);

    -- ============================================================
    -- Alert Rules Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS alert_rules (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        name            TEXT            NOT NULL,
        type            TEXT            NOT NULL,                -- 'usage', 'error', 'latency'
        threshold       INTEGER         NOT NULL,
        metric          TEXT            NOT NULL,                -- 'count', 'percentage', 'ms'
        enabled         BOOLEAN         NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );

    -- ============================================================
    -- Seed Data
    -- ============================================================
    
    -- Seed Audit Logs if empty
    INSERT INTO audit_logs (level, source, message)
    SELECT 'info', 'system', '系统初始化完成，所有服务已启动'
    WHERE NOT EXISTS (SELECT 1 FROM audit_logs LIMIT 1);

    INSERT INTO audit_logs (level, source, message)
    SELECT 'success', 'workflow', '工作流 "B2B 询盘处理" 成功运行完成'
    WHERE (SELECT COUNT(*) FROM audit_logs) < 2;

    -- Seed Alert Rules if empty
    INSERT INTO alert_rules (name, type, threshold, metric, enabled)
    VALUES 
        ('高错误率告警', 'error', 10, 'percentage', TRUE),
        ('工作流延迟告警', 'latency', 5000, 'ms', TRUE),
        ('每日配额耗尽告警', 'usage', 90, 'percentage', TRUE)
    ON CONFLICT DO NOTHING;
    """
    
    try:
        conn = psycopg2.connect(settings.database_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
            print("Successfully created system audit and alert tables.")
    except Exception as e:
        print(f"Error during system table creation: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    init_tables()
