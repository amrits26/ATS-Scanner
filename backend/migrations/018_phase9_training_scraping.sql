-- Migration 018: Phase 9 – Agent Training Pipeline + Multi-Source Job Scraping
-- New tables: agent_feedback_log, agent_outcome_feedback, scraped_jobs, job_scraping_runs

-- -------------------------------------------------------------------------
-- agent_feedback_log: RLHF interaction log (accepts, edits, rejections)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_feedback_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type      VARCHAR(50) NOT NULL,
    user_id         UUID        REFERENCES users(id) ON DELETE SET NULL,
    job_id          UUID        REFERENCES jobs(id)  ON DELETE SET NULL,

    input_context   JSONB       NOT NULL,
    agent_output    JSONB       NOT NULL,
    user_action     VARCHAR(20) NOT NULL,  -- accepted, edited, rejected, applied
    user_edited_output JSONB,
    edit_distance   FLOAT,
    rating          INTEGER     CHECK (rating >= 1 AND rating <= 5),

    is_synthetic    BOOLEAN     NOT NULL DEFAULT FALSE,
    use_count       INTEGER     NOT NULL DEFAULT 0,
    last_used_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_afl_agent_type       ON agent_feedback_log(agent_type);
CREATE INDEX IF NOT EXISTS idx_afl_user_id          ON agent_feedback_log(user_id);
CREATE INDEX IF NOT EXISTS idx_afl_job_id           ON agent_feedback_log(job_id);
CREATE INDEX IF NOT EXISTS idx_afl_type_rating      ON agent_feedback_log(agent_type, rating DESC);
CREATE INDEX IF NOT EXISTS idx_afl_user_action      ON agent_feedback_log(user_action);

-- -------------------------------------------------------------------------
-- agent_outcome_feedback: long-term outcome tracking (hired, rejected, etc.)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_outcome_feedback (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_type      VARCHAR(50) NOT NULL,
    session_id      VARCHAR(100) NOT NULL,
    final_outcome   VARCHAR(20) NOT NULL,  -- hired, interview, rejected, abandoned

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_aof_user_id    ON agent_outcome_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_aof_session_id ON agent_outcome_feedback(session_id);

-- -------------------------------------------------------------------------
-- scraped_jobs: multi-source job scraping cache
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scraped_jobs (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source           VARCHAR(50) NOT NULL,
    external_id      VARCHAR(200) NOT NULL,
    url              TEXT,

    title            VARCHAR(500) NOT NULL,
    company          VARCHAR(200) NOT NULL,
    location         VARCHAR(200),
    description      TEXT,
    description_html TEXT,

    salary_min       INTEGER,
    salary_max       INTEGER,
    salary_currency  VARCHAR(10),
    salary_period    VARCHAR(20),

    job_type         VARCHAR(50),
    experience_level VARCHAR(50),
    remote_status    VARCHAR(50),

    posted_date      TIMESTAMPTZ,
    scraped_date     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_date     TIMESTAMPTZ,

    company_logo_url TEXT,
    company_website  TEXT,

    required_skills  JSONB,
    raw_data         JSONB,

    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    last_verified    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sj_source_external ON scraped_jobs(source, external_id);
CREATE INDEX IF NOT EXISTS idx_sj_title_location         ON scraped_jobs(title, location);
CREATE INDEX IF NOT EXISTS idx_sj_posted_active           ON scraped_jobs(posted_date, is_active);
CREATE INDEX IF NOT EXISTS idx_sj_company                 ON scraped_jobs(company);
CREATE INDEX IF NOT EXISTS idx_sj_scraped_date            ON scraped_jobs(scraped_date);
CREATE INDEX IF NOT EXISTS idx_sj_is_active               ON scraped_jobs(is_active);

-- -------------------------------------------------------------------------
-- job_scraping_runs: audit trail for each scraping session
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_scraping_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(50) NOT NULL,
    search_query    JSONB       NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    jobs_found      INTEGER     NOT NULL DEFAULT 0,
    jobs_new        INTEGER     NOT NULL DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_by      UUID        REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_jsr_status     ON job_scraping_runs(status);
CREATE INDEX IF NOT EXISTS idx_jsr_started_at ON job_scraping_runs(started_at);
