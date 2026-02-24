# Interview Assistant: Professional Prep & Live Aid
> **Contact:** [mjulez70@gmail.com](mailto:mjulez70@gmail.com)

**Interview Assistant** (internally known as *Windows Runtime Host*) is a professional-grade tool designed to assist candidates during technical and behavioral interviews. By combining real-time audio capture, screen analysis, and high-performance AI reasoning, it provides the edge needed to navigate complex live interview scenarios with confidence.

---

##  Stealth & Professionalism
Unlike traditional "Co-pilots," this application is built with professional discretion as a core pillar:
- **Process Disguise**: Appears as "Windows Runtime Host" in Task Manager to maintain a low profile.
- **Stealth UI**: Minimalist, frosted-glass design that stays inconspicuous on your desktop.
- **Hotkeys**: Quick controls (Ctrl+Q, Ctrl+K, Ctrl+S) for rapid, silent interaction.

---

##  Key Features
### 1. Multi-Modal Context Awareness
- **AI with Vision**: Captures and analyzes shared screen frames (coding problems, architectural diagrams) using **GPT-4o**.
- **Real-time Transcription**: Seamlessly listens to microphone and system audio to capture interviewers' questions.

### 2. High-Performance AI Pipeline
- **Optimized Streaming**: Server-Sent Events (SSE) provide ultra-low latency responses.
- **Model Selector**: Switch between GPT-4o, GPT-3.5 Turbo, and high-reasoning **GPT-5 Nano/Mini** models on the fly.
- **Metric Tracking**: Tracks Time-to-First-Token (TTFT) and total response time to ensure the interview flow is never broken.

### 3. Session & Profile Customization
- **Tailored Personas**: Set your **Target Role** and **Preferred Language** (e.g., Python, Java) during setup for persona-aligned responses.
- **Persistent History**: Save, resume, and sort interview sessions by date. Review past performance or export logs to Markdown (`.md`).
- **Cost Control**: Real-time cumulative API cost tracking per session.

### 4. Enterprise-Grade Security
- **Hardware-Locked Licensing**: RSA-secured licensing system locked to your unique Hardware ID (HWID).
- **Backend Enforcement**: License and demo limits are enforced at the backend level to prevent unauthorized bypass.

---

##  Ethical Usage Policy
This tool is intended for **assistance and preparation**. We market it as an "Assistant" to support your natural knowledge:
- Use it to verify complex syntax or double-check architectural patterns.
- Use it as a real-time prompt for behavioral stories you've already prepared.
- **Intent**: To augment your human performance, not replace it.

---

##  Getting Started

### Prerequisites
*   **Node.js** (v18+): [Download](https://nodejs.org/)
*   **Python** (v3.10+): [Download](https://www.python.org/)

### Setup & Run
1.  **Clone the Repo**:
    ```bash
    git clone https://github.com/mjulez70/job_bandit.git
    cd job_bandit
    ```
2.  **Install Dependencies**:
    - **Frontend**: `cd frontend && npm install`
    - **Backend**: `cd ../backend && pip install -r requirements.txt`
3.  **Launch**:
    - Use the provided `build-all.bat` for a full production environment.
    - Or run in developer mode using `npm run start:dev` from the `frontend` folder.

---

## 📂 Project Architecture
- `frontend/`: Electron core with Vanilla JS/HTML.
- `backend/`: FastAPI server managing AI logic, token counts, and session persistence.
- `scripts/`: Build-time utilities including code obfuscation filters.
