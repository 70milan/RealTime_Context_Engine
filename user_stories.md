# Project Roadmap & User Stories

## Completed

- **User Story 4.1 [Complexity: Medium]:** As a developer, I want all personal info (resumes/profiles) completely scrubbed and ignored from the Git history for security. *(Scrubbed personal info and build artifacts from all branches. Updated README with developer setup instructions.)*
- **User Story 4.3 [Complexity: Low]:** As a developer, I want to completely expunge all legacy hardcoded license keys from `backend/main.py` locally AND from all git history/branches to prevent forensic retrieval.
- **User Story 4.2 [Complexity: High]:** As a business owner, I want an offline, hardware-locked licensing system where users send me a Request Code and I generate a License Key, eliminating the need for a central server.
- **User Story 3.1 [Complexity: High]:** As a user, I want a modern UI with premium aesthetics, smooth transitions, and tactile "clickable" feedback on all controls.
- **User Story 2.1 [Complexity: Medium]:** As a user, I want to create new sessions without errors and open past sessions to continue exactly where I left off.
- **User Story 2.3 [Complexity: Medium]:** As a user, when I open a "Past Session", I want to load the *existing* conversation history to review or continue it, rather than creating a new cloned session.
- **User Story 1.1 [Complexity: Low]:** As a user, I want my default model choice (GPT-4o) to be reliably remembered by the application.
- **User Story 5.1 [Complexity: High]:** As a user, I want code blocks (fenced and inline) in AI responses to be properly formatted and syntax-highlighted in both the main response area and the conversation history modals.
- **User Story 5.2 [Complexity: Medium]:** As a user, I want date/time separator headers in the conversation tab and session history, so I can tell when each exchange happened—especially when reviewing sessions that span multiple days/times.
- **User Story 5.3 [Complexity: Medium]:** As a user, I want a [Copy] button on each input/output pair in the conversation tab and session history modal, so I can copy individual exchanges to my clipboard.
- **User Story 5.4 [Complexity: Low]:** As a user, I want timestamps in the Past Sessions list to be formatted in a readable MM/DD/YYYY HH:MM format.
- **User Story 5.5 [Complexity: High]:** As a user, I want the session history modal (past sessions preview) to have the same UI improvements as the live convo tab—code formatting, copy buttons, and date/time markers.
- **User Story 5.6 [Complexity: Medium]:** As a user, I want GPT-5 and higher reasoning models' code blocks to format correctly, not just GPT-4 models. *(Fixed regex to handle GPT-5 formatting variations.)*
- **User Story 5.7 [Complexity: Low]:** As a user, I want date separators in convo/history to show date-only (MM/DD/YYYY) in the same white color as session names, with the time (HH:MM) shown inline next to each Input/Output label instead.
- **User Story 5.8 [Complexity: Low]:** As a user, I want the "Model Used" badge in the AI response area to be right-aligned in the footer for a cleaner layout.
- **User Story 5.9 [Complexity: Low]:** As a user, I want markdown formatting like bold text to be correctly parsed in the UI so code block language labels are clean.
- **User Story 1.4 [Complexity: Low]:** As a user, I want unsupported models like ChatGPT-5 to be removed from the options to avoid connection errors.
- **User Story 2.4 [Complexity: Medium]:** As a user, I want the session status indicator to proactively test the connection, turning green immediately when connected and red if the backend is unreachable.
- **User Story 5.10 [Complexity: Low]:** As a user, I want the "Model Used" indicator to look like a clean footprint signature fixed to the bottom-right of the AI response to track the model used inconspicuously. *(Fixed absolute positioning bug where the footer would overlap with long AI responses by moving it to an inline block with frosted styling)*
- **User Story 5.11 [Complexity: Low]:** As a user, I want the "Cumulative API Cost" label in the past sessions modal to retain the word "Cumulative" while matching the minimalist aesthetic of the main app, using muted soft colors instead of bright yellow.
- **User Story 5.12 [Complexity: Medium]:** As a user, I want a minimalist export button in the conversation history modal to download the entire chat log to a user-specified, elegantly formatted markdown (`.md`) file without emojis.
- **User Story 5.13 [Complexity: Low]:** As a user, I want a dedicated "Copy" button specifically fixed to the top right of every code block within the AI response area to easily extract generated code.
- **User Story 1.2 [Complexity: High]:** As a user, I want the response times for GPT-5 and higher reasoning models to be optimized for interview flow. *(Updated stream pipeline to calculate and display both Time-to-First-Token (TTFT) and Total Response Time in the UI footprint and conversation history, formatted securely as `(1.8s START / 1.9s TOTAL)`)*
- **User Story 1.3 [Complexity: Medium]:** As a user, I want the session state to fully reset when my 2-hour or 5-minute timer expires so that I securely land on a fresh Start Menu instead of mistakenly continuing an expired session state.
- **User Story 5.14 [Complexity: Medium]:** As a user, I want the TTFT and Total Time metrics to persist between responses instead of flashing to `--s` immediately, and the live transcript field to auto-clear once an AI response is fully generated.
- **User Story 5.15 [Complexity: Low]:** As a user, I want all utility buttons (`[copy]` and `[clear]`) to share a unified, sleek monospace aesthetic that turns green or white upon clicking before fading back.
- **User Story 1.5 [Complexity: Low]:** As a user, I want ChatGPT Nano to consistently wrap all generated code inside standard Markdown codeblocks instead of returning unformatted plaintext blocks.
- **User Story 1.6 [Complexity: Low]:** As a user, I want the resume detach 'x' button to be properly hidden when a session ends so that the UI resets cleanly.
- **User Story 1.8 [Complexity: High]:** As a user, I want demo mode sessions to be restricted to once every 47 minutes (calculating the wait from the moment a session ends) to encourage purchasing a full license. *(Implemented high-precision countdown showing minutes and seconds in the status area).*
- **User Story 3.2 [Complexity: Medium]:** As a user, I want a minimalist, console-style status area for all setup feedback, ensuring that validation messages and errors appear in one consistent location with subtle, premium color coding.
- **User Story 3.3 [Complexity: Low]:** As a user, I want the "Demo mode" informational text to intelligently hide once my license is verified, keeping the UI clean and relevant to my current status.
- **User Story 3.4 [Complexity: Low]:** As a user, I want all error and success messages to share a unified, subtle color palette (Red: `rgba(255, 107, 107, 0.5)`, Green: `rgba(100, 255, 150, 0.4)`), with validation status colors only appearing after successful verification to avoid misleading feedback.
- **User Story 4.4 [Complexity: High]:** As an administrator, I want a dedicated license generation script that securely signs Hardware IDs using RSA-PSS padding, matching the application's verification logic exactly.
- **User Story 2.2 [Complexity: High]:** As a user, I want the ability to customize my session profile (e.g., Target Role, Default Programming Language) during session creation so the AI provides more tailored responses. *(Implemented dynamic inputs with localStorage persistence and included Target Role in transcript headers and exports.)*
- **User Story 1.3 [Complexity: Low]:** As a user, I want to verify that when using screenshot capabilities, the system accurately logs the model and response time. *(Verified that backend logs model, TTFT, and total response time for vision requests.)*
- **User Story 5.16 [Complexity: Low]:** As a user, I want my conversation exports to include the session's Target Role and Cumulative API Cost for better tracking.
- **User Story 1.9 [Complexity: Medium]:** As a user, I want the application to detect if another instance is already running and show an error message instead of opening a second one, ensuring system stability. *(Implemented `app.requestSingleInstanceLock()` to prevent dual-launch and instantly pull up existing window).*
- **User Story 1.10 [Complexity: High]:** As a user, I want the application to remain "stealthy" in the Task Manager without requiring a app rename, maintaining a low profile during operation. *(Disguised Frontend as Windows Runtime Host and Backend as WinHostSvc with console=False).*
- **User Story 5.17 [Complexity: Low]:** As a user, I want my Past Sessions list to be sorted by date descending (newest first) instead of oldest first, so I can easily find my most recent interviews. *(Updated backend `/sessions` endpoint and removed frontend reverse sort).*
- **User Story 1.12 [Complexity: Medium]:** As a user, I want to be able to successfully update my OpenAI API key in the Setup screen, and understand why certain project-scoped keys might pass initial validation but fail during chat generation. *(Diagnosed OpenAI project key validation discrepancy and resolved local cache issues causing 401 errors).*
- **User Story 1.13 [Complexity: Medium]:** As a user, I want the application window to scale its internal UI proportionally when using resizing shortcuts and strictly bind window movement to the active display to prevent dragging it out of bounds. *(Implemented `setZoomFactor` scaling synced with window width and added `clampWindowToScreen` boundary enforcement in `main.js`).*
- **User Story 4.5 [Complexity: High]:** As a developer, I want to include digital signatures and author information in the application to prevent antivirus software from flagging it as malware. *(Created `create_cert.bat` to generate a self-signed PFX certificate, and configured Pyinstaller and Electron-Builder to digitally sign both backend and frontend binaries).*
- **User Story 6.1 [Complexity: Low]:** As a developer, I want to obfuscate the frontend JavaScript during the build process to deter unauthorized tampering with license and logic. *(Implemented `javascript-obfuscator` pre/post-build scripts natively in `package.json`).*
- **User Story 6.2 [Complexity: Medium]:** As a developer, I want the backend to independently verify the license status and refuse AI requests if the session is invalid or expired, providing a second layer of security. *(Implemented `check_access_allowed` verification immediately rejecting unauthorized requests on the `/ai/stream` endpoint).*
- **User Story 3.1 [STRETCH] [Complexity: Very High]:** As a developer, I want to obfuscate the application code and the final executable to protect intellectual property and prevent reverse-engineering. *(SKIPPED/RE-EVALUATED: Deemed unnecessary for a $20 offline app; hardware-locked licensing is sufficient protection for this price point).*
- **User Story 7.1 [Complexity: Low]:** As a business owner, I want my contact email (`mjulez70@gmail.com`) and payment links (CashApp/PayPal) integrated into all licensing prompts for easier customer support.
- **User Story 7.2 [Complexity: Low]:** As a user, I want a dedicated "Hotkeys" reference modal accessible from the setup screen and the live status bar, starting with **`Ctrl+Q`** for Mini Mode.
- **User Story 7.3 [Complexity: Low]:** As a user, I want the "Convo" button moved next to the "Process" button for a more ergonomic session workflow.
- **User Story 7.4 [Complexity: Medium]:** As a developer, I want robust logging and error handling for the auto-updater to resolve "silent failures" and identify machine-specific certificate trust issues.
- **User Story 5.18 [Complexity: Low]:** As a user, I want the AI input text to clear only once I start providing the next input, so I can review my previous query after the response is generated. *(Implemented `shouldClearTranscriptOnNextInput` logic to persist text until the next keystroke.)*

## Pending

*(All current user stories have been successfully completed!)*

---

## Technical Notes & Context
- **User Story 3.1:** Re-evaluating. Moved to automated obfuscation (6.1) and backend anchor (6.2).
- **Update Strategy:** Distribute via a private source repo and a public "releases-only" repo to maintain code privacy while allowing auto-updates.

