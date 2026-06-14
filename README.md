<div align="center">

# 🏠 Awaas AI

### A context-aware smart-home brain that understands how you **feel**, learns how you **live**, and protects who you **love**.

*Built for the Indian household — connected to Amazon Alexa, powered by AWS Bedrock, Amazon DynamoDB, and ambient intelligence.*

<br/>

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)
![DynamoDB](https://img.shields.io/badge/DynamoDB-NoSQL-4053D6?logo=amazondynamodb&logoColor=white)
![AWS Bedrock](https://img.shields.io/badge/AWS%20Bedrock-Nemotron-FF9900?logo=amazonaws&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLaMA%203.3-F55036)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

</div>

---

## 📑 Table of Contents

1. [🏠 Problem & Solution](#-problem--solution)
2. [⭐ Core Features](#-core-features)
3. [🌍 Real-World Scenarios](#-real-world-scenarios)
4. [⚙️ How It Works](#️-how-it-works)
5. [📊 Pattern Recognition Engine](#-pattern-recognition-engine)
6. [😄 Mood & Cognitive-Load Engine](#-mood--cognitive-load-engine)
7. [🛡️ Adaptive Safety Intelligence](#️-adaptive-safety-intelligence)
8. [🏛️ Architecture](#️-architecture)
9. [🧰 Tech Stack](#-tech-stack)
10. [🚀 Setup](#-setup)
11. [📚 Further Reading](#-further-reading)

---

## 🏠 Problem & Solution

### The Problem

A "smart home" today is just a collection of connected devices controlled through an app. It follows commands, but it doesn't truly understand what's happening inside the home.

It doesn't realize when:

* 😟 You come home after a stressful day and the bright white lights make the environment even more uncomfortable.
* 🔥 The gas stove has been running for 45 minutes when it normally runs for only 15.
* 👵 An elderly parent living alone may have missed their medication or needs assistance.
* 💡 Your son rushed out in the morning and accidentally left the fan running in an empty room all day.

The home is connected, but it isn't aware of the people it serves. Modern smart homes remain technology-centric instead of **customer-centric**, focusing on devices rather than the needs of the family.

In a country of **joint families**, elderly parents living independently, children coming from school to home alone, working couples, domestic help on schedules, a home that *cannot notice* is a home that *cannot care*.

### The Solution

**Awaas AI** turns a passive house into an **attentive companion** — an Alexa-native ambient intelligence experience built on the **customer obsession** principle, where every decision starts with understanding the people living in the home. It fuses three streams of understanding into one decision-making brain:

| It understands… | …by | …so it can |
|---|---|---|
| **How you feel** 😌 | analysing your voice & on-device behaviour | adapt lights, music & notifications to your mood |
| **How you live** 📊 | learning device routines deterministically over 30 days | notice when something is *off* — left on, missed, or running too long |
| **Who you love** 🛡️ | layering a vulnerability lens over every anomaly | escalate a small risk into an urgent alert when a vulnerable person is alone |

> **The core philosophy:** the system *discovers what is true* **deterministically** (statistically), and only uses an **LLM to phrase it** in natural, caring language through the **Alexa voice interface**. The AI never decides reality, it only narrates it — ensuring **trustworthiness** and **responsible AI** at every layer. This creates a highly customer-centric experience, ensuring that actions are driven by real household context rather than generic AI assumptions.

---

## ⭐ Core Features

<table>
<tr>
<td width="33%" valign="top">

### 😌 Mood-Based Adaptation
Detects emotion from **speech** (Whisper → LLM) and **behaviour** (scroll/tap/idle), then auto-adjusts **lights, music & notifications**.

`9 moods` · `4 cognitive-load levels`

</td>
<td width="33%" valign="top">

### 📊 Pattern Recognition
Learns daily routines from IoT events using pure **statistics** (time / sequence / duration). Flags **anomalies** with explainable confidence. Uses our end-to-end pattern-recognition implementaton engine which generates patterns from daily events logs and compares these patterns to current state of things in real time. This generates reliable contexts and hence anomalies can be flagged.

`no ML` · `fully auditable`

</td>
<td width="33%" valign="top">

### 🛡️ Adaptive Safety
A **vulnerability-aware overlay** that re-reads every concern by *who's home*. Produces a live **safety score** + emergency detection (SOS, health, inactivity).

`vulnerability_score ×2.0 if elderly` · `0–100 score`

</td>
</tr>
</table>

**Plus:**
- 🗣️ **Natural Alexa voice** — every alert is spoken in caring, human language (LLM-generated, never templated when online). Designed for **voice-first interaction** aligned with the Alexa Smart Home skill model.
- 🔌 **Dual-provider resilience** — AWS Bedrock primary → Groq fallback → deterministic fallback. *It never fails silently.* Built with **operational excellence** and **high availability** principles.
- 🇮🇳 **Indian-context first** — a customer-focused design philosophy tailored for Indian households including water motors, gas stoves, pooja routines, joint-family vulnerability, domestic-help schedules. Serving **Bharat's next billion users**.
- 🔒 **Privacy by design** — all inferencing happens within the customer's AWS account via Bedrock. No raw audio or personal data leaves to third parties. Aligned with **AWS Shared Responsibility** and **data sovereignty** principles.

---

## 🌍 Real-World Scenarios

> *Each scenario is a real, runnable demo in the app.*

#### 1. 😮‍💨 "I'm fine." *(but you're clearly having a rough day)*
You say you're okay, but your actions tell a different story. You're scrolling restlessly, tapping harder than usual, and moving around the house less. → Behaviour speaks louder than words. The lights soften, calming music fades in, and distractions are quietly reduced.

#### 2. 🔥 The forgotten gas stove
Dinner was finished long ago, but the stove is still burning. It's been on for over an hour, far longer than usual. → `Duration anomaly detected`. Since Grandma is home alone, the situation is treated as **critical**. *"The stove appears to have been left on. I'm turning it off and notifying the family."*

#### 3. 👵 Looking after elderly parents, even from afar
Mom usually starts her day around **7 AM**, opening the curtains, making tea, and moving through the house. Today, her routine is `noticeably different`. → Pattern deviation detected. A gentle check-in notification is sent to the family: *"Your mother's morning routine seems unusual today. Would you like to check in?"*
Not every alert is an emergency—sometimes it's simply peace of mind for families caring for loved ones from a distance.

#### 4. 🪟 An open window after midnight
The bedroom window is still open at 23:30 (night window 22:00–06:00). → `unsafe_at_night`. With an elderly resident alone, it's a **security concern** → *"I've closed and locked the window and notified the family."* This way Thefts & Robberies can be easily prevented further ensuring safety of the family.

#### 5. 💡 Rushed out, fan still running
The son's room fan is still ON, hours past its learned 9:00 AM OFF time. → `device_left_on`. A gentle suggestion appears on the Patterns dashboard.

#### 6. 🆘 A fall at 3 AM
The wearable fires an `SOS` event. → instant **Emergency** status, score crashes, emergency contacts alerted. No routine analysis needed — this jumps the queue.

---

## ⚙️ How It Works

At the highest level, **everything is one end-to-end flow**: raw signals come in, deterministic engines decide *what is true*, and an LLM decides *how to say it*. This ensures every recommendation remains transparent, explainable, and aligned with a customer-first smart living experience.

```mermaid
flowchart LR
    subgraph IN["📥 Signals"]
        V["🎙️ Voice"]
        B["👆 Behaviour"]
        E["🔌 Device events"]
        P["👥 People profiles"]
    end

    subgraph BRAIN["🧠 Deterministic Intelligence"]
        M["Mood Engine"]
        PE["Pattern Engine"]
        SO["Safety Overlay"]
    end

    L["🗣️ LLM Narrator<br/>(Bedrock → Groq)"]
    OUT["🏠 Actions + Alexa voice<br/>lights · music · alerts"]

    V --> M
    B --> M
    E --> PE
    P --> SO
    PE --> SO
    M --> L
    PE --> L
    SO --> L
    L --> OUT

    classDef in fill:#1e3a5f,stroke:#4a90d9,color:#fff;
    classDef brain fill:#1e4620,stroke:#3fb950,color:#fff;
    classDef out fill:#3d1e5c,stroke:#a371f7,color:#fff;
    class V,B,E,P in;
    class M,PE,SO brain;
    class L,OUT out;
```

**Next we explain our three strongest features: Pattern Recognition Engine, Mood & Cognitive Load Engine, and Adaptive Safety Intelligence**

---

## 📊 Pattern Recognition Engine

The engine learns routines from **30 days of device events**, entirely with statistics — **no machine learning, fully explainable**.

### Events → Patterns → Context

```mermaid
flowchart TB
    A["📥 <b>EVENTS</b><br/>device · action · time"]
    B["🗄️ <b>EVENT STORE</b><br/>30 days history"]
    C["🧠 <b>PATTERN ENGINE</b><br/>Time · Sequence · Duration"]
    D["📚 <b>LEARNED PATTERNS</b><br/>+ confidence"]
    E["🏠 <b>CURRENT STATE</b><br/>who's home · what's ON"]
    F["⚖️ <b>COMPARE</b><br/>patterns vs. now → anomalies"]
    G["📦 <b>CONTEXT OBJECT</b>"]
    H["🤖 <b>LLM NARRATOR</b>"]

    A --> B --> C --> D
    D --> F
    E --> F
    F --> G --> H

    classDef ev fill:#1e3a5f,stroke:#4a90d9,color:#fff,stroke-width:2px;
    classDef pat fill:#1e4620,stroke:#3fb950,color:#fff,stroke-width:2px;
    classDef ctx fill:#5c3d1e,stroke:#d99e4a,color:#fff,stroke-width:2px;
    classDef out fill:#3d1e5c,stroke:#a371f7,color:#fff,stroke-width:2px;
    class A,B ev;
    class C,D pat;
    class E,F ctx;
    class G,H out;
```

### The three extractors

| Extractor | Learns | Example |
|-----------|--------|---------|
| **Time-based** | clusters event time-of-day into 30-min buckets | *"living-room light turns ON around 19:00"* |
| **Sequence-based** | repeated ordered chains within a 10-min session | *"door OPEN → fan OFF → light OFF"* (departure) |
| **Duration-based** | pairs each ON with the next OFF | *"water motor runs ~15 min, starting ~09:00"* |

### Confidence — explainable by design

$$\text{confidence} = \underbrace{\min\left(1, \frac{\text{occurrences}}{\text{windowdays}}\right)}_{\text{support}} \times \underbrace{\left(1 - \frac{\text{stddev}}{2 \times \text{tolerance}}\right)}_{\text{consistency}}$$

A pattern is kept only if it occurs **≥ 3 times** *and* scores **≥ 0.6**. No randomness, fully reproducible.

### The five anomaly detectors

| Detector | Catches |
|----------|---------|
| `device_left_on` | a device still ON past its learned OFF time (+ 60-min grace) |
| `duration_exceeded` | running longer than `usual × 2.0` (e.g. motor 45 vs 15 min) |
| `device_active_too_long` | absolute 12-hour safety-net for devices with no duration pattern |
| `missed_routine` | a high-confidence ON routine whose window passed without happening |
| `unexpected_activity` | an entry/activity far outside the learned schedule |

📄 **Deep dive:** [`docs/ARCHITECTURE_DIAGRAMS.md`](docs/ARCHITECTURE_DIAGRAMS.md) · [`backend/patterns/README.md`](backend/patterns/README.md)

---

## 😄 Mood & Cognitive-Load Engine

This is the **feeling** half of Awaas AI. Two services work together — one reads
*what you say*, the other reads *how you behave* — and the orchestrator fuses
them (plus the household patterns above) into one LLM decision that adapts the room.

```mermaid
flowchart LR
    subgraph MO["😌 Mood Service · :8001"]
        direction TB
        AUD["🎙️ Audio"] --> STT["Whisper STT<br/>(Groq)"]
        STT --> MTX["Text"]
        TXT["⌨️ Typed text"] --> MTX
        MTX --> MLLM["LLM mood analysis<br/>(Bedrock → Groq)"]
        MLLM --> MOUT["mood · confidence<br/>cognitive_load · features"]
    end

    subgraph BE["👆 Behaviour Service · :8002"]
        direction TB
        SIG["scroll · tap<br/>idle · swipe"] --> SCORE["agitation scoring<br/>(deterministic)"]
        SCORE --> BOUT["cognitive_load<br/>agitation · patterns"]
    end

    ORCH["🧠 Orchestrator · :8005<br/>Action Engine LLM"]
    DEV["💡 Devices · :8004<br/>preset + overrides"]
    OUT["🏠 Lights · Music · Notifications<br/>+ Alexa voice"]

    MOUT --> ORCH
    BOUT --> ORCH
    ORCH --> DEV --> OUT

    classDef mood fill:#16301c,stroke:#3fb950,color:#fff;
    classDef beh fill:#16263d,stroke:#4a90d9,color:#fff;
    classDef orch fill:#2d1f3d,stroke:#a371f7,color:#fff;
    classDef out fill:#3d2c14,stroke:#e3b341,color:#fff;
    class AUD,STT,MTX,TXT,MLLM,MOUT mood;
    class SIG,SCORE,BOUT beh;
    class ORCH orch;
    class DEV,OUT out;
```

### 🎙️ Mood Service — *what you say*

Reads emotion from speech or text. Audio is transcribed by **Groq Whisper**
(`whisper-large-v3-turbo`), then the text is sent to the LLM (**Bedrock
Nemotron** primary → **Groq LLaMA** fallback) which returns a structured
judgement — never free-form prose:

```json
{ "mood": "stressed", "confidence": 0.85,
  "cognitive_load": "high",
  "speech_features": { "sentiment": "negative", "complexity": "simple", "urgency": "high" } }
```

**9 mood states** — each maps to a device preset:

| Mood | Light | Music | Notifications |
|------|-------|-------|---------------|
| Calm | lavender, 50% | classical | normal |
| Happy | bright white, 75% | upbeat | normal |
| Stressed | cool blue, 40% | ambient | reduced |
| Anxious | lavender, 35% | nature sounds | DND |
| Frustrated | teal, 45% | lo-fi | reduced |
| Sad | warm gold, 55% | uplifting | normal |
| Energetic | green, 80% | electronic | normal |
| Tired | deep orange, 30% | sleep | DND |
| Neutral | white, 65% | — | normal |

### 👆 Behaviour Service — *how you behave*

Reads **cognitive load** from on-device interaction signals — purely
deterministic scoring, no LLM. Each signal is scored 0–1 for agitation, then
mapped to a load level:

| Signal | Reads as |
|--------|----------|
| fast / aggressive **scroll** | frustration, searching |
| rapid **tap** | impatience, agitation |
| prolonged **idle** | fatigue, distraction *(lowers agitation)* |
| erratic **swipe** | overwhelm |

Agitation → **4 cognitive-load levels** that *override* the mood preset:

| Level | Effect on the room |
|-------|--------------------|
| Low | +5% brightness / +5% volume |
| Moderate | no change |
| High | −10% brightness, −10% volume, reduced notifications |
| Overloaded | −20% brightness, −15% volume, full DND |

### 🧠 The Orchestrator (the brain)

The orchestrator's `/process` pipeline calls each service over HTTP, then hands
**everything** to the **Action Engine LLM**:

```
mood + confidence + speech features      (Mood :8001)
  + cognitive load + agitation + patterns (Behaviour :8002)
  + household anomalies / who's home       (Patterns :8003)
  + room + time of day
        → Action Engine LLM (Bedrock → Groq → preset fallback)
        → { actions, alexa_response, reasoning, mood_assessment }
        → stored to SmartHome_MoodHistory
```

Key behaviours baked into the prompt:
- **Behaviour overrides speech** — if you *say* "I'm fine" but tap aggressively, it trusts the behaviour.
- **Tone matches state** — terse when you're stressed (*"On it."*), warm and longer when you're calm.
- **Graceful fallback** — if both LLMs are unreachable, the [Devices service](backend/services/devices/controller.py) computes the preset + cognitive override deterministically, so the room *always* responds.

Every change is persisted to the `SmartHome_MoodHistory` table (mood, load,
confidence, trigger source, what Alexa said) and rendered as a colour-coded
timeline on the dashboard.

---

## 🛡️ Adaptive Safety Intelligence

Safety is an **independent twin** of the pattern engine (its own service on `:8006`) that adds **one powerful new idea**: *who is home, and how vulnerable are they?*

```mermaid
flowchart TB
    F["⚖️ <b>ANOMALIES</b><br/>(pattern engine +<br/>night · inactivity · SOS)"]
    P["👥 <b>PEOPLE PROFILES</b><br/>elderly · child · pregnant<br/>unwell · normal"]
    S["🛡️ <b>SAFETY OVERLAY</b><br/>escalate severity by vulnerability<br/>→ score 0–100 + status"]
    H["🤖 <b>LLM NARRATOR</b><br/>caring, urgent voice"]

    F --> S
    P --> S
    S --> H

    classDef ctx fill:#5c3d1e,stroke:#d99e4a,color:#fff,stroke-width:2px;
    classDef saf fill:#5c1e2e,stroke:#f85149,color:#fff,stroke-width:2px;
    classDef out fill:#3d1e5c,stroke:#a371f7,color:#fff,stroke-width:2px;
    class F ctx;
    class P,S saf;
    class H out;
```

### Vulnerability weights

| Person | Weight | | Person | Weight |
|--------|:------:|---|--------|:------:|
| 🧑 Normal adult | ×1.0 | | 🤰 Pregnant | ×1.8 |
| 🧒 Child | ×1.7 | | 👵 Elderly | ×2.0 |
| 🤒 Unwell | ×1.8 | | 🧑‍🦱 Capable adult present | ×0.6 *(mitigates)* |

> The **same** open door is `low` severity with a fit adult home — but `critical` for an elderly person alone. Escalated rank = `round(base_rank × vulnerability_factor)`, clamped 0–4.

### Extra safety detectors

| Detector | Fires when |
|----------|-----------|
| 🌙 `unsafe_at_night` | door/window open during 22:00–06:00 |
| 😴 `global_inactivity` | no activity for 4 h (warn) / 8 h (emergency) while someone's home |
| ❤️ `health_alert` / 🆘 `sos` | wearable vital out of range, or panic button → instant **Emergency** |

### Safety score & status

Starts at **100**, deducts per escalated anomaly → `low −4` · `medium −12` · `high −28` · `critical −55`.

| 🟢 Safe | 🟡 Inactive | 🟠 Needs Attention | 🔴 Emergency |
|---------|-------------|--------------------|--------------|
| ≥ 60, no high/critical | only inactivity-type | < 60 or any high/critical | SOS / health / global-inactivity / < 25 |

📄 **Deep dive:** [`docs/ARCHITECTURE_DIAGRAMS.md`](docs/ARCHITECTURE_DIAGRAMS.md) · [`backend/safety/README.md`](backend/safety/README.md)

---

## 🏛️ Architecture

Awaas AI is an end-to-end **microservices** platform — 7 independently deployable FastAPI services communicating over HTTP, backed by **Amazon DynamoDB** for serverless persistence and dual LLM providers (**AWS Bedrock** + Groq) for generative AI reasoning. In production it deploys as an **EC2 Auto Scaling Group** behind an **Application Load Balancer** with **Amazon Cognito**-based auth and **Amazon API Gateway** rate limiting — following the **AWS Well-Architected Framework** for reliability, security, and cost efficiency. Locally, the identical services run inside Docker Compose with a FastAPI gateway replicating ALB path-routing — so the code you develop against is the exact code that ships. Both topologies are shown below.

### Production architecture (AWS)

Request flows left → right through six layers: **clients → auth → load balancer
→ compute → AI & data → outputs**.

```mermaid
flowchart LR
    %% ─── 1 · Clients ───
    subgraph C["1 · CLIENTS"]
        direction TB
        MOB["📱 Mobile App"]
        WEB["🌐 Web App"]
        ALX["🔊 Alexa /<br/>Voice Assistant"]
    end

    %% ─── 2 · Auth + Entry ───
    subgraph A["2 · AUTH + ENTRY"]
        direction TB
        COG["🔐 Amazon Cognito<br/>JWT auth · user pools"]
        APIGW["🚪 API Gateway<br/>JWT validation · rate limiting · routing"]
    end

    %% ─── 3 · Load Balancer ───
    subgraph LB["3 · LOAD BALANCER"]
        ALB["⚖️ Application Load Balancer<br/>path routing · health checks · auto scaling"]
    end

    %% ─── 4 · EC2 Auto Scaling Group ───
    subgraph EC2["4 · EC2 INSTANCES · Auto Scaling Group"]
        direction TB
        I1["🟢 Instance 1 · Mood Analysis<br/>Voice/Text → Whisper STT → LLM mood"]
        I2["🔵 Instance 2 · Behavior Analysis<br/>Scroll · Tap · Idle · Swipe → cognitive load"]
        I3["🟠 Instance 3 · Device Pattern Engine<br/>learns routines · detects anomalies"]
        I4["🔴 Instance 4 · Safety Intelligence<br/>vulnerable monitoring · scoring · alerts"]
        I5["🟣 Instance 5 · Orchestrator<br/>collects signals → LLM reasoning → actions"]
        CACHE[("⚡ DynamoDB Cache<br/>native TTL · per instance")]
    end

    %% ─── 5 · AI & Data ───
    subgraph AID["5 · AI & DATA"]
        direction TB
        BR["🧠 NVIDIA Nemotron 3 Super 120B<br/>primary · via AWS Bedrock"]
        GQ["🧠 Groq LLaMA 3.3 70B<br/>fallback"]
        DDB[("🗄️ Amazon DynamoDB<br/>Events · Patterns · State<br/>Mood History · Safety Profiles")]
        S3[("🪣 Amazon S3<br/>logs · voice files")]
    end

    %% ─── 6 · Outputs ───
    subgraph OUT["6 · OUTPUTS"]
        direction TB
        O1["💡 Adjust Ambience<br/>lights · music · temperature"]
        O2["🔔 Notifications<br/>Alexa voice · mobile push"]
        O3["🏠 Device Control<br/>on / off / schedule"]
        O4["🚨 Emergency Alerts<br/>family / caregivers"]
    end

    %% ─── Flow ───
    MOB --> COG
    WEB --> COG
    ALX --> COG
    COG --> APIGW --> ALB
    ALB --> I1 & I2 & I3 & I4 & I5
    I1 --> CACHE
    I2 --> CACHE
    I3 --> CACHE
    I4 --> CACHE
    I1 -. signals .-> I5
    I2 -. signals .-> I5
    I3 -. signals .-> I5
    I4 -. signals .-> I5
    I5 -->|primary| BR
    I5 -. fallback .-> GQ
    I1 --> DDB
    I2 --> DDB
    I3 --> DDB
    I4 --> DDB
    I5 --> DDB
    I1 --> S3
    I5 --> S3
    I5 --> O1
    I5 --> O2
    I5 --> O3
    I4 --> O4

    %% ─── Styling ───
    classDef client fill:#1c2128,stroke:#6e7681,color:#fff;
    classDef auth fill:#3d2a14,stroke:#ff9900,color:#fff;
    classDef lb fill:#2d1f3d,stroke:#a371f7,color:#fff;
    classDef i1 fill:#16301c,stroke:#3fb950,color:#fff;
    classDef i2 fill:#16263d,stroke:#4a90d9,color:#fff;
    classDef i3 fill:#3d2c14,stroke:#d99e4a,color:#fff;
    classDef i4 fill:#3d1820,stroke:#f85149,color:#fff;
    classDef i5 fill:#2d1f3d,stroke:#a371f7,color:#fff;
    classDef cache fill:#241a33,stroke:#a371f7,color:#fff;
    classDef ai fill:#143030,stroke:#2dd4bf,color:#fff;
    classDef data fill:#16263d,stroke:#4a90d9,color:#fff;
    classDef out fill:#3d2c14,stroke:#e3b341,color:#fff;
    class MOB,WEB,ALX client;
    class COG,APIGW auth;
    class ALB lb;
    class I1 i1;
    class I2 i2;
    class I3 i3;
    class I4 i4;
    class I5 i5;
    class CACHE cache;
    class BR,GQ ai;
    class DDB,S3 data;
    class O1,O2,O3,O4 out;
```

**Legend** — `──▶️` synchronous flow · `╌╌▶️` external / fallback call · `⚡` DynamoDB cache (native TTL).

**Cross-cutting shared services** (observe & support every layer):

| Service | Role |
|---------|------|
| 📊 **Amazon CloudWatch** | metrics, logs & alarms across all instances — **observability** |
| 🔑 **AWS Secrets Manager** | API keys (Groq), DB creds, Bedrock access — **least privilege** |
| 📣 **Amazon SNS / SES** | emergency alert delivery (SMS / email / push) — **event-driven** |
| 🪣 **Amazon S3** | shared logs & archived voice files — **durable storage** |

| AWS layer | Service | Maps to (local) |
|-----------|---------|-----------------|
| Clients | Mobile · Web · Alexa | React dashboard `:5173` |
| Auth + Entry | Cognito + API Gateway | FastAPI gateway `:8000` |
| Load Balancer | Application Load Balancer | gateway path-routing |
| Compute (ASG) | 5 EC2 instances | the 6 FastAPI services |
| AI & Data | Bedrock → Groq · DynamoDB · S3 | Bedrock/Groq · DynamoDB Local |
| Outputs | Ambience · Notifications · Device control · Emergency alerts | device + narration responses |

---

### Local / codebase architecture

The same services run behind a FastAPI gateway — the model AWS ALB path-routing mirrors in production, forming a complete end-to-end implementation

```mermaid
flowchart TB
    FE["⚛️ React Dashboard<br/>:5173"]
    GW["🚪 API Gateway<br/>:8000"]

    FE --> GW

    subgraph SVC["Microservices (FastAPI)"]
        MO["😌 Mood<br/>:8001"]
        BE["👆 Behaviour<br/>:8002"]
        PA["📊 Patterns<br/>:8003"]
        DE["💡 Devices<br/>:8004"]
        OR["🧠 Orchestrator<br/>:8005"]
        SA["🛡️ Safety<br/>:8006"]
    end

    GW --> MO & BE & PA & DE & OR & SA
    OR -.calls.-> MO & BE & PA & DE

    DB[("🗄️ DynamoDB<br/>Events · State · Patterns<br/>MoodHistory · Profiles")]
    LLM["☁️ Bedrock → Groq<br/>+ Whisper STT"]

    PA --> DB
    SA --> DB
    OR --> DB
    MO --> LLM
    OR --> LLM
    PA --> LLM
    SA --> LLM

    classDef fe fill:#1e3a5f,stroke:#4a90d9,color:#fff;
    classDef gw fill:#3d2f1f,stroke:#d99e4a,color:#fff;
    classDef svc fill:#1e4620,stroke:#3fb950,color:#fff;
    classDef ext fill:#3d1e5c,stroke:#a371f7,color:#fff;
    class FE fe;
    class GW gw;
    class MO,BE,PA,DE,OR,SA svc;
    class DB,LLM ext;
```

| Service | Port | Role |
|---------|:----:|------|
| 🚪 **Gateway** | 8000 | Single entry point · path-based routing · CORS |
| 😌 **Mood** | 8001 | Whisper STT + LLM emotion detection |
| 👆 **Behaviour** | 8002 | Scroll/tap/idle → cognitive-load scoring |
| 📊 **Patterns** | 8003 | Event store + deterministic pattern engine + anomalies |
| 💡 **Devices** | 8004 | Mood → light/music/notification presets |
| 🧠 **Orchestrator** | 8005 | *The brain* — fuses all signals → Action Engine LLM |
| 🛡️ **Safety** | 8006 | Vulnerability-aware twin of the pattern engine |
| 🗄️ **DynamoDB** | 8100 | Events · State · Patterns · MoodHistory · Profiles |

> **Design principles:** graceful degradation (every LLM call has a deterministic fallback) · explainability (confidence + reasoning everywhere) · *no ML in detection* · *LLM only for language* · **Well-Architected Framework** alignment (operational excellence, security, reliability, performance efficiency, cost optimization).

### Repository layout

```
Team-NoWins/
├── backend/
│   ├── gateway/              # API gateway (:8000)
│   ├── config.py             # Shared settings
│   ├── services/
│   │   ├── mood/             # Speech → mood (:8001)
│   │   ├── behavior/         # Interaction → cognitive load (:8002)
│   │   ├── devices/          # Mood → environment presets (:8004)
│   │   └── orchestrator/     # The brain + Action Engine (:8005)
│   ├── patterns/             # Pattern Recognition service (:8003)
│   │   ├── pattern_engine/   #   time / sequence / duration / confidence
│   │   ├── context_builder/  #   anomaly detection + context assembly
│   │   ├── logic/            #   services + LLM narrator
│   │   ├── models/ routes/ dynamodb/ scripts/ tests/
│   └── safety/               # Adaptive Safety service (:8006)
│       ├── context_builder/  #   anomaly.py + safety_overlay.py
│       ├── models/safety.py  #   profiles + vulnerability + assessment
│       └── logic/ routes/ ...
├── frontend/                 # React + Vite dashboards (:5173)
│   └── src/pages/            # Dashboard · Patterns · Safety · Devices · History
├── docs/ARCHITECTURE_DIAGRAMS.md
├── FEATURES.md               # Full feature reference
└── docker-compose.yml
```

---

## 🧰 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19 · Vite 8 · React Router · TailwindCSS 4 · lucide-react |
| **Backend** | Python 3.11+ · FastAPI · Uvicorn · Pydantic v2 |
| **Database** | Amazon DynamoDB (DynamoDB Local / `moto` for dev) — serverless, pay-per-request |
| **LLM — primary** | AWS Bedrock — Nvidia Nemotron Super 3 120B (fully managed, no infrastructure) |
| **LLM — fallback** | Groq — LLaMA 3.3 70B Versatile |
| **Speech-to-Text** | Groq Whisper Large V3 Turbo |
| **Infra** | Docker Compose (9 containers) · `httpx` inter-service calls |

---

## 🚀 Setup

### Prerequisites
- **Docker** & Docker Compose *(easiest path)*, **or** Python 3.11+ and Node 18+ for local dev
- A **Groq API key** (free tier) and/or AWS credentials for Bedrock

### Configure environment

Create `backend/.env`:

```bash
# LLM provider: "groq" or "bedrock"
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key_here
GROQ_LLM_MODEL=llama-3.3-70b-versatile

# AWS Bedrock (optional, if LLM_PROVIDER=bedrock)
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=nvidia.nemotron-super-3-120b

# DynamoDB (local)
DYNAMODB_ENDPOINT_URL=http://localhost:8100
```

And `frontend/.env`:

```bash
VITE_API_BASE_URL=http://localhost:8000        # gateway (mood, devices, history)
VITE_WS_URL=ws://localhost:8000/alexa/stream   # live orchestrator stream
VITE_PATTERNS_API_BASE=http://localhost:8003   # pattern recognition service
VITE_SAFETY_API_BASE=http://localhost:8006     # adaptive safety service
```

### Option A — Docker (everything at once)

```bash
docker-compose up --build
```

Open **http://localhost:5173** 🎉

### Option B — Local development

```bash
# 1. Backend deps
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. Start DynamoDB Local (or moto: `moto_server -p 8100`)
docker run -p 8100:8000 amazon/dynamodb-local

# 3. Launch services (separate terminals, or background)
uvicorn gateway.main:app               --reload --port 8000
uvicorn services.mood.main:app         --reload --port 8001
uvicorn services.behavior.main:app     --reload --port 8002
uvicorn patterns.app.main:app          --reload --port 8003
uvicorn services.devices.main:app      --reload --port 8004
uvicorn services.orchestrator.main:app --reload --port 8005
uvicorn safety.app.main:app            --reload --port 8006

# 4. Frontend
cd ../frontend && npm install && npm run dev
```

### Seed demo data

```bash
# Patterns demo (household H001)
cd backend && python patterns/scripts/seed_data.py

# Safety demo (household E001) — via the dashboard "Simulate" buttons,
# or: curl -X POST "http://localhost:8006/admin/seed/E001?scenario=window_night"
```

### Run the tests

```bash
cd backend && pytest patterns/ safety/   # uses in-memory moto DynamoDB, no AWS needed
```

---

## 📚 Further Reading

| Document | What's inside |
|----------|---------------|
| [`FEATURES.md`](FEATURES.md) | Complete feature-by-feature reference |
| [`docs/ARCHITECTURE_DIAGRAMS.md`](docs/ARCHITECTURE_DIAGRAMS.md) | Detailed block diagrams + parameter tables |
| [`backend/patterns/README.md`](backend/patterns/README.md) | Pattern engine internals & API |
| [`backend/safety/README.md`](backend/safety/README.md) | Safety overlay internals & API |

---

<div align="center">

### 🔑 The one idea to remember

> **Deterministic engines decide _what is true_. The LLM only decides _how to say it_.**
> That's what makes Awaas AI explainable, reliable, and genuinely caring.

<br/>

*Built with ❤️ for HackOn 2026 · Team NoWins · Powered by AWS*

</div>
