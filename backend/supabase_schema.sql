-- Supabase Schema for Pyrexia

CREATE TABLE IF NOT EXISTS patients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    age INTEGER,
    gender TEXT,
    language TEXT,
    voice_distress_score NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS triage_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patients(id),
    clinic_id TEXT,
    chief_complaint TEXT,
    language TEXT DEFAULT 'en',
    conversation_history JSONB DEFAULT '[]',
    urgency_score INTEGER,
    urgency_level TEXT,
    reasoning_trace JSONB DEFAULT '[]',
    red_flags JSONB DEFAULT '[]',
    recommended_action TEXT,
    estimated_wait_minutes INTEGER,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    scored_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS briefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patients(id),
    session_id UUID REFERENCES triage_sessions(id),
    brief_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Fast lookups by patient and session
CREATE INDEX IF NOT EXISTS idx_briefs_patient_id ON briefs(patient_id);
CREATE INDEX IF NOT EXISTS idx_briefs_session_id ON briefs(session_id);

CREATE TABLE IF NOT EXISTS doctors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    specialty TEXT,
    photo_url TEXT,
    room_number TEXT,
    is_available BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS queue_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patients(id),
    doctor_id UUID REFERENCES doctors(id),
    position INTEGER,
    status TEXT DEFAULT 'waiting' -- waiting, in_consult, done
);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    patient_id UUID REFERENCES patients(id),
    payload_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Cached demo responses — Anthropic API fallback
CREATE TABLE IF NOT EXISTS demo_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario TEXT UNIQUE NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Seed default fallback scenario
INSERT INTO demo_cache (scenario, response_json)
VALUES ('aarav_sharma', '{
  "urgency_score": 72,
  "urgency_level": "HIGH",
  "reasoning_trace": [
    "Patient reports severe abdominal pain (8/10)",
    "Onset: 3 hours ago, sudden",
    "Associated nausea and fever (38.5°C)",
    "No prior history of similar episodes",
    "Voice distress analysis suggests significant discomfort"
  ],
  "recommended_action": "Prioritise for physician assessment within 15 minutes",
  "estimated_wait_minutes": 15,
  "red_flags": ["Acute abdomen", "Fever with pain"],
  "chief_complaint_refined": "Acute abdominal pain with fever and nausea"
}'::jsonb)
ON CONFLICT (scenario) DO NOTHING;
