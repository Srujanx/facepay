-- FacePay — Database Schema
-- Supabase (PostgreSQL + pgvector). Run this file in the Supabase SQL Editor.
-- Generated from docs/SCHEMA.md

-- =============================================================================
-- Extension
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- Tables
-- =============================================================================

-- One row per registered passenger. id references auth.users.
CREATE TABLE profiles (
  id                   UUID        PRIMARY KEY REFERENCES auth.users ON DELETE CASCADE,
  full_name            TEXT        NOT NULL,
  stripe_customer_id   TEXT,
  fare_category        TEXT        NOT NULL DEFAULT 'adult'
                                   CHECK (fare_category IN (
                                     'adult','senior','youth','child','u_pass','tap','armed_forces'
                                   )),
  pass_expires_at      DATE,       -- null unless fare_category is u_pass or tap
  institution          TEXT        CHECK (institution IN (
                                     'durham_college','ontario_tech','trent_durham', NULL
                                   )),
  payment_failed_at    TIMESTAMPTZ, -- set when Stripe rejects. null = good standing
  pin_hash             TEXT,        -- SHA-256 hash of (secret + 4-digit PIN) for pin-confirm flow
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Add pin_hash if running on an existing database that had profiles without it
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS pin_hash TEXT;

-- Zero-knowledge table. No images. Only 128-dimensional float vectors.
CREATE TABLE face_embeddings (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID        NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  embedding    VECTOR(128) NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- IVFFlat cosine similarity index
CREATE INDEX idx_face_embeddings_ivfflat
  ON face_embeddings
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- GTFS-inspired fare table. Seeded with DRT 2025 PRESTO prices.
CREATE TABLE fare_rules (
  fare_category   TEXT         PRIMARY KEY
                               CHECK (fare_category IN (
                                 'adult','senior','youth','child','u_pass','tap','armed_forces'
                               )),
  amount_cents    INT          NOT NULL DEFAULT 0 CHECK (amount_cents >= 0),
  label           TEXT         NOT NULL,
  requires_card   BOOLEAN      NOT NULL DEFAULT true,
  requires_pass   BOOLEAN      NOT NULL DEFAULT false,
  updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Every boarding attempt logged — including free ones and $0 fares.
CREATE TABLE transactions (
  id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 UUID        NOT NULL REFERENCES profiles(id),
  amount_cents            INT         NOT NULL DEFAULT 0,
  confidence              FLOAT       NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  stripe_pi_id            TEXT,       -- null if $0 fare or payment failed
  status                  TEXT        NOT NULL
                                      CHECK (status IN ('success','pin_required','payment_failed')),
  resolved_fare_category  TEXT        NOT NULL,
  pass_was_expired        BOOLEAN     NOT NULL DEFAULT false,
  route_id                TEXT,       -- DRT route number e.g. '110'
  trip_id                 TEXT,       -- GTFS trip_id for this specific journey
  stop_id                 TEXT,       -- GTFS stop_id for this terminal's location
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rejected boarding attempts. Kept separate from transactions.
CREATE TABLE failed_scans (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID        REFERENCES profiles(id), -- null if not identified
  confidence   FLOAT       CHECK (confidence >= 0 AND confidence <= 1),
  reason       TEXT        NOT NULL
                           CHECK (reason IN (
                             'liveness_failed','no_face_detected','low_confidence','pin_exceeded'
                           )),
  route_id     TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Additional indexes
-- =============================================================================
CREATE INDEX idx_profiles_stripe_customer ON profiles (stripe_customer_id);
CREATE INDEX idx_profiles_fare_category   ON profiles (fare_category);
CREATE INDEX idx_face_embeddings_user     ON face_embeddings (user_id);
CREATE INDEX idx_transactions_user        ON transactions (user_id);
CREATE INDEX idx_transactions_route       ON transactions (route_id);
CREATE INDEX idx_transactions_created     ON transactions (created_at);

-- Partial index for TAP monthly counter — only indexes TAP success rows
CREATE INDEX idx_transactions_tap_counter
  ON transactions (user_id, created_at)
  WHERE resolved_fare_category = 'tap' AND status = 'success';

-- =============================================================================
-- Seed data: fare_rules (DRT 2025 PRESTO rates)
-- =============================================================================
INSERT INTO fare_rules (fare_category, amount_cents, label, requires_card, requires_pass) VALUES
  ('adult', 373, 'Adult PRESTO', true, false),
  ('senior', 246, 'Senior PRESTO (65+)', true, false),
  ('youth', 335, 'Youth PRESTO (13-19)', true, false),
  ('child', 0, 'Child (12 and under) — Free', false, false),
  ('u_pass', 0, 'U-Pass — Semester Free', false, true),
  ('tap', 5222, 'TAP Monthly Pass', true, true),
  ('armed_forces', 0, 'Canadian Armed Forces — Free', false, false)
ON CONFLICT (fare_category) DO UPDATE SET
  amount_cents = EXCLUDED.amount_cents,
  label = EXCLUDED.label,
  requires_card = EXCLUDED.requires_card,
  requires_pass = EXCLUDED.requires_pass,
  updated_at = now();

-- =============================================================================
-- Functions
-- =============================================================================

-- Keeps profiles.updated_at accurate automatically.
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER profiles_updated_at
  BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Returns count of successful TAP trips in the current calendar month.
-- If result >= 14, charge $0 instead of $52.22.
CREATE OR REPLACE FUNCTION get_tap_trips_this_month(p_user_id UUID)
RETURNS INT AS $$
  SELECT COUNT(*)::INT
  FROM transactions
  WHERE user_id = p_user_id
    AND resolved_fare_category = 'tap'
    AND status = 'success'
    AND created_at >= date_trunc('month', now())
    AND created_at <  date_trunc('month', now()) + INTERVAL '1 month';
$$ LANGUAGE sql STABLE;

-- Implements all fare logic. Backend calls this after identification.
CREATE OR REPLACE FUNCTION resolve_fare(p_user_id UUID)
RETURNS TABLE (
  resolved_category  TEXT,
  amount_cents       INT,
  requires_card      BOOLEAN,
  pass_expired       BOOLEAN
) AS $$
DECLARE
  v_category       TEXT;
  v_expires_at     DATE;
  v_tap_trips      INT;
BEGIN
  SELECT fare_category, pass_expires_at
  INTO   v_category, v_expires_at
  FROM   profiles WHERE id = p_user_id;

  -- U-Pass: check if still valid
  IF v_category = 'u_pass' THEN
    IF v_expires_at IS NULL OR v_expires_at < CURRENT_DATE THEN
      RETURN QUERY SELECT 'adult'::TEXT, 373, true, true;
      RETURN;
    END IF;
  END IF;

  -- TAP: check monthly trip limit
  IF v_category = 'tap' THEN
    v_tap_trips := get_tap_trips_this_month(p_user_id);
    IF v_tap_trips >= 14 THEN
      RETURN QUERY SELECT 'tap'::TEXT, 0, false, false;
      RETURN;
    END IF;
  END IF;

  -- All other categories: direct fare_rules lookup
  RETURN QUERY
    SELECT v_category, fr.amount_cents, fr.requires_card, false
    FROM fare_rules fr
    WHERE fr.fare_category = v_category;
END;
$$ LANGUAGE plpgsql STABLE;

-- =============================================================================
-- Row Level Security
-- =============================================================================
ALTER TABLE profiles        ENABLE ROW LEVEL SECURITY;
ALTER TABLE face_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE fare_rules      ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE failed_scans    ENABLE ROW LEVEL SECURITY;

-- profiles: users can read and update their own row only
CREATE POLICY "Users read own profile"
  ON profiles FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users update own profile"
  ON profiles FOR UPDATE USING (auth.uid() = id);

-- face_embeddings: NO frontend access. Only backend (service_role) can read/write.
CREATE POLICY "No frontend access to embeddings"
  ON face_embeddings FOR ALL USING (false);

-- fare_rules: public read — frontend displays fares during registration
CREATE POLICY "Anyone can read fare rules"
  ON fare_rules FOR SELECT USING (true);

-- transactions: users can read their own history only
CREATE POLICY "Users read own transactions"
  ON transactions FOR SELECT USING (auth.uid() = user_id);

-- failed_scans: no frontend access
CREATE POLICY "No frontend access to failed scans"
  ON failed_scans FOR ALL USING (false);

-- =============================================================================
-- match_face (for POST /identify)
-- =============================================================================
-- Returns the closest face_embeddings row by cosine similarity.
-- Backend calls this via supabase.rpc('match_face', {'query_embedding': list[float]}).
CREATE OR REPLACE FUNCTION match_face(query_embedding vector(128))
RETURNS TABLE(user_id uuid, confidence float)
LANGUAGE sql STABLE
AS $$
  SELECT fe.user_id, (1 - (fe.embedding <=> query_embedding))::float AS confidence
  FROM face_embeddings fe
  ORDER BY fe.embedding <=> query_embedding
  LIMIT 1;
$$;

-- =============================================================================
-- Realtime
-- =============================================================================
-- Terminal subscribes to INSERT events on transactions for the success screen.
ALTER PUBLICATION supabase_realtime ADD TABLE transactions;
