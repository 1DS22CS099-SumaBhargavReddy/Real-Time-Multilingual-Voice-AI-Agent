# Real-Time Multilingual Voice AI Agent

A clinical appointment booking system featuring a Real-Time Voice AI Agent capable of understanding spoken language, managing scheduling logic (bookings, rescheduling, cancellations), resolving conflicts, and speaking back responses in English, Hindi, and Tamil.

---

## 🚀 Key Features

- **Real-Time Voice & Text WebSockets**: Bidirectional audio and state streaming over WebSockets.
- **Multilingual Support**: Supports **English**, **Hindi**, and **Tamil** dynamically.
- **Dual Voice Pipeline Modes**:
  - **Hybrid Mode**: Client-side `SpeechRecognition` (STT) and `SpeechSynthesis` (TTS) for fast, low-latency execution.
  - **Server Mode**: Streams microphone data to backend using OpenAI Whisper (STT) and Edge-TTS (TTS) for cross-browser accessibility.
- **Appointment Scheduling Engine**:
  - Automatically identifies user intent (Book, Reschedule, Cancel).
  - Handles scheduling conflicts and provides alternative slot recommendations.
  - SQLite database persists doctors, patients, and calendar slots.
- **Aesthetic Dark Glassmorphic Dashboard**:
  - Visual calendar view showing slot availability.
  - Telemetry board displaying real-time latencies (STT, LLM Thinking, DB Access, TTS, and Total Roundtrip).
  - Live transcripts and detailed LLM thinking logs.

---

## 🛠️ Tech Stack

### Backend
- **FastAPI**: Main API framework for HTTP endpoints and WebSockets.
- **SQLite**: Database for storing doctors, patient profiles (memory), and appointments.
- **Edge-TTS**: Python library for high-quality synthetic voices.
- **OpenAI Whisper & GPT-4o-mini**: Advanced speech-to-text translation and AI reasoning.

### Frontend
- **React (Vite) + TypeScript**: Fast modern UI framework.
- **CSS Modules / Vanilla CSS**: Stunning dark glassmorphism design.

---
<img width="1914" height="852" alt="image" src="https://github.com/user-attachments/assets/4ad8a96d-81fb-4fb8-8267-71a22ec4909f" />
<img width="1893" height="846" alt="image" src="https://github.com/user-attachments/assets/f295c797-099d-40b8-9a93-974c2e93ebbc" />

## 📦 Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+

### Setup & Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/1DS22CS099-SumaBhargavReddy/Real-Time-Multilingual-Voice-AI-Agent.git
   cd Real-Time-Multilingual-Voice-AI-Agent
   ```

2. **Backend Setup**:
   ```bash
   # Create a virtual environment
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt

   # Initialize & start FastAPI server
   python -m uvicorn backend.api.main:app --port 8000
   ```

3. **Frontend Setup**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. **Access the App**:
   Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🧪 Verification & Testing

### 1. Unit Tests
To verify scheduling and conflict resolution rules:
```bash
python -m unittest tests.test_scheduling
```

### 2. Integration Tests
To test real-time WebSocket communication and audio streaming:
```bash
python -X utf8 tests/test_websocket.py
```

---

## ☁️ Cloud Deployment Guide

This app has a split-architecture (Stateless Vite frontend + Stateful WebSocket FastAPI backend). Follow these instructions to deploy them:

### 1. Deploy the Backend (on Render or Railway)

Since this app requires **persistent WebSockets** and **SQLite database** operations, it must be hosted on a persistent web server (not serverless functions).

#### Option A: Render.com
1. Log in to [Render](https://render.com) and click **New > Web Service**.
2. Connect your GitHub repository.
3. Configure the following settings:
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`
4. Add the following Environment Variable:
   - Key: `DATABASE_PATH` | Value: `backend/appointments.db` (Render will build a local file, or you can attach a persistent volume for production storage persistence).
5. Click **Deploy**. Once successfully built, copy the backend URL (e.g., `https://care2-voice-backend.onrender.com`).

---

### 2. Deploy the Frontend (on Vercel)

Vercel is ideal for hosting the static React Vite frontend:
1. Log in to [Vercel](https://vercel.com) and click **Add New > Project**.
2. Select your repository.
3. Configure the Project settings:
   - **Root Directory**: Select `frontend` (important as the frontend resides in this subdirectory).
   - **Framework Preset**: `Vite` (automatically detected).
4. Expand **Environment Variables** and add:
   - **Key**: `VITE_API_URL`
   - **Value**: `https://care2-voice-backend.onrender.com` (Use the URL of your deployed Render/Railway backend).
5. Click **Deploy**. Your frontend is now live!

