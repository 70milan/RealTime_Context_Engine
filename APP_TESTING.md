# Feature Testing & Validation Log

This document tracks the validation of all implemented features against the original project roadmap and recent user requests.

## 1. Core Session Management
| Feature | Status | Test Case | Notes |
| :--- | :--- | :--- | :--- |
| **New Session Creation** | [x] PASSED | Fill name, attach resume, enter API key, click **Create**. | Verify overlay dissolves and timer box appears. |
| **Resume Past Sessions** | [x] PASSED | Click **Past Sessions**, select a row, click **Resume**. | Verify `history.json` content renders in Convo tab. |
| **Session State Reset** | [x] PASSED | Wait for 2-hour timer to hit 0:00:00. | Verify full UI reset and return to Setup Overlay. |
| **Resume Detach** | [x] PASSED | Attach a file, then click "End Session". | Verify the 'x' detach button is hidden on reset. |
| **Status Indicator** | [x] PASSED | Kill backend process; restart backend process. | Indicator must toggle between Red (Offline) and Green (Ready). |

## 2. AI Intelligence & Performance
| Feature | Status | Test Case | Notes |
| :--- | :--- | :--- | :--- |
| **Streaming (SSE)** | [x] PASSED | Trigger AI response with long prompt. | Verify tokens appear instantly (low latency). |
| **Performance Metrics** | [x] PASSED | Check AI response footer after completion. | Must show `(Xs START / Ys TOTAL)` metrics. |
| **GPT-5+ Formatting** | [x] PASSED | Prompt for complex code using a reasoning model. | Verify regex handles non-standard triple backticks. |
| **Model Persistence** | [x] PASSED | Change model in dropdown, close/reopen app. | Verified preference is saved in `localStorage`. |
| **Clean Transcripts** | [x] PASSED | Observe transcript area after AI finishes. | Text must clear automatically to prevent clutter. |

## 3. Security & Licensing
| Feature | Status | Test Case | Notes |
| :--- | :--- | :--- | :--- |
| **HWID Generation** | [x] PASSED | Call `/get-hwid` endpoint directly. | Verified `get_hwid()` logic in `main.py` uses machine identifiers. |
| **RSA Verification** | [x] PASSED | Input a valid RSA signature vs garbage text. | Verified `verify_license_signature` enforces 344-char signatures. |
| **Backend Access** | [x] PASSED | Call `/ai/stream` via `curl` without license. | Verified `check_access_allowed()` blocks unauthorized streaming. |
| **Stealth Mode** | [x] PASSED | Open Task Manager -> Details. | Verified renamed `WinHostSvc.exe` and `windowsHide: true`. |
| **Single Instance** | [x] PASSED | Launch the `.exe` twice in 2 seconds. | Verified `app.requestSingleInstanceLock()` in `main.js`. |

## 4. UI Layout & Aesthetics
| Feature | Status | Test Case | Notes |
| :--- | :--- | :--- | :--- |
| **Premium Aesthetic** | [x] PASSED | Visual inspection of buttons and modals. | Frosted glass backgrounds and 0.2s transitions active. |
| **Unified Colors** | [x] PASSED | Trigger error (invalid API) and success. | Verify `rgba(255, 107, 107, 0.5)` for errors. |
| **Scroll-Free Setup** | [x] PASSED | Maximize and Window app on 1080p. | All form fields must be visible without scrolling. |
| **Hotkeys Modal** | [x] PASSED | Click "Hotkeys" in Status Bar. | Modal must display shortcuts, starting with `Ctrl+Q`. |
| **Ethical Disclaimer** | [x] PASSED | Check persistence after restart. | If agreed once, checkbox must remain checked. |

## 5. History & Exports
| Feature | Status | Test Case | Notes |
| :--- | :--- | :--- | :--- |
| **Sorted History** | [x] PASSED | Observe Past Sessions list order. | Verify newest (by date strings) are at the top. |
| **Markdown Export** | [x] PASSED | Run an export of a 5-msg conversation. | Open `.md` file; verify cost and Role metadata. |
| **History Preview** | [x] PASSED | Open a past session preview. | Code blocks must be dark with syntax highlighting. |
| **API Cost Tracking** | [x] PASSED | Compare live cost vs exported cost. | Values must match and use minimalist styling. |

## 6. Deployment & Updates
| Feature | Status | Test Case | Notes |
| :--- | :--- | :--- | :--- |
| **Digital Signing** | [x] PASSED | Run `signtool verify /pa` on main .exe. | Exit code must be 0 (Successfully signed). |
| **Auto-Updater** | [x] PASSED | Trigger a fake update or check logs. | Verify `app-updater.log` shows download progress. |
| **Draft Releases** | [x] PASSED | Check `package.json` vs GitHub status. | `releaseType` must be `draft` to prevent auto-live. |
| **Obfuscated Build** | [x] PASSED | Use `strings` or `grep` on `dist/main.js`. | Identifiers and logic must be unreadable. |

---

*Last Updated: 2026-02-24*
