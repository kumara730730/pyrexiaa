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

-- Seed default fallback scenario (legacy key — triage output only)
INSERT INTO demo_cache (scenario, response_json)
VALUES ('aarav_sharma', '{
  "urgency_score": 94,
  "urgency_level": "CRITICAL",
  "reasoning_trace": [
    "ACS pattern: chest pressure + left arm radiation",
    "Diaphoresis with sudden onset — high-risk presentation",
    "Symptom onset during sleep/early morning — peak cardiac event window",
    "Jaw radiation = triple-vessel pattern consistent with STEMI/NSTEMI",
    "Diabetic patient: atypical presentation risk — real urgency likely higher than reported",
    "15 pack-year smoking history compounds atherogenic risk"
  ],
  "presenting_complaint": "52M presenting with sudden-onset chest tightness, left arm heaviness, and jaw radiation since 07:00. Associated diaphoresis.",
  "red_flags": [
    "ACS pattern — chest + arm + jaw radiation",
    "Diaphoresis reported",
    "Sudden onset in early morning — peak STEMI window",
    "Diabetic with masked pain threshold"
  ],
  "suggested_doctor_questions": [
    "Is the chest discomfort constant or does it come and go?",
    "Rate your pain from 1 to 10 right now.",
    "Have you taken any aspirin or GTN before coming in?"
  ],
  "recommended_doctor_specialty": "Cardiology"
}'::jsonb)
ON CONFLICT (scenario) DO UPDATE SET response_json = EXCLUDED.response_json;

-- Full triage record: patient + triage_output + brief
INSERT INTO demo_cache (scenario, response_json)
VALUES ('aarav_sharma_triage', '{
  "patient": {
    "name": "Aarav Sharma",
    "age": 52,
    "gender": "M",
    "history_notes": "Type 2 Diabetes (metformin 500mg BD). Smoker — 15 pack-years. No prior cardiac events documented. Last clinic visit: 8 months ago for HbA1c monitoring."
  },
  "triage_output": {
    "urgency_score": 94,
    "urgency_level": "CRITICAL",
    "reasoning_trace": [
      "ACS pattern: chest pressure + left arm radiation",
      "Diaphoresis with sudden onset — high-risk presentation",
      "Symptom onset during sleep/early morning — peak cardiac event window",
      "Jaw radiation = triple-vessel pattern consistent with STEMI/NSTEMI",
      "Diabetic patient: atypical presentation risk — real urgency likely higher than reported",
      "15 pack-year smoking history compounds atherogenic risk"
    ],
    "presenting_complaint": "52M presenting with sudden-onset chest tightness, left arm heaviness, and jaw radiation since 07:00. Associated diaphoresis.",
    "red_flags": [
      "ACS pattern — chest + arm + jaw radiation",
      "Diaphoresis reported",
      "Sudden onset in early morning — peak STEMI window",
      "Diabetic with masked pain threshold"
    ],
    "suggested_doctor_questions": [
      "Is the chest discomfort constant or does it come and go?",
      "Rate your pain from 1 to 10 right now.",
      "Have you taken any aspirin or GTN before coming in?"
    ],
    "recommended_doctor_specialty": "Cardiology"
  },
  "brief": {
    "brief_summary": "52M diabetic smoker presenting with classical ACS-pattern symptoms: chest pressure, left arm heaviness, jaw radiation, and diaphoresis since 07:00. Atypical pain in diabetics — do not underestimate. Immediate assessment required.",
    "priority_flags": [
      "ACS pattern — chest + arm + jaw triple radiation",
      "Diabetic: masked pain threshold, atypical presentation risk",
      "Diaphoresis with sudden AM onset — peak STEMI window",
      "15 pack-year smoking: high baseline atherogenic risk"
    ],
    "context_from_history": "T2DM on metformin, active smoker (15 pack-years). No prior cardiac events. HbA1c 8 months ago — current glycaemic control unknown.",
    "suggested_opening_questions": [
      "Is the discomfort still ongoing, and has the character changed since arrival?",
      "Have you taken aspirin or GTN today?",
      "Any similar episodes in the past — even mild ones you dismissed?"
    ],
    "watch_for": "IMMEDIATE: ECG within 60 seconds. Do not defer for full history — STEMI door-to-balloon time is the priority."
  }
}'::jsonb)
ON CONFLICT (scenario) DO UPDATE SET response_json = EXCLUDED.response_json;
