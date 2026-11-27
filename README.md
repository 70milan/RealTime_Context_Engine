# RealTime Context Engine

**A free, open-source AI interview copilot and mock-interview coach for Windows.**
It knows your resume and the job description, so its cues come from *your* experience. Or it runs a full mock interview out loud and reviews every answer.

<p align="center">
  <a href="https://github.com/mjulez70/realtimecontextengine/releases/latest"><img alt="Download for Windows" src="https://img.shields.io/badge/Download-Windows%20installer-2ea44f?style=for-the-badge&logo=windows"></a>
</p>

<p align="center">
  <img alt="Latest release" src="https://img.shields.io/github/v/release/mjulez70/realtimecontextengine?label=latest">
  <img alt="Downloads" src="https://img.shields.io/github/downloads/mjulez70/realtimecontextengine/total">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="Platform: Windows" src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4?logo=windows">
</p>

<!-- DEMO: add a 30-45 second GIF of Practice mode here (question read aloud, your answer, follow-up, round review)
<p align="center"><img src="docs/demo.gif" width="760" alt="Practice mode demo"></p>
-->

> **No subscription. No account. No time limits. MIT licensed.**
> You bring your own OpenAI key (an hour of live use costs roughly 40¢), and Practice mode can run free on a Groq key.

**On this page:** [Features](#features) · [How it compares](#how-it-compares) · [Install](#install) · [Quick start](#quick-start) · [Honest limits](#honest-limits) · [FAQ](#faq) · [Privacy](#privacy) · [Costs](#what-it-costs-to-use) · [Roadmap](#roadmap) · [Build from source](#build-from-source) · [Contributing](#contributing)

---

## Features

### Practice mode: a mock interviewer that knows your resume
- Writes realistic questions from **your resume and the job description**: your real projects, the skills the job asks for, and the gaps between them.
- **Reads them out loud** in a natural voice and listens hands-free. Your answer ends when you stop talking (or press Space).
- **Follows up** when an answer is vague, the way a real interviewer drills in.
- **Coding questions** open a code box for your solution.
- After each round, a **review of every answer**: what you covered, what you missed, and exactly what to say next time.
- **Never repeats a question** for the same job. Pick the focus: mixed, behavioural, technical, or coding.
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

## How it compares

There are good free tools in this space. This is how they differ, taken from each project's own README in November 2026. I haven't run every one of them, so corrections are welcome.

| | **This app** | [Cheating Daddy](https://github.com/sohzm/cheating-daddy) | [Pluely](https://github.com/iamsrikanthnani/pluely) | [Natively](https://github.com/Natively-AI-assistant/natively-cluely-ai-assistant) | [free-cluely](https://github.com/Prat011/free-cluely) |
|---|---|---|---|---|---|
| **License** | MIT | GPL-3.0 | GPL-3.0 | Personal-use source license | Apache-2.0 |
| **Free to use** | Fully free | Fully free | Free with your own keys; Pro plans sold | Free with your own keys; plans from $8/mo | Fully free |
| **Resume + job description grounding** | **Built in, free** | One pasted context box | Not advertised | Pro (paid) | Not advertised |
| **Mock-interview practice with follow-ups and reviews** | **Yes** | No | No | Not advertised | No |
| **Answers avoid inventing experience** | **Built in** | Not a focus | Not a focus | Not a focus | Not a focus |
| **Real per-answer cost shown** | **Yes** | No | No | No | No |
| **AI provider** | OpenAI (Groq for Practice) | Gemini free tier, Groq, local | Any, via custom endpoint | Many, plus local | Gemini or local Ollama |
| **Runs fully offline** | No | Optional local mode | With a local model | With Ollama | With Ollama |
| **Platforms** | Windows | Windows, Mac, Linux (beta) | Windows, Mac, Linux | Windows, Mac | Desktop |

**Where the others are stronger:** Cheating Daddy and free-cluely have **free or offline AI**, and several have **Mac and Linux builds**. Pluely's installer is a fraction of the size. Natively has more providers and meeting notes. **Where this app is stronger:** it's built around *your* resume and the job, it can **coach** you instead of only feeding you lines, and it's honest about what you've actually done.

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

<!-- SCREENSHOTS: add the setup screen, a live session, and a Practice round review here
<p align="center"><img src="docs/setup.png" width="380"> <img src="docs/practice.png" width="380"></p>
-->

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

---

## Honest limits

- **Windows only** for now. There are no Mac or Linux builds.
- **It needs the internet and an API key.** There's no offline mode: audio and text go to OpenAI (and Groq if you use it) for transcription and answers.
- **Free AI tiers can't carry a live interview.** Groq and Gemini's free plans have request and token limits that can run out mid-interview, so live answers use OpenAI. Practice mode is where a free Groq key works well.
- **The installer isn't code-signed**, so Windows shows an "unknown publisher" warning the first time.
- **The AI can still be wrong.** Check technical details, and read what it suggests before you say it.

## FAQ

**Is it really free?** Yes: no subscription, no license key, no time limit. You only pay OpenAI for what you use.

**What does it cost to run?** About 40¢ for an hour of live use (mostly transcription), roughly 3¢ per 100 answers, and 3–5¢ per Practice review. $1 of OpenAI credit covers a few interviews. See [costs](#what-it-costs-to-use).

**Do I need a Groq key?** No. It's optional and only makes Practice mode free.

**Where does my data go?** It's stored only on your PC. It's sent only to the services whose keys you provide, plus Microsoft's free voice service for the Practice interviewer. See [Privacy](#privacy).

**Can I use it for coding questions?** Yes: screenshots solve problems on your screen, and Practice mode has a coding round with a code box.

**Is it the same as Cluely, Final Round AI and the rest?** No. Those are built to feed you answers. This one is built around your resume, and around helping you practise until you don't need the cues.

**Can I change it?** Yes: it's MIT licensed and the code is split into small modules. See [Contributing](#contributing).

---

## Privacy

- **Stored on your PC only:** sessions, resumes, Talking Points and history are kept in `%APPDATA%\jobandit`. There's no server of ours and no account.
- **Sent out only as needed, to the services you gave keys for:** live audio and text to OpenAI; Practice text and your recorded answers to Groq if you use a Groq key; each Practice question's text to Microsoft's free text-to-speech to speak it; update checks to GitHub.
- **API keys are encrypted** with your Windows account (DPAPI) and never saved inside a session.
- **No analytics, no tracking.**

## What it costs to use
The app is free. You pay OpenAI directly for what you use:
- **Answers** on gpt-4o-mini: about 0.03¢ each.
- **Live transcription:** about $0.18 per hour per audio source (both sources: about $0.36 per hour).
- **Practice reviews** on gpt-4o: 3–5¢ a round.

The app shows the running cost of each session.

## Roadmap
Ideas, not promises. Open an issue if one matters to you.
- **Story bank:** your 8–10 best stories with the follow-ups they usually trigger, for the night before.
- **"Based on" line:** show which resume line each answer came from, and flag what's *not* on your resume.
- **Optional free answer mode** on Groq or Gemini, clearly labelled, for light use.
- **Offline option** with local models.
- **Mac support.**

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

## Contributing
Issues and pull requests are welcome. Good places to start:
- a new AI provider (the backend already talks to Groq through an OpenAI-compatible endpoint);
- a Mac or Linux port of the audio capture;
- anything on the [roadmap](#roadmap).

Run the app with `npm run start:dev`, change one thing, and open a pull request with a short description of what and why.

---

## Responsible use
Use it to prepare, to practise, and where the interview allows assistance. Many companies don't allow AI help during interviews; it's your responsibility to follow their rules. The software is provided as-is, without warranty.

## Support
It's free. If it helped you land something, you can [buy me a coffee ☕](https://buymeacoffee.com/mjulez70v).

## License
[MIT](LICENSE)
