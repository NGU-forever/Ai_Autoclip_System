"""
backend/scripts/init_new_tables.py
----------------------------
Creates missing tables for the system.
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

    -- ============================================================
    -- B2B Leads Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS b2b_leads (
        id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        company_name        TEXT            NOT NULL,
        website_url         TEXT            NOT NULL UNIQUE,
        decision_maker_name TEXT,
        verified_email      TEXT,
        whatsapp_number     TEXT,
        company_context     TEXT,
        icebreaker_text     TEXT,
        lead_status         TEXT            NOT NULL DEFAULT 'Scouted',
        is_approved         BOOLEAN         NOT NULL DEFAULT FALSE,
        last_contact_date   TIMESTAMPTZ,
        daily_send_count    INTEGER         NOT NULL DEFAULT 0,
        blacklisted         BOOLEAN         NOT NULL DEFAULT FALSE,
        created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_b2b_leads_lead_status  ON b2b_leads (lead_status);
    CREATE INDEX IF NOT EXISTS idx_b2b_leads_is_approved  ON b2b_leads (is_approved);
    CREATE INDEX IF NOT EXISTS idx_b2b_leads_blacklisted  ON b2b_leads (blacklisted);
    CREATE INDEX IF NOT EXISTS idx_b2b_leads_created_at   ON b2b_leads (created_at DESC);

    -- ============================================================
    -- Tasks Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS tasks (
        id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        title               TEXT            NOT NULL,
        description         TEXT,
        status              TEXT            NOT NULL DEFAULT 'pending',
        priority            TEXT            NOT NULL DEFAULT 'medium',
        assignee_id         TEXT,
        assignee_name       TEXT,
        workflow_id         TEXT,
        workflow_name       TEXT,
        scheduled_at        TIMESTAMPTZ,
        completed_at        TIMESTAMPTZ,
        tags                TEXT[]          DEFAULT '{}',
        comments            INTEGER         NOT NULL DEFAULT 0,
        created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_status    ON tasks (status);
    CREATE INDEX IF NOT EXISTS idx_tasks_priority  ON tasks (priority);
    CREATE INDEX IF NOT EXISTS idx_tasks_assignee  ON tasks (assignee_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_created   ON tasks (created_at DESC);

    -- ============================================================
    -- Messages Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS messages (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        type            TEXT            NOT NULL DEFAULT 'info',
        title           TEXT            NOT NULL,
        content         TEXT            NOT NULL,
        link            TEXT,
        read            BOOLEAN         NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_messages_type    ON messages (type);
    CREATE INDEX IF NOT EXISTS idx_messages_read    ON messages (read);
    CREATE INDEX IF NOT EXISTS idx_messages_created ON messages (created_at DESC);

    -- ============================================================
    -- Workflows Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS workflows (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        name            TEXT            NOT NULL,
        description     TEXT,
        status          TEXT            NOT NULL DEFAULT 'draft',
        workflow_type   TEXT            NOT NULL DEFAULT 'n8n',
        storyline_config JSONB          NOT NULL DEFAULT '{}'::jsonb,
        last_storyline_session_id TEXT,
        node_count      INTEGER         NOT NULL DEFAULT 0,
        run_count       INTEGER         NOT NULL DEFAULT 0,
        success_count   INTEGER         NOT NULL DEFAULT 0,
        failed_count    INTEGER         NOT NULL DEFAULT 0,
        last_run        TIMESTAMPTZ,
        last_success_at TIMESTAMPTZ,
        last_failed_at  TIMESTAMPTZ,
        n8n_workflow_id TEXT,
        webhook_url     TEXT,
        nodes           JSONB           NOT NULL DEFAULT '[]',
        edges           JSONB           NOT NULL DEFAULT '[]',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_workflows_status  ON workflows (status);
    CREATE INDEX IF NOT EXISTS idx_workflows_created ON workflows (created_at DESC);

    -- Ensure new columns exist even if workflows table was created earlier
    ALTER TABLE workflows ADD COLUMN IF NOT EXISTS workflow_type TEXT NOT NULL DEFAULT 'n8n';
    ALTER TABLE workflows ADD COLUMN IF NOT EXISTS storyline_config JSONB NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE workflows ADD COLUMN IF NOT EXISTS last_storyline_session_id TEXT;
    ALTER TABLE workflows ADD COLUMN IF NOT EXISTS success_count INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE workflows ADD COLUMN IF NOT EXISTS failed_count INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE workflows ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ;
    ALTER TABLE workflows ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMPTZ;
    ALTER TABLE workflows ADD COLUMN IF NOT EXISTS n8n_workflow_id TEXT;
    ALTER TABLE workflows ADD COLUMN IF NOT EXISTS webhook_url TEXT;
    CREATE INDEX IF NOT EXISTS idx_workflows_type    ON workflows (workflow_type);
    CREATE INDEX IF NOT EXISTS idx_workflows_n8n_id  ON workflows (n8n_workflow_id);

    -- ============================================================
    -- Skills Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS skills (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        name            TEXT            NOT NULL,
        description     TEXT,
        -- 给 LLM 使用的详细说明书，支持从前端/DB 动态配置
        instructions    TEXT,
        category        TEXT            NOT NULL,
        icon            TEXT,
        agent_id        TEXT,
        -- 额外结构化参数（前端传入的 JSON 配置）
        parameters      JSONB           NOT NULL DEFAULT '{}'::jsonb,
        enabled         BOOLEAN         NOT NULL DEFAULT TRUE,
        usage_count     INTEGER         NOT NULL DEFAULT 0,
        last_used       TIMESTAMPTZ,
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_skills_category  ON skills (category);
    CREATE INDEX IF NOT EXISTS idx_skills_enabled   ON skills (enabled);

    -- ============================================================
    -- Reports Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS reports (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        name            TEXT            NOT NULL,
        period          TEXT            NOT NULL,
        start_date      DATE,
        end_date        DATE,
        agent_stats     JSONB,
        workflow_stats  JSONB,
        cost_stats      JSONB,
        daily_data      JSONB,
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_reports_period   ON reports (period);
    CREATE INDEX IF NOT EXISTS idx_reports_created   ON reports (created_at DESC);

    -- ============================================================
    -- Integrations Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS integrations (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        platform        TEXT            NOT NULL UNIQUE,
        enabled         BOOLEAN         NOT NULL DEFAULT FALSE,
        config          JSONB           NOT NULL DEFAULT '{}',
        status          TEXT            NOT NULL DEFAULT 'disconnected',
        last_sync       TIMESTAMPTZ,
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_integrations_platform ON integrations (platform);
    CREATE INDEX IF NOT EXISTS idx_integrations_status  ON integrations (status);

    -- ============================================================
    -- Webhooks Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS webhooks (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        name            TEXT            NOT NULL,
        url             TEXT            NOT NULL,
        events          TEXT[]          NOT NULL DEFAULT '{}',
        auth_type       TEXT            NOT NULL DEFAULT 'none',
        auth_token      TEXT,
        status          TEXT            NOT NULL DEFAULT 'active',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_webhooks_status    ON webhooks (status);
    CREATE INDEX IF NOT EXISTS idx_webhooks_created   ON webhooks (created_at DESC);

    -- ============================================================
    -- Agents Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS agents (
        id VARCHAR(50) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        custom_name VARCHAR(100),
        role VARCHAR(100),
        status VARCHAR(20) DEFAULT 'online',
        load INTEGER DEFAULT 0,
        tokens_per_second INTEGER DEFAULT 0,
        waveform JSONB DEFAULT '[]'::jsonb,
        skills JSONB DEFAULT '[]'::jsonb,
        process JSONB DEFAULT '[]'::jsonb,
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    ALTER TABLE agents ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

    -- ============================================================
    -- Materials Table (For video/audio assets)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS materials (
        id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        name            TEXT            NOT NULL,
        type            TEXT            NOT NULL,
        file_path       TEXT            NOT NULL,
        size            BIGINT          NOT NULL,
        owner_id        UUID            NOT NULL REFERENCES users(id),
        status          TEXT            NOT NULL DEFAULT 'active',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_materials_owner    ON materials (owner_id);
    CREATE INDEX IF NOT EXISTS idx_materials_type     ON materials (type);
    CREATE INDEX IF NOT EXISTS idx_materials_status   ON materials (status);

    -- ============================================================
    -- Knowledge Documents Table
    -- ============================================================
    CREATE TABLE IF NOT EXISTS knowledge_documents (
        id VARCHAR(50) PRIMARY KEY,
        name VARCHAR(200) NOT NULL,
        type VARCHAR(20) DEFAULT 'txt',
        size INTEGER DEFAULT 0,
        status VARCHAR(20) DEFAULT 'active',
        tags JSONB DEFAULT '[]'::jsonb,
        content TEXT,
        owner_id TEXT,
        storage_path TEXT,
        agent_ids JSONB DEFAULT '[]'::jsonb,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_knowledge_documents_status ON knowledge_documents (status);
    CREATE INDEX IF NOT EXISTS idx_knowledge_documents_type ON knowledge_documents (type);
    CREATE INDEX IF NOT EXISTS idx_knowledge_documents_created_at ON knowledge_documents (created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_knowledge_documents_owner_id ON knowledge_documents (owner_id);
    CREATE INDEX IF NOT EXISTS idx_knowledge_documents_tags_gin ON knowledge_documents USING GIN (tags);
    CREATE INDEX IF NOT EXISTS idx_knowledge_documents_agent_ids_gin ON knowledge_documents USING GIN (agent_ids);

    -- ============================================================
    -- AI Call Logs Table (Observability)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS ai_call_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        provider TEXT NOT NULL,
        model TEXT,
        success BOOLEAN NOT NULL DEFAULT TRUE,
        error_message TEXT,
        latency_ms INTEGER NOT NULL DEFAULT 0,
        prompt_chars INTEGER NOT NULL DEFAULT 0,
        response_chars INTEGER NOT NULL DEFAULT 0,
        input_tokens INTEGER,
        output_tokens INTEGER,
        total_tokens INTEGER,
        source TEXT,
        request_id TEXT,
        meta JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_ai_call_logs_created_at ON ai_call_logs (created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_ai_call_logs_provider ON ai_call_logs (provider);
    CREATE INDEX IF NOT EXISTS idx_ai_call_logs_success ON ai_call_logs (success);
    CREATE INDEX IF NOT EXISTS idx_ai_call_logs_source ON ai_call_logs (source);

    -- ========================================
    -- Seed Integrations (LLM Providers)
    -- ========================================
    INSERT INTO integrations (platform, enabled, config, status)
    VALUES 
        ('openai', FALSE, '{"model": "gpt-4o", "api_key": "", "base_url": ""}'::jsonb, 'disconnected'),
        ('anthropic', FALSE, '{"model": "claude-3-5-sonnet-20241022", "api_key": "", "base_url": ""}'::jsonb, 'disconnected')
    ON CONFLICT (platform) DO NOTHING;
    """
    
    try:
        conn = psycopg2.connect(settings.database_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
            print("Successfully created all missing tables.")
    except Exception as e:
        print(f"Error during table creation: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    init_tables()
