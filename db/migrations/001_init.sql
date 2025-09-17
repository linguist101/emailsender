-- Use on Render Postgres
CREATE TABLE IF NOT EXISTS contacts (
  id BIGSERIAL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  first_name TEXT,
  last_name TEXT,
  company TEXT,
  tags TEXT,
  source TEXT,
  lawful_basis TEXT,
  consent_ts TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS suppression (
  email TEXT PRIMARY KEY,
  reason TEXT,
  ts TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS unsubscribes (
  email TEXT PRIMARY KEY,
  ts TIMESTAMPTZ DEFAULT NOW(),
  campaign_id BIGINT
);

CREATE TABLE IF NOT EXISTS templates (
  id BIGSERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  subject TEXT NOT NULL,
  body_markdown TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS campaigns (
  id BIGSERIAL PRIMARY KEY,
  name TEXT,
  template_id BIGINT NOT NULL REFERENCES templates(id) ON DELETE RESTRICT,
  status TEXT CHECK(status IN ('draft','running','paused','done')) DEFAULT 'draft',
  daily_send_cap INTEGER DEFAULT 300,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inboxes (
  id BIGSERIAL PRIMARY KEY,
  name TEXT,
  smtp_host TEXT,
  smtp_port INTEGER,
  username TEXT,
  password TEXT,
  from_name TEXT,
  from_email TEXT,
  daily_cap INTEGER DEFAULT 30,
  monthly_cap INTEGER DEFAULT 1000,
  pace_seconds INTEGER DEFAULT 90,
  health_score REAL DEFAULT 1.0,
  disabled BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS send_queue (
  id BIGSERIAL PRIMARY KEY,
  campaign_id BIGINT REFERENCES campaigns(id) ON DELETE SET NULL,
  contact_id BIGINT REFERENCES contacts(id) ON DELETE SET NULL,
  inbox_id BIGINT REFERENCES inboxes(id) ON DELETE SET NULL,
  subject TEXT,
  body_html TEXT,
  scheduled_at TIMESTAMPTZ,
  attempts INTEGER DEFAULT 0,
  status TEXT CHECK(status IN ('queued','sending','sent','failed','skipped')) DEFAULT 'queued'
);

CREATE TABLE IF NOT EXISTS events (
  id BIGSERIAL PRIMARY KEY,
  campaign_id BIGINT,
  contact_id BIGINT,
  inbox_id BIGINT,
  type TEXT,  -- sent, bounce, complaint, unsubscribe, reply, error
  meta JSONB,
  ts TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS heartbeats (
  service_name TEXT PRIMARY KEY,
  ts TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_queue_status_sched ON send_queue(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_unsubs_email ON unsubscribes(email);
CREATE INDEX IF NOT EXISTS idx_suppression_email ON suppression(email);
