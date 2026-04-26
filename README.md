# Pyrexia

**AI-powered clinical triage and intelligent queue management for outpatient clinics.**

Pyrexia is a full-stack medical triage system that replaces paper-based intake with an AI-driven kiosk. Patients interact with a conversational assistant that conducts a structured symptom interview, assigns a clinically validated urgency score based on the Manchester Triage System, and feeds a real-time priority queue visible to attending physicians. The system generates pre-visit clinical briefs so doctors can review patient context in under 30 seconds before entering the exam room.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Key Features](#key-features)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Database Schema](#database-schema)
- [How It Works](#how-it-works)
- [Internationalization](#internationalization)
- [Contributing](#contributing)
- [License](#license)

---

## Architecture Overview

Pyrexia follows a decoupled frontend/backend architecture with real-time communication through Supabase Realtime channels.

```
Patient Kiosk (Next.js)          Doctor Dashboard (Next.js)
       |                                  |
       | REST + SSE                       | REST + Supabase Realtime
       v                                  v
  ┌──────────────────────────────────────────┐
  |            FastAPI Backend               |
  |  ┌──────────┐  ┌──────────┐  ┌────────┐ |
  |  |  Triage   |  |  Queue   |  | Brief  | |
  |  |  Routes   |  |  Routes  |  | Routes | |
  |  └────┬─────┘  └────┬─────┘  └───┬────┘ |
  |       |              |             |      |
  |  ┌────v──────────────v─────────────v────┐ |
  |  |         Service Layer                | |
  |  |  Gemini AI  |  Queue  |  Supabase    | |
  |  └──────┬──────┴────┬────┴──────┬───────┘ |
  └─────────|───────────|───────────|─────────┘
            v           v           v
     Google Gemini    Redis      Supabase
        API        (Sorted Set)  (Postgres)
```

---

## Key Features

### Patient-Facing Kiosk

- **Conversational triage interview** -- an AI assistant asks focused, empathetic questions one at a time to assess symptoms, severity, onset, and relevant medical history.
- **Hard-rule emergency detection** -- critical keywords (chest pain, seizure, anaphylaxis, etc.) are matched before any AI call, short-circuiting triage and triggering an immediate emergency response.
- **Voice distress analysis** -- an optional vocal distress score (0.0--1.0) factors into urgency scoring. Scores above 0.85 automatically escalate the patient to HIGH priority.
- **Multilingual support** -- the kiosk interface and AI responses are available in English, Hindi, Kannada, Tamil, and Telugu.
- **Urgency scoring** -- patients receive a score from 0--100 mapped to five urgency levels: CRITICAL, HIGH, MODERATE, LOW, and NON_URGENT.

### Doctor-Facing Dashboard (PriorIQ)

- **Live priority queue** -- patients are displayed in real-time, ordered by urgency score, wait time, and voice distress indicators using AI-assisted re-ranking.
- **Pre-visit clinical briefs** -- AI-generated summaries include a brief narrative, priority flags, relevant history context, suggested opening questions, and a "watch for" note.
- **PDF export** -- clinical briefs can be exported as formatted PDF documents.
- **Critical alert banners** -- emergency patients trigger real-time alert banners on the dashboard via Supabase broadcast channels.
- **Call-in workflow** -- doctors can call patients in directly from the queue, removing them from the list and updating all connected clients in real time.

### Backend Intelligence

- **Multi-agent triage pipeline** -- the system routes conversations through specialized agents (triage orchestrator, diagnostic specialist, verification agent) with mid-stream handoffs.
- **Redis-backed conversation history** -- session state is stored in Redis with a 2-hour TTL and falls back to in-memory storage if Redis is unavailable.
- **AI-powered queue re-ranking** -- when the queue is retrieved, patients are re-ordered by a Gemini model that evaluates urgency, wait time fairness, and distress signals.
- **Background task orchestration** -- scoring, brief generation, patient enqueuing, and real-time broadcasting happen asynchronously and non-blocking after triage completion.
- **Graceful degradation** -- every external dependency (Gemini API, Redis, Supabase) has a fallback path. The system remains functional even when individual services are down.

---

## Technology Stack

| Layer          | Technology                                              |
| -------------- | ------------------------------------------------------- |
| Frontend       | Next.js 15, React 19, TypeScript, Tailwind CSS 4        |
| Backend        | Python 3.11+, FastAPI, Pydantic v2, Uvicorn             |
| AI             | Google Gemini (via OpenAI-compatible endpoint)           |
| Database       | Supabase (PostgreSQL)                                   |
| Cache / Queue  | Redis (sorted sets for priority queue, lists for history)|
| Real-time      | Supabase Realtime (broadcast channels)                  |
| Streaming      | Server-Sent Events (SSE) via sse-starlette              |
| PDF Generation | ReportLab                                               |
| i18n           | next-intl                                               |

---

## Project Structure

```
pyrexiaa/
├── backend/
│   ├── main.py                  # FastAPI application entry point
│   ├── requirements.txt         # Python dependencies
│   ├── supabase_schema.sql      # Database schema and seed data
│   ├── .env.example             # Environment variable template
│   ├── models/
│   │   ├── patient.py           # Patient data models
│   │   ├── triage.py            # Triage session and scoring models
│   │   └── queue.py             # Queue entry and response models
│   ├── routes/
│   │   ├── triage.py            # Session start, message streaming, scoring
│   │   ├── brief.py             # Clinical brief retrieval and PDF export
│   │   ├── queue.py             # Queue retrieval, call-in, reorder
│   │   ├── patients.py          # Patient CRUD operations
│   │   └── voice.py             # Voice input processing with distress scoring
│   ├── services/
│   │   ├── claude_service.py    # Gemini AI integration (streaming, briefs, re-ranking)
│   │   ├── supabase_service.py  # Database operations
│   │   ├── queue_service.py     # Redis sorted-set queue management
│   │   ├── realtime_service.py  # Supabase Realtime broadcasting
│   │   ├── background_tasks.py  # Async post-scoring orchestration
│   │   └── pdf_service.py       # PDF clinical brief generation
│   └── utils/
│       ├── hard_rules.py        # Emergency keyword detection
│       └── i18n.py              # Language detection utilities
├── frontend/
│   ├── package.json
│   ├── app/
│   │   ├── layout.tsx           # Root layout with font loading
│   │   ├── globals.css          # Global styles and design system
│   │   ├── kiosk/               # Patient-facing triage kiosk
│   │   │   ├── page.tsx         # Kiosk page (stage-based flow)
│   │   │   ├── hooks.ts         # Triage chat hook (SSE, state management)
│   │   │   ├── types.ts         # TypeScript type definitions
│   │   │   └── components/
│   │   │       ├── RegistrationForm.tsx
│   │   │       ├── ChatPanel.tsx
│   │   │       ├── VoiceMicButton.tsx
│   │   │       ├── ScoringOverlay.tsx
│   │   │       ├── DoctorCard.tsx
│   │   │       ├── EmergencyAlert.tsx
│   │   │       └── LanguagePicker.tsx
│   │   └── dashboard/           # Doctor-facing PriorIQ dashboard
│   │       ├── page.tsx         # Live queue and clinical brief viewer
│   │       ├── supabase.ts      # Supabase client configuration
│   │       └── types.ts         # Dashboard type definitions
│   ├── components/
│   │   └── DoctorAssignmentCard.tsx
│   ├── messages/                # i18n translation files
│   │   ├── en.json
│   │   ├── hi.json
│   │   ├── kn.json
│   │   ├── ta.json
│   │   └── te.json
│   └── i18n/
│       └── request.ts           # Locale resolution
└── amd/                         # Architecture and design decision records
    ├── 001-agentic-triage-architecture.md
    └── 002-background-services-design.md
```

---

## Prerequisites

- **Python** 3.11 or later
- **Node.js** 18 or later
- **Redis** instance (local or hosted)
- **Supabase** project with the schema applied
- **Google Gemini API** key

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/shashank03-dev/pyrexiaa.git
cd pyrexiaa
```

### 2. Set up the database

Run the schema file against your Supabase project's SQL editor or via the CLI:

```bash
# Apply the schema to your Supabase PostgreSQL instance
psql $DATABASE_URL < backend/supabase_schema.sql
```

### 3. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Edit .env with your credentials
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive documentation is served at `http://localhost:8000/docs`.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The application will be available at `http://localhost:3000`.

| Route           | Description                    |
| --------------- | ------------------------------ |
| `/kiosk`        | Patient check-in kiosk         |
| `/dashboard`    | Doctor queue and brief viewer  |

---

## Environment Variables

Create a `.env` file in the `backend/` directory using `.env.example` as a template.

| Variable                | Required | Description                                          |
| ----------------------- | -------- | ---------------------------------------------------- |
| `GEMINI_API_KEY`        | Yes      | Google Gemini API key                                |
| `GEMINI_MODEL`          | No       | Model identifier (default: `gemini-2.0-flash`)       |
| `GEMINI_SCORING_API_KEY`| No       | Separate key for scoring calls (defaults to primary)  |
| `GEMINI_SCORING_MODEL`  | No       | Model for scoring/briefs (defaults to primary model)  |
| `SUPABASE_URL`          | Yes      | Supabase project URL                                 |
| `SUPABASE_SERVICE_KEY`  | Yes      | Supabase service role key                            |
| `REDIS_URL`             | Yes      | Redis connection string (e.g. `redis://localhost:6379/0`) |
| `CORS_ORIGINS`          | No       | Comma-separated allowed origins (default: `*`)       |

---

## API Reference

### Triage

| Method | Endpoint            | Description                                         |
| ------ | ------------------- | --------------------------------------------------- |
| POST   | `/triage/start`     | Begin a new triage session; returns initial question |
| POST   | `/triage/message`   | Continue conversation; streams response via SSE      |
| POST   | `/triage/score`     | Request final urgency scoring for a session          |

### Queue

| Method | Endpoint                          | Description                              |
| ------ | --------------------------------- | ---------------------------------------- |
| GET    | `/queue/current`                  | Retrieve the current clinic queue         |
| POST   | `/queue/call/{patient_id}`        | Call a patient in (remove from queue)     |
| PUT    | `/queue/reorder/{patient_id}`     | Manually override a patient's urgency     |

### Briefs

| Method | Endpoint                    | Description                              |
| ------ | --------------------------- | ---------------------------------------- |
| GET    | `/brief/{patient_id}`       | Retrieve clinical brief for a patient     |
| GET    | `/brief/{patient_id}/pdf`   | Download brief as a formatted PDF         |

### Voice

| Method | Endpoint           | Description                                         |
| ------ | ------------------ | --------------------------------------------------- |
| POST   | `/voice/process`   | Process transcribed voice input with distress scoring |

### Health

| Method | Endpoint   | Description         |
| ------ | ---------- | ------------------- |
| GET    | `/health`  | Service health check |
| GET    | `/`        | Service metadata     |

---

## Database Schema

The system uses six tables in Supabase (PostgreSQL):

- **patients** -- core patient records (name, age, gender, language, voice distress score).
- **triage_sessions** -- conversation state including history (JSONB), urgency scores, red flags, and session status.
- **briefs** -- AI-generated pre-visit clinical briefs linked to a patient and session.
- **doctors** -- doctor registry with specialty, availability, room number, and photo.
- **queue_assignments** -- persistent queue assignments mapping patients to doctors with position tracking.
- **audit_log** -- event-sourced audit trail for all significant system actions.
- **demo_cache** -- cached AI responses for offline demonstration and API fallback scenarios.

---

## How It Works

### Patient Flow

1. **Registration** -- the patient enters their name, age, gender, and preferred language at the kiosk.
2. **Triage Interview** -- the AI assistant conducts a focused 3--5 question interview, assessing symptom severity, onset, and associated conditions. Critical keywords are intercepted before the AI is called.
3. **Urgency Scoring** -- once sufficient data is collected, the system produces a structured urgency assessment with a 0--100 score, urgency level, reasoning trace, red flags, and a recommended doctor specialty.
4. **Queue Placement** -- the patient is placed into a Redis sorted-set queue, ordered by urgency and wait time. The queue update is broadcast to all connected dashboard clients.
5. **Doctor Assignment** -- the patient sees their assigned doctor, estimated wait time, and room number on the kiosk screen.

### Emergency Path

If a critical keyword is detected at any point during the conversation (e.g., "chest pain", "seizure", "anaphylaxis"), the system bypasses the AI entirely:

- Urgency score is set to 100 (CRITICAL).
- The patient is placed at position 1 in the queue via emergency override.
- A real-time emergency alert is broadcast to all connected dashboards.
- The kiosk displays an emergency confirmation screen.

### Doctor Flow

1. **Queue Monitoring** -- the PriorIQ dashboard displays the live queue with real-time updates via Supabase broadcast channels.
2. **Brief Review** -- selecting a patient loads their AI-generated clinical brief with priority flags, suggested questions, and immediate watch-for notes.
3. **Call-In** -- the doctor calls the patient in, removing them from the queue and notifying all connected clients.

---

## Internationalization

The kiosk interface supports five languages through `next-intl`:

| Code | Language |
| ---- | -------- |
| `en` | English  |
| `hi` | Hindi    |
| `kn` | Kannada  |
| `ta` | Tamil    |
| `te` | Telugu   |

The AI assistant responds in the patient's selected language throughout the triage conversation.

---

## Contributing

1. Fork the repository.
2. Create a feature branch from `main`.
3. Make your changes and ensure they follow the existing code style.
4. Submit a pull request with a clear description of the changes.

---

## License

This project is proprietary. All rights reserved.
