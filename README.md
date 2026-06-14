# Awaas AI — AI-Powered Smart Home Mood & Safety Platform

An intelligent system that understands how you feel and keeps your home safe. HomeLens detects mood and cognitive load through speech, behavioral patterns, and device usage history — then automatically adjusts your environment and monitors vulnerable family members.

---

## Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Services](#services)
- [Data Flow](#data-flow)
- [API Endpoints](#api-endpoints)
- [Getting Started](#getting-started)
- [Deployment](#deployment)
- [Team](#team)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React Dashboard)                               │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     API GATEWAY (port 8000)                                       │
│               Path-based routing / Load balancer                                  │
├──────────┬───────────┬──────────────┬────────────┬──────────────┬───────────────┤
│ /mood/*  │/behavior/*│ /patterns/*  │ /safety/*  │  /devices/*  │/orchestrate/* │
└────┬─────┴─────┬─────┴──────┬───────┴─────┬──────┴──────┬───────┴──────┬────────┘
     │           │            │             │             │              │
     ▼           ▼            ▼             ▼             ▼              ▼
┌────────┐ ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌───────────────┐
│  Mood  │ │Behavior │ │ Pattern  │ │  Safety   │ │ Device  │ │ Orchestrator  │
│Service │ │ Service │ │ Service  │ │ Service   │ │ Service │ │ (The Brain)   │
│ :8001  │ │ :8002   │ │ :8003    │ │ :8006     │ │ :8004   │ │ :8005         │
│        │ │         │ │          │ │           │ │         │ │               │
│Whisper │ │Scroll/  │ │Time/Seq/ │ │Elderly    │ │Mood →   │ │Collects all   │
│+ LLM   │ │Tap/Idle │ │Duration  │ │Monitoring │ │Light/   │ │signals → LLM  │
│Mood    │ │Cognitive│ │Patterns  │ │Vulnerable │ │Music/   │ │reasoning →    │
│Detect  │ │Load     │ │Anomalies │ │Safety     │ │Notif    │ │device actions │
└────────┘ └─────────┘ └──────────┘ └───────────┘ └─────────┘ └───────────────┘
```

---

## Features

### 1. Voice-Based Mood Detection
Records audio via Alexa/microphone → Groq Whisper STT → NVIDIA Nemotron 3 Super 120B analyzes text for emotional state. Detects 9 mood states: calm, happy, stressed, anxious, frustrated, sad, energetic, tired, neutral.

### 2. Behavioral Cognitive Load Detection
Monitors real-time interaction patterns from connected devices — scrolling speed, tap frequency, idle duration, swipe patterns → outputs cognitive load level (low/moderate/high/overloaded) and agitation score.

### 3. Device Usage Pattern Recognition
Learns household routines deterministically (no ML): time-based patterns, sequence-based departure routines, device duration norms. Detects anomalies like devices left on or exceeded runtime.

### 4. Adaptive Safety Intelligence
Monitors elderly and vulnerable family members living alone. Learns their daily routines, tracks activity, and produces a real-time safety assessment (safe/inactive/needs_attention/emergency). Alerts family contacts when something is wrong.

### 5. LLM-Powered Orchestration
The orchestrator collects all signals (mood + behavior + patterns + safety), feeds them to NVIDIA Nemotron 3 Super 120B for holistic reasoning, and decides environment adjustments. Handles contradictions intelligently.

### 6. Smart Environment Control
Maps mood + cognitive load → device adjustments: light color/brightness/temperature, music genre/volume, notification mode (normal/reduced/DND). 9 mood presets with cognitive load overrides.

### 7. Alexa Voice Responses with TTS
Every LLM response is read aloud via browser speech synthesis, simulating Alexa speaking naturally. Mutable, replayable, with expandable reasoning.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Primary LLM | NVIDIA Nemotron 3 Super 120B (AWS Bedrock) |
| Fallback LLM | Groq LLaMA 3.3 70B Versatile |
| Speech-to-Text | Groq Whisper Large V3 Turbo |
| Backend | FastAPI (Python 3.13) — 6 microservices + gateway |
| Database | Amazon DynamoDB (on-demand) |
| Frontend | React 19 + Vite 8 + Tailwind CSS 4 |
| Auth | Amazon Cognito (JWT) |
| Infra | Docker Compose (local) / EC2 + ALB + API Gateway (prod) |
| Communication | HTTP (inter-service), WebSocket (real-time) |
| Monitoring | Amazon CloudWatch |

---

## Project Structure

```
├── backend/
│   ├── gateway/main.py                 # API Gateway — routes to all services
│   ├── config.py                       # Shared settings (LLM provider toggle)
│   ├── services/
│   │   ├── mood/                       # Port 8001 — Mood analysis
│   │   │   ├── main.py
│   │   │   ├── bedrock_client.py       # Dual-provider: Bedrock + Groq
│   │   │   └── models.py
│   │   ├── behavior/                   # Port 8002 — Behavior analysis
│   │   │   ├── main.py
│   │   │   ├── engine.py              # Signal processing algorithm
│   │   │   └── models.py
│   │   ├── patterns/                   # Port 8003 — Pattern recognition
│   │   │   ├── main.py
│   │   │   ├── engine/                # Deterministic extractors
│   │   │   ├── context_builder.py
│   │   │   ├── dynamo.py
│   │   │   └── models.py
│   │   ├── devices/                    # Port 8004 — Device control
│   │   │   ├── main.py
│   │   │   └── controller.py
│   │   └── orchestrator/              # Port 8005 — The Brain
│   │       ├── main.py
│   │       ├── action_engine.py       # Dual-provider LLM reasoning
│   │       └── mood_history.py        # DynamoDB mood timeline
│   ├── patterns/                       # Standalone pattern engine (ECS)
│   │   ├── app/main.py
│   │   ├── logic/narrator.py          # LLM-powered Alexa narration
│   │   └── ...
│   ├── safety/                         # Port 8006 — Adaptive Safety
│   │   ├── app/main.py
│   │   ├── models/safety.py           # Vulnerability, SafetyAssessment
│   │   ├── routes/safety.py           # Safety dashboard API
│   │   └── ...
│   └── docker-compose.yml
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx          # Real-time mood monitoring + TTS
│       │   ├── Patterns.jsx           # Interactive floor plan + anomalies
│       │   ├── MoodHistory.jsx        # DynamoDB-backed timeline
│       │   └── DeviceControl.jsx
│       ├── components/
│       │   ├── VoiceInput.jsx         # Mic recording → base64 → backend
│       │   ├── BehaviorTracker.jsx    # DOM event monitoring
│       │   └── patterns/
│       │       ├── AlexaNotification.jsx  # TTS popup with stacked notifications
│       │       └── HouseFloor.jsx         # Interactive device floor plan
│       └── patternsApi.js
└── docker-compose.yml                  # Full stack (9 containers)
```

---

## Services

| Service | Port | Purpose |
|---------|------|---------|
| API Gateway | 8000 | Routes requests to microservices |
| Mood Analysis | 8001 | Speech/text → mood classification via LLM |
| Behavior Analysis | 8002 | Interaction signals → cognitive load (algorithmic) |
| Pattern Recognition | 8003 | Device events → learned routines + anomaly detection |
| Device Control | 8004 | Mood → environment presets (lights, music, notifications) |
| Orchestrator | 8005 | Collects all signals → LLM reasoning → action decisions |
| Safety Intelligence | 8006 | Elderly monitoring → vulnerability-aware safety assessment |
| DynamoDB Local | 8100 | Local database for development |
| Frontend | 5173 | React dashboard |

---

## Data Flow

```
User speaks / interacts with devices
         │                        │                    │
         ▼                        ▼                    ▼
   Mood Service              Behavior Service    Pattern Service
   (Whisper + Nemotron)      (Algorithm)         (Deterministic)
   mood: "stressed"          load: "overloaded"  anomaly: "fan left on"
   confidence: 85%           agitation: 93%      
         │                        │                    │
         └──────────────┬─────────┘                    │
                        │         ┌────────────────────┘
                        ▼         ▼
              ┌──────────────────────────┐
              │      ORCHESTRATOR        │      Safety Service
              │   (Nemotron 3 Super)     │ ←── (vulnerability context)
              │                          │
              │  Holistic reasoning:     │
              │  mood + behavior +       │
              │  patterns + safety       │
              │                          │
              │  Decides:                │
              │  • Dim blue lights       │
              │  • Ambient music         │
              │  • Turn off fan          │
              │  • DND mode              │
              │  • Alert family if       │
              │    elderly inactive      │
              └────────────┬─────────────┘
                           │
                           ▼
              Smart Home Devices + Notifications
```

---

## API Endpoints

All endpoints accessed via the gateway at `http://localhost:8000`:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/mood/analyze/audio` | Analyze audio for mood |
| POST | `/mood/analyze/text` | Analyze text for mood |
| POST | `/behavior/analyze` | Process behavior signals |
| POST | `/patterns/events` | Ingest device event |
| GET | `/patterns/context/{id}` | Get AI-ready context object |
| POST | `/patterns/patterns/{id}/extract` | Run pattern extraction |
| GET | `/safety/{household_id}` | Full safety dashboard payload |
| POST | `/safety/{household_id}/profiles` | Configure vulnerable person profiles |
| POST | `/devices/adjust` | Compute environment settings |
| POST | `/orchestrate/process` | Full pipeline (all signals → LLM → actions) |
| GET | `/orchestrate/history/{user_id}` | Mood history timeline |
| GET | `/services/health` | Health check all services |

---

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for frontend dev)
- AWS credentials (for Bedrock access)
- Groq API key (free tier — backup LLM + Whisper STT)

### Run All Services (Docker)

```bash
docker-compose up --build
```

Open `http://localhost:5173` for the dashboard.

### Run Individually (Development)

```bash
# Backend services
cd backend

# Terminal 1: Gateway
uvicorn gateway.main:app --reload --port 8000

# Terminal 2: Mood Service
uvicorn services.mood.main:app --reload --port 8001

# Terminal 3: Behavior Service
uvicorn services.behavior.main:app --reload --port 8002

# Terminal 4: Pattern Service (needs DynamoDB Local)
docker run -p 8100:8000 amazon/dynamodb-local
uvicorn patterns.app.main:app --reload --port 8003

# Terminal 5: Device Service
uvicorn services.devices.main:app --reload --port 8004

# Terminal 6: Orchestrator
uvicorn services.orchestrator.main:app --reload --port 8005

# Terminal 7: Safety Service
uvicorn safety.app.main:app --reload --port 8006

# Terminal 8: Frontend
cd ../frontend && npm run dev
```

### Environment Variables

Create `backend/.env`:
```env
LLM_PROVIDER=bedrock
BEDROCK_MODEL_ID=nvidia.nemotron-super-3-120b
GROQ_API_KEY=<your-groq-key>
GROQ_LLM_MODEL=llama-3.3-70b-versatile
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>
DYNAMODB_ENDPOINT_URL=http://localhost:8100
```

---

## Deployment

Production target: AWS

| Component | Service |
|-----------|---------|
| Auth | Amazon Cognito |
| API Entry | Amazon API Gateway |
| Load Balancing | Application Load Balancer |
| Compute | EC2 Auto Scaling Groups (5 instances) |
| Database | Amazon DynamoDB (on-demand) |
| AI Inference | AWS Bedrock (Nemotron 3 Super 120B) |
| Frontend | S3 + CloudFront |
| Secrets | AWS Secrets Manager |
| Monitoring | Amazon CloudWatch |

Each microservice runs on its own EC2 instance behind the ALB with path-based routing. The orchestrator calls other services via internal ALB DNS.

---

## Team

Built by **Team NoWins** for HackOn 2026
