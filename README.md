# RealTime Context Engine

**A free, open-source AI interview copilot and mock-interview coach for Windows.**
It listens to the interview, knows your resume and the job description, and gives you short, accurate cues. Or it runs a full mock interview out loud and reviews every answer.

<p align="center">
  <a href="https://github.com/mjulez70/realtimecontextengine/releases/latest"><img alt="Download for Windows" src="https://img.shields.io/badge/Download-Windows%20installer-2ea44f?style=for-the-badge&logo=windows"></a>
</p>

<p align="center">
  <img alt="Latest release" src="https://img.shields.io/github/v/release/mjulez70/realtimecontextengine?label=latest">
  <img alt="Downloads" src="https://img.shields.io/github/downloads/mjulez70/realtimecontextengine/total">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue">
</p>

No subscription, no account, no time limits. You bring your own OpenAI API key (an hour-long session usually costs well under a dollar), and Practice mode can run free on a Groq key.

---

## Features

### Practice mode: a mock interviewer that knows your resume
- Writes realistic questions from **your resume and the job description**: your real projects, the skills the job asks for, and the gaps between them.
- **Reads them out loud** with a natural voice and listens hands-free. Your answer ends when you stop talking.
- **Follows up** when an answer is vague, the way a real interviewer drills in.
- **Coding questions** open a code box for your solution.
- After each round, a **review of every answer**: what you covered, what you missed, and exactly what to say next time.
- **Never repeats a question** for the same job, and pick the focus: mixed, behavioural, technical, or coding.
- **Free with a Groq key** (optional). Without one it uses your OpenAI key, about 10¢ a round.

### Live sessions
- **Live transcription** of the interviewer (system audio) and you (microphone).
- **Smart Interview:** tells who's speaking and answers automatically when a question is finished.
- **Cue Mode:** 3–5 short bullet cues instead of a script, so you answer in your own words.
- **ESL Mode:** short, simple sentences.
- **Screenshots:** solve the coding problem or diagram on your screen.
- **Grounded in your experience:** names a tool only at the job your resume lists it under, and never invents numbers.

### Talking Points
One click turns your resume and the job description into a short brief of the experience that matters for that job, plus how to answer. Edit it and add your own rules ("say watermark, not CDC"); every answer follows them.

### Answer Review
Every session keeps the questions, the suggestions and what you actually said. **Critique** compares them and tells you what to fix.

---

## Install

1. **[Download the latest installer](https://github.com/mjulez70/realtimecontextengine/releases/latest)** (`Windows-Runtime-Host-Setup-x.y.z.exe`).
2. Run it. Windows may say **"Windows protected your PC"** because the installer isn't signed by a paid certificate yet: click **More info → Run anyway**. The full source code is right here if you want to check what it does.
3. The app updates itself when a new version is out.

**You need:** Windows 10 or 11, and an [OpenAI API key](https://platform.openai.com/api-keys) with a little credit. A [Groq key](https://console.groq.com/keys) is optional, for free Practice mode.

## Quick start

1. Open the app, choose **Live** or **Practice**, and fill in a session name, the role, your resume (`.docx`) and the job description.
2. Paste your OpenAI key (and optionally a Groq key for Practice).
3. Optional: click **Generate** under Talking Points, then edit the brief.
4. **Create Session**, then **Start**.

## Hotkeys

| Keys | Action |
|---|---|
| Ctrl+R / Ctrl+M | Start or stop system audio / microphone |
| Ctrl+Enter | Answer the current transcript |
| Ctrl+Alt+A | Smart Interview on/off |
| Ctrl+K / Ctrl+S | Screenshot and solve (Ctrl+S keeps it for follow-ups) |
| Ctrl+Backspace | Clear the transcript |
| Ctrl+F | Enlarge the answer |
| ↑ / ↓, Page Up / Down, Home / End | Scroll the answer (app focused) |
| Ctrl+Alt+U / I | Scroll the answer (from any app) |
| Ctrl+Q | Mini mode on/off |
| Ctrl+Alt+C | Conversation window |
| Ctrl+Shift+Q | Quit |
| Space | Practice: end your answer |

## Privacy

- **Everything stays on your PC:** sessions, resumes and settings are stored in `%APPDATA%\jobandit`.
- **API keys are encrypted** with your Windows account (DPAPI) and are never stored per session.
- **The only outside services** are the ones you give keys for: OpenAI, and Groq if you use it. The practice voice uses Microsoft's free text-to-speech service.
- **No analytics, no tracking, no account.**

## What it costs to use
The app is free. You pay OpenAI directly for what you use:
- **Answers** on gpt-4o-mini: about 0.03¢ each.
- **Live transcription:** about $0.18 per hour per audio source.
- **Practice reviews** on gpt-4o: 3–5¢ a round.

The app shows the running cost of each session.

---

## Build from source

**Prerequisites:** Windows, [Node.js](https://nodejs.org) 20+, [Python](https://www.python.org) 3.13.

```bat
:: Backend (Python / FastAPI)
cd backend
python -m venv .venv-build
.venv-build\Scripts\python -m pip install -r requirements.txt

:: Frontend (Electron)
cd ..\frontend
npm install

:: Run both in development
npm run start:dev
```

`build-all.bat` packages the backend with PyInstaller, builds the Windows installer with electron-builder, and publishes a GitHub release. It needs a `GH_TOKEN`, and optionally a code-signing certificate.

### Project layout

```
backend/
  main.py              FastAPI app: auth middleware, routers, startup
  WinHostSvc.py        launcher used by the packaged app
  engine/
    config.py          paths, models, prices
    usage.py           token counting and session cost
    user_profile.py    profile on disk, encrypted keys, OpenAI client
    session_store.py   session folders and saved conversations
    context.py         active session context and answer prompts
    memory.py          last questions verbatim + notes on older ones
    answers.py         streamed answers and Smart Interview detection
    transcription.py   live transcription (OpenAI Realtime)
    practice.py        Practice mode
    api_sessions.py    session endpoints
    api_review.py      Talking Points brief and Critique
    api_settings.py    models, key check, usage
frontend/
  main.js              Electron main process: windows, hotkeys, updates
  preload.js           the only bridge between pages and Electron
  index.html           main window, convo.html: conversation window
  js/                  app.js (capture, Smart, screenshots), setup.js, streaming-ai.js, practice.js, convo.js
  css/                 app.css, setup.css, convo.css
```

### How it works
- **Electron** shows the windows and captures audio.
- **The FastAPI backend** runs on `127.0.0.1:5050`, locked to the app with a per-launch token.
- **Audio** streams over a WebSocket to OpenAI's Realtime transcription.
- **Each answer** is built from one fixed session prompt (role, your brief or resume, the job description, your modes), which OpenAI's prompt cache bills at a discount after the first answer. Added on top: short notes on earlier questions, the last two questions word for word, and the new question.

---

## Responsible use
Use it to prepare, to practise, and where the interview allows assistance. Many companies don't allow AI help during interviews; it's your responsibility to follow their rules. The software is provided as-is, without warranty.

## Support
It's free. If it helped you land something, you can [buy me a coffee ☕](https://buymeacoffee.com/mjulez70v).

## License
[MIT](LICENSE)
