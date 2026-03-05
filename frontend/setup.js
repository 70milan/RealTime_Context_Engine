// Session Setup & Timer Logic
// Session Setup & Timer Logic


const FULL_SESSION_DURATION_MS = 2 * 60 * 60 * 1000; // 2 hours
const DEMO_SESSION_DURATION_MS = 12 * 60 * 1000; // 12 minutes

const DEMO_COOLDOWN_MS = 47 * 60 * 1000; // 47 minutes
let SESSION_DURATION_MS = DEMO_SESSION_DURATION_MS; // Default to demo
let sessionEndTime = null;
let timerInterval = null;
let sessionCreated = false;
let sessionTimerStarted = false;
let currentSessionName = null;  // Track current session name
let isLicensed = false; // Track license status
let sessionStartTimestamp = null; // Track when session started for duration calculation
let backendReady = false; // Track if backend has finished starting

// Helper to check demo cooldown remaining time (in ms)
function getRemainingDemoCooldown() {
    const lastDemoTime = localStorage.getItem('last_demo_timestamp');
    if (!lastDemoTime) return 0;

    const elapsed = Date.now() - parseInt(lastDemoTime);
    if (elapsed < DEMO_COOLDOWN_MS) {
        return DEMO_COOLDOWN_MS - elapsed;
    }
    return 0;
}

// Helper to format ms into "X min and Y second(s)"
function formatCooldownTime(ms) {
    const totalSeconds = Math.ceil(ms / 1000);
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;

    if (mins > 0) {
        return `${mins} min and ${secs} second(s)`;
    }
    return `${secs} second(s)`;
}

// License validation (Hardware-Locked)
async function validateLicense(key) {
    if (!key || key.trim() === '') return 'empty';

    try {
        console.log('[DEBUG] Calling validate-license endpoint...');
        const res = await fetch('http://127.0.0.1:5050/validate-license', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ license_key: key.trim() })
        });
        console.log('[DEBUG] Response status:', res.status);
        const data = await res.json();
        console.log('[DEBUG] Response data:', data);
        return data.status; // 'valid', 'invalid', or 'empty'
    } catch (e) {
        console.error('[DEBUG] License validation error:', e);
        // If backend is down, allow demo mode
        return 'empty';
    }
}

// Session lock - prevents actions until Start is clicked
window.isSessionActive = false;

// Custom styled alert/confirm functions
function showCustomModal(message, isConfirm = false) {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-modal');
        const msgEl = document.getElementById('custom-modal-message');
        const okBtn = document.getElementById('custom-modal-ok');
        const cancelBtn = document.getElementById('custom-modal-cancel');

        // Allow HTML in message for HWID display
        msgEl.innerHTML = message.replace(/\n/g, '<br>');
        cancelBtn.style.display = isConfirm ? 'block' : 'none';
        modal.style.display = 'flex';

        const handleOk = () => {
            modal.style.display = 'none';
            cleanup();
            resolve(true);
        };

        const handleCancel = () => {
            modal.style.display = 'none';
            cleanup();
            resolve(false);
        };

        const cleanup = () => {
            okBtn.removeEventListener('click', handleOk);
            cancelBtn.removeEventListener('click', handleCancel);
        }

        okBtn.addEventListener('click', handleOk);
        cancelBtn.addEventListener('click', handleCancel);

        // Focus OK button for keyboard navigation
        okBtn.focus();
    });
}

window.customAlert = (msg) => showCustomModal(msg, false);
window.customConfirm = (msg) => showCustomModal(msg, true);

// Get HWID helper
async function getHardwareID() {
    try {
        const res = await fetch('http://127.0.0.1:5050/get-hwid');
        const data = await res.json();
        return data.hwid || 'Unknown';
    } catch (e) {
        console.error("Failed to fetch HWID:", e);
        return "Backend Offline";
    }
}

// License prompt after demo expires
async function showLicensePrompt() {
    const hwid = await getHardwareID();
    const result = await customConfirm(
        `Demo session expired (12 min).\n\n` +
        `Your Hardware ID: <strong style="color: #64ff96; user-select: all;">${hwid}</strong>\n\n` +
        `Email this ID to: <strong style="color: #64ff96; user-select: all;">mjulez70@gmail.com</strong>\n\n` +
        `One-time payment of $20 only.\n` +
        `CashApp: <a href="https://cash.app/$passdpawn" target="_blank" style="color: rgba(100, 255, 150, 0.9); text-decoration: underline;">$passdpawn</a>\n` +
        `PayPal: <a href="https://paypal.me/passdpawn" target="_blank" style="color: rgba(100, 255, 150, 0.9); text-decoration: underline;">paypal.me/passdpawn</a>\n\n` +
        `Click OK to enter license, or Cancel to return to setup.`
    );

    if (result) {
        // Show setup overlay again so user can enter license
        const overlay = document.getElementById('setup-overlay');
        if (overlay) {
            overlay.style.display = 'flex';
            // Focus on license input
            setTimeout(() => {
                const licenseInput = document.getElementById('setup-license');
                if (licenseInput) {
                    licenseInput.focus();
                    licenseInput.style.borderColor = 'rgba(100, 255, 150, 0.5)';
                }
            }, 100);
        }
        // Reset session state
        sessionCreated = false;
        window.isSessionActive = false;
    } else {
        // Return to setup screen
        const overlay = document.getElementById('setup-overlay');
        if (overlay) {
            overlay.style.display = 'flex';
        }
        sessionCreated = false;
        window.isSessionActive = false;
    }
}


function showSessionError() {
    const popup = document.getElementById('session-error-popup');
    if (popup) {
        popup.style.display = 'block';
        popup.style.opacity = '1';
        setTimeout(() => {
            popup.style.opacity = '0';
            setTimeout(() => { popup.style.display = 'none'; }, 200);
        }, 2000);
    }
}

window.showSessionError = showSessionError;

// Global validation function
function checkAllInputs() {
    const sessionNameInput = document.getElementById('setup-session-name');
    const fileInput = document.getElementById('setup-resume');
    const apiKeyInput = document.getElementById('setup-apikey');
    const roleInput = document.getElementById('setup-role');
    const langInput = document.getElementById('setup-language');
    const jdInput = document.getElementById('setup-jobdesc');
    const startBtn = document.getElementById('btn-start-session');

    const hasSessionName = sessionNameInput && sessionNameInput.value.trim().length > 0;
    const hasFile = fileInput && fileInput.files && fileInput.files.length > 0;
    const hasApiKey = apiKeyInput && apiKeyInput.value.trim().length > 0;
    const hasRole = roleInput && roleInput.value.trim().length > 0;
    const hasLang = langInput && langInput.value.trim().length > 0;
    const hasJD = jdInput && jdInput.value.trim().length > 0;

    // Button is always clickable but style reflects readiness
    if (hasSessionName && hasFile && hasApiKey && hasRole && hasLang && hasJD && startBtn) {
        startBtn.style.opacity = '1';
    } else if (startBtn) {
        startBtn.style.opacity = '0.5';
    }
}

// Backend health check - polls until backend is responsive
async function waitForBackend() {
    const pastSessionsBtn = document.getElementById('btn-past-sessions');
    const startBtn = document.getElementById('btn-start-session');

    // Show starting state on Past Sessions button
    if (pastSessionsBtn) {
        pastSessionsBtn.innerHTML = '&#9203; Starting...';
        pastSessionsBtn.style.opacity = '0.4';
        pastSessionsBtn.style.cursor = 'not-allowed';
    }

    const poll = async () => {
        try {
            const res = await fetch('http://127.0.0.1:5050/sessions', { signal: AbortSignal.timeout(2000) });
            if (res.ok) {
                backendReady = true;
                console.log('[BACKEND] Backend is ready!');

                // Refresh HWID display now that backend is ready
                if (typeof updateHWIDDisplay === 'function') {
                    updateHWIDDisplay();
                }

                if (pastSessionsBtn) {
                    pastSessionsBtn.innerHTML = 'Past Sessions';
                    pastSessionsBtn.style.opacity = '1';
                    pastSessionsBtn.style.cursor = 'pointer';
                }
                // Clear any lingering "backend starting" message
                const status = document.getElementById('setup-status');
                if (status && status.innerText.includes('starting')) {
                    status.innerText = '';
                }
                return;
            }
        } catch (e) {
            // Backend not ready yet
        }
        // Retry in 2 seconds
        setTimeout(poll, 2000);
    };

    poll();
}

// Initialize immediately since script is loaded at end of body
initSession();
waitForBackend();

function initSession() {
    const sessionNameInput = document.getElementById('setup-session-name');
    const fileInput = document.getElementById('setup-resume');
    const apiKeyInput = document.getElementById('setup-apikey');
    const jdInput = document.getElementById('setup-jobdesc');
    const startBtn = document.getElementById('btn-start-session');
    const resumeFilename = document.getElementById('resume-filename');

    console.log('[DEBUG] initSession: fileInput found?', !!fileInput);
    console.log('[DEBUG] initSession: resumeFilename found?', !!resumeFilename);

    // Update filename display when file is selected
    if (fileInput && resumeFilename) {
        fileInput.addEventListener('change', () => {
            console.log('[DEBUG] File input changed!');
            console.log('[DEBUG] Files:', fileInput.files);
            const detachBtn = document.getElementById('resume-detach-btn');
            if (fileInput.files && fileInput.files.length > 0) {
                console.log('[DEBUG] Selected file:', fileInput.files[0].name);
                resumeFilename.textContent = fileInput.files[0].name;
                resumeFilename.style.color = 'rgba(255, 255, 255, 0.6)';
                if (detachBtn) detachBtn.style.display = 'inline-block';
            } else {
                resumeFilename.textContent = 'No file chosen';
                resumeFilename.style.color = 'rgba(255, 255, 255, 0.4)';
                if (detachBtn) detachBtn.style.display = 'none';
            }
            checkAllInputs();
        });

        // Resume detach button
        const detachBtn = document.getElementById('resume-detach-btn');
        if (detachBtn) {
            detachBtn.addEventListener('click', () => {
                fileInput.value = '';
                resumeFilename.textContent = 'No file chosen';
                resumeFilename.style.color = 'rgba(255, 255, 255, 0.4)';
                detachBtn.style.display = 'none';
                checkAllInputs();
            });
        }
    }

    if (sessionNameInput) {
        sessionNameInput.addEventListener('input', checkAllInputs);
    }
    if (fileInput) {
        fileInput.addEventListener('change', function () {
            if (fileInput.files && fileInput.files.length > 0) {
                fileInput.classList.add('selected');
            }
            checkAllInputs();
        });
    }
    if (apiKeyInput) {
        // Load saved API key from localStorage
        const savedApiKey = localStorage.getItem('openai_api_key');
        if (savedApiKey) {
            apiKeyInput.value = savedApiKey;
            console.log('[DEBUG] API key loaded from localStorage');
        }
        apiKeyInput.addEventListener('input', () => {
            // Save API key as user types
            const val = apiKeyInput.value.trim();
            if (val) {
                localStorage.setItem('openai_api_key', val);
            }
            checkAllInputs();
        });
    }

    const roleInput = document.getElementById('setup-role');
    if (roleInput) {
        const savedRole = localStorage.getItem('target_role');
        if (savedRole) roleInput.value = savedRole;
        roleInput.addEventListener('input', () => {
            const val = roleInput.value.trim();
            if (val) localStorage.setItem('target_role', val);
            checkAllInputs();
        });
    }

    const langInput = document.getElementById('setup-language');
    if (langInput) {
        const savedLang = localStorage.getItem('target_language');
        if (savedLang) langInput.value = savedLang;
        langInput.addEventListener('input', () => {
            const val = langInput.value.trim();
            if (val) localStorage.setItem('target_language', val);
            checkAllInputs();
        });
    }

    if (jdInput) {
        jdInput.addEventListener('input', checkAllInputs);
    }



    // Check for saved valid license - verify it's still valid with current backend/HWID
    const licenseInput = document.getElementById('setup-license');
    const savedLicense = localStorage.getItem('valid_license_key');
    const licenseBadge = document.getElementById('license-status-badge');

    const demoInfoText = document.getElementById('demo-info-text');

    if (savedLicense) {
        (async () => {
            const status = await validateLicense(savedLicense);
            if (status === 'valid') {
                isLicensed = true;
                if (demoInfoText) demoInfoText.style.display = 'none';
                if (licenseInput) {
                    licenseInput.value = 'License Active';
                    licenseInput.disabled = true;
                    licenseInput.style.opacity = '0.5';
                    licenseInput.style.cursor = 'not-allowed';
                }
                if (licenseBadge) {
                    licenseBadge.textContent = 'Licensed';
                    licenseBadge.style.color = 'rgba(100, 255, 150, 0.4)';
                }
                console.log('[DEBUG] Valid license verified on startup');
            } else if (status === 'invalid') {
                // Only clear if backend explicitly says invalid (not when unreachable)
                console.log('[DEBUG] License explicitly invalid - clearing');
                localStorage.removeItem('valid_license_key');
                if (licenseBadge) {
                    licenseBadge.textContent = 'Demo';
                    licenseBadge.style.color = 'rgba(255, 200, 100, 0.4)';
                }
                if (demoInfoText) demoInfoText.style.display = 'block';
            } else {
                // Backend unreachable ('empty') - preserve license, assume still valid
                console.log('[DEBUG] Backend not ready yet - preserving saved license');
                isLicensed = true;
                if (demoInfoText) demoInfoText.style.display = 'none';
                if (licenseInput) {
                    licenseInput.value = 'License Active';
                    licenseInput.disabled = true;
                    licenseInput.style.opacity = '0.5';
                    licenseInput.style.cursor = 'not-allowed';
                }
                if (licenseBadge) {
                    licenseBadge.textContent = 'Licensed';
                    licenseBadge.style.color = 'rgba(100, 255, 150, 0.4)';
                }
            }
        })();
    } else {
        // Show Unlicensed badge
        if (licenseBadge) {
            licenseBadge.textContent = 'Demo';
            licenseBadge.style.color = 'rgba(255, 200, 100, 0.4)';
        }
        if (demoInfoText) demoInfoText.style.display = 'block';
    }

    const endBtn = document.getElementById('btn-session-end');
    const startTimerBtn = document.getElementById('btn-session-start');
    const stopTimerBtn = document.getElementById('btn-session-stop');

    // Overlay is visible by default - waiting for session creation
    console.log('[DEBUG] initSession: startBtn found?', !!startBtn);
    if (startBtn) {
        startBtn.onclick = handleCreateSession;
        console.log('[DEBUG] initSession: onclick handler attached to Start Session button');
    } else {
        console.error('[DEBUG] initSession: btn-start-session NOT FOUND!');
    }

    if (endBtn) {
        endBtn.onclick = endSession;
    }

    if (startTimerBtn) {
        startTimerBtn.onclick = startSessionTimer;
    }

    if (stopTimerBtn) {
        stopTimerBtn.onclick = stopSessionTimer;
    }

    // Past Sessions button and modal
    const pastSessionsBtn = document.getElementById('btn-past-sessions');
    const pastSessionsModal = document.getElementById('past-sessions-modal');
    const closePastSessions = document.getElementById('close-past-sessions');

    if (pastSessionsBtn) {
        pastSessionsBtn.onclick = async () => {
            // Block if backend isn't ready yet
            if (!backendReady) {
                const errorPopup = document.getElementById('session-error-popup');
                if (errorPopup) {
                    errorPopup.textContent = 'Backend is still starting up, please wait...';
                    errorPopup.style.display = 'block';
                    errorPopup.style.opacity = '1';
                    setTimeout(() => {
                        errorPopup.style.opacity = '0';
                        setTimeout(() => errorPopup.style.display = 'none', 200);
                    }, 3000);
                }
                return;
            }

            pastSessionsModal.style.display = 'flex';
            const listContainer = document.getElementById('past-sessions-list');
            listContainer.innerHTML = '<div style="color: rgba(255,255,255,0.4); font-size: 12px; text-align: center; padding: 20px;">Loading...</div>';

            try {
                const res = await fetch('http://127.0.0.1:5050/sessions');
                const data = await res.json();

                if (data.sessions && data.sessions.length > 0) {
                    // Backend already sorts sessions by newest first
                    const sorted = data.sessions;
                    listContainer.innerHTML = sorted.map(session => {
                        // Format the timestamp nicely
                        let formattedDate = session.created_at || 'No date';
                        if (session.created_at) {
                            try {
                                const d = new Date(session.created_at);
                                if (!isNaN(d.getTime())) {
                                    formattedDate = d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' }) + ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
                                }
                            } catch (e) { /* keep original */ }
                        }
                        return `
                        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; padding: 12px; transition: all 0.2s; display: flex; justify-content: space-between; align-items: center;" 
                             onmouseover="this.style.background='rgba(255,255,255,0.06)'" 
                             onmouseout="this.style.background='rgba(255,255,255,0.03)'">
                            <div style="flex: 1; cursor: pointer;" onclick="window.openPastSession('${session.name.replace(/'/g, "\\'")}')"> 
                                <div style="color: rgba(255,255,255,0.8); font-size: 13px; margin-bottom: 4px;">${session.name} ${session.target_role ? `<span style="font-size: 11px; color: rgba(255,255,255,0.4);">(${session.target_role})</span>` : ''}</div>
                                <div style="color: rgba(255,255,255,0.4); font-size: 10px;">${formattedDate}</div>
                                <div style="color: rgba(255,255,255,0.3); font-size: 10px; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${session.job_description_preview || ''}</div>
                            </div>
                            <button onclick="event.stopPropagation(); window.deletePastSession('${session.name.replace(/'/g, "\\\\'")}')" 
                                    style="background: none; border: 1px solid rgba(255,255,255,0.08); border-radius: 3px; cursor: pointer; padding: 4px 8px; margin-left: 8px; transition: all 0.2s; font-size: 9px; color: rgba(255,255,255,0.3); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500;"
                                    onmouseover="this.style.color='#ff5555'; this.style.borderColor='rgba(255,68,68,0.3)'; this.style.background='rgba(255,68,68,0.08)';"
                                    onmouseout="this.style.color='rgba(255,255,255,0.3)'; this.style.borderColor='rgba(255,255,255,0.08)'; this.style.background='none';"
                                    title="Delete session">TRASH</button>
                        </div>
                    `;
                    }).join('');
                } else {
                    listContainer.innerHTML = '<div style="color: rgba(255,255,255,0.4); font-size: 12px; text-align: center; padding: 20px;">No past sessions found</div>';
                }
            } catch (e) {
                listContainer.innerHTML = '<div style="color: rgba(255, 107, 107, 0.5); font-size: 12px; text-align: center; padding: 20px;">Error loading sessions. Is backend running?</div>';
            }
        };
    }

    if (closePastSessions) {
        closePastSessions.onclick = () => {
            pastSessionsModal.style.display = 'none';
        };
    }

    // Close modal when clicking outside
    if (pastSessionsModal) {
        pastSessionsModal.onclick = (e) => {
            if (e.target === pastSessionsModal) {
                pastSessionsModal.style.display = 'none';
            }
        };
    }

    // Guide button and modal
    const guideBtn = document.getElementById('btn-guide');
    const guideModal = document.getElementById('guide-modal');
    const closeGuide = document.getElementById('close-guide');

    if (guideBtn) {
        guideBtn.onclick = () => {
            guideModal.style.display = 'flex';
        };
    }

    if (closeGuide) {
        closeGuide.onclick = () => {
            guideModal.style.display = 'none';
        };
    }

    // Close guide modal when clicking outside
    if (guideModal) {
        guideModal.onclick = (e) => {
            if (e.target === guideModal) {
                guideModal.style.display = 'none';
            }
        };
    }

    // Hotkeys button and modal
    const hotkeysBtn = document.getElementById('btn-hotkeys-setup');
    const hotkeysModal = document.getElementById('hotkeys-modal');
    const closeHotkeys = document.getElementById('close-hotkeys');

    if (hotkeysBtn) {
        hotkeysBtn.onclick = () => {
            hotkeysModal.style.display = 'flex';
        };
    }

    if (closeHotkeys) {
        closeHotkeys.onclick = () => {
            hotkeysModal.style.display = 'none';
        };
    }

    // Close hotkeys modal when clicking outside
    if (hotkeysModal) {
        hotkeysModal.onclick = (e) => {
            if (e.target === hotkeysModal) {
                hotkeysModal.style.display = 'none';
            }
        };
    }

    // Conversation So Far floating window toggle
    const convoBtn = document.getElementById('btn-conversation');

    if (convoBtn) {
        convoBtn.onclick = () => {
            ipcRenderer.send('toggle-convo-window');
        };
    }

    // API Key info click handler
    const apikeyInfo = document.getElementById('apikey-info');
    if (apikeyInfo) {
        apikeyInfo.onclick = () => {
            customAlert('You need your own OpenAI API key to use this app.\n\n' +
                'HOW TO GET ONE:\n' +
                '1. Go to <a href="https://platform.openai.com" target="_blank" style="color: rgba(100, 255, 150, 0.9);">platform.openai.com</a>\n' +
                '2. Sign up or log in\n' +
                '3. Go to API Keys section\n' +
                '4. Create a new secret key (starts with sk-)\n\n' +
                'WHY THIS IS CHEAP:\n' +
                'Similar interview apps charge $30-100/month.\n' +
                'With your own API key, you pay only for what you use!\n\n' +
                'EXAMPLE COST:\n' +
                '- 50 AI responses = $0.15 - $0.30\n' +
                '- Full 2-hour interview = $0.50 - $1.00\n' +
                '- That is 10-100x cheaper than competitors!\n\n' +
                'Add $5-10 credit to start. It lasts for many interviews.');
        };
    }

    // License info click handler
    const licenseInfo = document.getElementById('license-info');
    if (licenseInfo) {
        licenseInfo.onclick = async () => {
            await customAlert(
                `Get a license key for full 2-hour sessions.\n\n` +
                `Email your Hardware ID to: <a href="mailto:mjulez70@gmail.com" style="color: rgba(100, 255, 150, 0.9);">mjulez70@gmail.com</a>\n\n` +
                `Your Hardware ID (HWID) is found below the license key input field.\n\n` +
                `One-time payment of $20 only.\n` +
                `CashApp: <a href="https://cash.app/$passdpawn" target="_blank" style="color: rgba(100, 255, 150, 0.9); text-decoration: underline;">$passdpawn</a>\n` +
                `PayPal: <a href="https://paypal.me/passdpawn" target="_blank" style="color: rgba(100, 255, 150, 0.9); text-decoration: underline;">paypal.me/passdpawn</a>`
            );
        };
    }


}

// Load and show history for a past session
window.openPastSession = async function (sessionName) {
    const pastSessionsModal = document.getElementById('past-sessions-modal');
    const apiKeyInput = document.getElementById('setup-apikey');
    const status = document.getElementById('setup-status');

    if (pastSessionsModal) pastSessionsModal.style.display = 'none';

    try {
        const apiKey = apiKeyInput ? apiKeyInput.value.trim() : '';
        if (!apiKey) {
            status.innerText = 'Enter your OpenAI API Key first, then select a past session.';
            status.style.color = 'rgba(255, 107, 107, 0.5)';
            if (apiKeyInput) apiKeyInput.focus();
            return;
        }

        status.innerText = 'Validating API key...';
        status.style.color = 'rgba(100, 255, 150, 0.4)';

        const validateRes = await fetch('http://127.0.0.1:5050/validate-api-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey })
        });
        const validateData = await validateRes.json();

        if (!validateData.valid) {
            status.innerText = validateData.error || 'Invalid API key';
            status.style.color = 'rgba(255, 107, 107, 0.5)';
            return;
        }

        // Check license
        const savedLicense = localStorage.getItem('valid_license_key');
        if (savedLicense) {
            isLicensed = true;
        } else {
            const licenseInput = document.getElementById('setup-license');
            const licenseKey = licenseInput ? licenseInput.value.trim() : '';
            const licenseStatus = await validateLicense(licenseKey);
            isLicensed = (licenseStatus === 'valid');
        }

        const demoInfoText = document.getElementById('demo-info-text');
        if (isLicensed && demoInfoText) demoInfoText.style.display = 'none';

        // Apply demo cooldown check for unlicensed users
        if (!isLicensed) {
            const remainingMs = getRemainingDemoCooldown();
            if (remainingMs > 0) {
                const timeStr = formatCooldownTime(remainingMs);
                status.innerText = `Demo cooldown active. Try again in ${timeStr}.`;
                status.style.color = "rgba(255, 107, 107, 0.5)";
                return;
            }
        }

        SESSION_DURATION_MS = isLicensed ? FULL_SESSION_DURATION_MS : DEMO_SESSION_DURATION_MS;

        // Load session data from backend
        status.innerText = 'Loading session...';
        status.style.color = 'rgba(100, 255, 150, 0.4)';
        const loadRes = await fetch(`http://127.0.0.1:5050/session/load/${encodeURIComponent(sessionName)}`);
        const sessionData = await loadRes.json();

        if (sessionData.status !== 'ok') {
            status.innerText = sessionData.error || 'Failed to load session';
            status.style.color = 'rgba(255, 107, 107, 0.5)';
            return;
        }

        status.innerText = '';

        // === SHOW HISTORY MODAL ===
        const historyModal = document.getElementById('session-history-modal');
        const historyList = document.getElementById('session-history-list');
        const historyTitle = document.getElementById('session-history-title');

        if (historyTitle) historyTitle.innerHTML = `History — ${sessionName} ${sessionData.target_role ? '<span style="color: rgba(255,255,255,0.4);">(' + sessionData.target_role + ')</span>' : ''}`;
        if (historyList) historyList.innerHTML = '';

        // Populate history entries
        let lastHistoryDateStr = '';
        if (sessionData.history && Array.isArray(sessionData.history) && sessionData.history.length > 0) {
            sessionData.history.forEach((entry, idx) => {
                // Insert date separator if date changes (date only, no time)
                if (entry.timestamp) {
                    try {
                        const d = new Date(entry.timestamp);
                        const dayStr = d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' });
                        if (dayStr !== lastHistoryDateStr) {
                            lastHistoryDateStr = dayStr;
                            const separator = document.createElement('div');
                            separator.style.cssText = 'text-align: center; padding: 6px 0; margin: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.06);';
                            separator.innerHTML = '<span style="color: rgba(255,255,255,0.6); font-size: 10px; letter-spacing: 1px; font-weight: 500;">' + dayStr + '</span>';
                            historyList.appendChild(separator);
                        }
                    } catch (e) { /* skip separator */ }
                }

                const pairDiv = document.createElement('div');
                pairDiv.style.cssText = 'margin-bottom: 14px;';

                const entryTimeStr = entry.timestamp
                    ? new Date(entry.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
                    : '';

                // ── USER BUBBLE (right-aligned) ──────────────────────────────
                if (entry.question) {
                    const userRow = document.createElement('div');
                    userRow.style.cssText = 'display: flex; justify-content: flex-end; margin-bottom: 6px;';
                    const userBubble = document.createElement('div');
                    userBubble.style.cssText = [
                        'max-width: 75%; background: rgba(60,60,70,0.7);',
                        'border: 1px solid rgba(255,255,255,0.08); border-radius: 14px 14px 3px 14px;',
                        'padding: 8px 12px; font-size: 11px; color: rgba(255,255,255,0.75); line-height: 1.5;',
                        'word-break: break-word;'
                    ].join('');
                    const isScreenEntry = entry.question.startsWith('[USER SHARED A SCREENSHOT]');
                    const displayQ = isScreenEntry
                        ? entry.question.replace('[USER SHARED A SCREENSHOT] Question about the screenshot: ', '').trim() || '<em style="color:rgba(255,255,255,0.35);">screen only</em>'
                        : (window.formatConvoText ? window.formatConvoText(entry.question) : entry.question);
                    const screenLabel = isScreenEntry ? '📷 SCREEN · ' : '';
                    userBubble.innerHTML = `<div style="font-size:9px;color:rgba(255,255,255,0.3);margin-bottom:3px;letter-spacing:0.5px;">${screenLabel}${entryTimeStr}</div>${displayQ}`;
                    userBubble.querySelectorAll('pre code').forEach(b => { if (typeof hljs !== 'undefined') hljs.highlightElement(b); });
                    userRow.appendChild(userBubble);
                    pairDiv.appendChild(userRow);
                }

                // ── AI BUBBLE (left-aligned) with [copy] header + stats footer ──
                if (entry.response) {
                    const aiRow = document.createElement('div');
                    aiRow.style.cssText = 'display: flex; justify-content: flex-start; margin-bottom: 5px;';
                    const aiBubble = document.createElement('div');
                    aiBubble.style.cssText = [
                        'max-width: 80%; background: rgba(30,40,35,0.7);',
                        'border: 1px solid rgba(100,255,150,0.12); border-radius: 14px 14px 14px 3px;',
                        'padding: 8px 12px; font-size: 11px; color: rgba(220,240,225,0.85); line-height: 1.5;',
                        'word-break: break-word; max-height: 300px; overflow-y: auto;',
                        'display: flex; flex-direction: column; gap: 6px;'
                    ].join('');

                    const modelLabel = entry.model ? entry.model.toUpperCase() : 'AI';

                    // Header: model · time + [copy]
                    const aiHeader = document.createElement('div');
                    aiHeader.style.cssText = 'display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;';
                    const responseText = entry.response;
                    aiHeader.innerHTML = `
                        <span style="font-size:9px;color:rgba(100,255,150,0.4);letter-spacing:0.5px;">${modelLabel} · ${entryTimeStr}</span>
                        <span style="font-size:9px;color:rgba(255,255,255,0.25);font-family:monospace;cursor:pointer;padding:1px 5px;border-radius:3px;border:1px solid rgba(255,255,255,0.08);transition:all 0.15s;"
                              onmouseover="this.style.color='#fff';this.style.borderColor='rgba(255,255,255,0.25)';"
                              onmouseout="this.style.color='rgba(255,255,255,0.25)';this.style.borderColor='rgba(255,255,255,0.08)';"
                              onclick="navigator.clipboard.writeText(this.closest('div').nextSibling.innerText);this.textContent='copied!';setTimeout(()=>this.textContent='[copy]',2000);">[copy]</span>`;

                    // Body
                    const aiBody = document.createElement('div');
                    aiBody.className = 'ai-body';
                    aiBody.style.cssText = 'flex: 1; min-height: 0;';
                    aiBody.innerHTML = window.formatConvoText ? window.formatConvoText(entry.response) : entry.response;
                    aiBody.querySelectorAll('pre code').forEach(b => { if (typeof hljs !== 'undefined') hljs.highlightElement(b); });

                    // Footer stats
                    const aiFooter = document.createElement('div');
                    aiFooter.style.cssText = 'display: flex; flex-wrap: wrap; gap: 6px; font-size: 9px; font-family: monospace; color: rgba(255,255,255,0.2); letter-spacing: 0.3px; padding-top: 5px; border-top: 1px solid rgba(100,255,150,0.07); flex-shrink: 0;';
                    const statsItems = [];
                    if (entry.response_time) statsItems.push(`TTFT <span style="color:rgba(180,220,200,0.6)">${parseFloat(entry.response_time).toFixed(1)}s</span>`);
                    if (entry.total_time) statsItems.push(`TT <span style="color:rgba(180,220,200,0.6)">${parseFloat(entry.total_time).toFixed(1)}s</span>`);
                    if (entry.input_tokens) statsItems.push(`IN <span style="color:rgba(180,180,180,0.4)">${Number(entry.input_tokens).toLocaleString()}</span>`);
                    if (entry.output_tokens) statsItems.push(`OUT <span style="color:rgba(180,180,180,0.4)">${Number(entry.output_tokens).toLocaleString()}</span>`);
                    if (entry.cost) statsItems.push(`<span style="color:rgba(180,180,180,0.35)">${entry.cost < 1 ? (entry.cost * 100).toFixed(3) + '¢' : '$' + entry.cost.toFixed(3)}</span>`);
                    aiFooter.innerHTML = statsItems.length > 0
                        ? statsItems.join('<span style="opacity:0.25"> · </span>')
                        : '<span style="opacity:0.3">no stats</span>';

                    aiBubble.appendChild(aiHeader);
                    aiBubble.appendChild(aiBody);
                    aiBubble.appendChild(aiFooter);
                    aiRow.appendChild(aiBubble);
                    pairDiv.appendChild(aiRow);
                }

                historyList.appendChild(pairDiv);
            });
        } else {
            const emptyDiv = document.createElement('div');
            emptyDiv.style.cssText = 'color: rgba(255,255,255,0.3); font-size: 12px; text-align: center; padding: 30px;';
            emptyDiv.textContent = 'No conversation history for this session.';
            historyList.appendChild(emptyDiv);
        }

        // Show the modal
        if (historyModal) historyModal.style.display = 'flex';

        // === WIRE UP BUTTONS ===
        const resumeBtn = document.getElementById('btn-resume-session');
        const closeHistoryBtn = document.getElementById('btn-close-history');
        const closeXBtn = document.getElementById('close-session-history');

        // Close handler (shared)
        const closeModal = () => {
            if (historyModal) historyModal.style.display = 'none';
        };

        if (closeHistoryBtn) closeHistoryBtn.onclick = closeModal;
        if (closeXBtn) closeXBtn.onclick = closeModal;

        // Resume handler
        if (resumeBtn) {
            resumeBtn.onclick = async () => {
                closeModal();

                // Set session as active
                currentSessionName = sessionName;
                sessionCreated = true;
                window.sessionTargetRole = sessionData.target_role || '';
                window.sessionTargetLanguage = sessionData.target_language || '';

                // Restore model preference
                if (sessionData.text_model) {
                    window.selectedModel = sessionData.text_model;
                    const modelBtn = document.getElementById('model-selector-btn');
                    if (modelBtn) {
                        const modelOpt = document.querySelector(`[data-model="${sessionData.text_model}"]`);
                        if (modelOpt) {
                            modelBtn.textContent = modelOpt.querySelector('div').textContent;
                        } else {
                            modelBtn.textContent = sessionData.text_model.replace('gpt-', 'GPT-').replace('-turbo', '');
                        }
                    }
                    console.log('[SESSION] Restored model:', sessionData.text_model);
                }

                // Reset status bar metrics for the resumed session logic
                const apiInEl = document.getElementById('api-usage-input');
                const apiOutEl = document.getElementById('api-usage-output');
                const apiCostEl = document.getElementById('api-cost');
                if (apiInEl) apiInEl.innerText = '0';
                if (apiOutEl) apiOutEl.innerText = '0';
                if (apiCostEl) {
                    apiCostEl.innerText = '$0.00';
                    apiCostEl.style.color = 'rgba(120, 200, 180, 0.85)';
                }

                // Update license badge
                const badge = document.getElementById('license-status-badge');
                if (badge) {
                    if (isLicensed) {
                        badge.textContent = 'LICENSED';
                        badge.style.color = 'rgba(100, 255, 150, 0.8)';
                    } else {
                        badge.textContent = 'Demo';
                        badge.style.color = 'rgba(255, 200, 100, 0.7)';
                    }
                }

                // Update timer
                const timerText = document.getElementById('session-timer-text');
                if (timerText) {
                    timerText.innerText = isLicensed ? '2:00:00' : '0:12:00';
                }

                const statusText = document.getElementById('status-text');
                const statusDot = document.getElementById('status-dot');
                if (statusText) {
                    statusText.innerText = 'Session Ready - Click Start';
                }
                if (statusDot) {
                    statusDot.className = 'dot';
                }

                // Hide setup overlay and reset end button state
                const overlay = document.getElementById('setup-overlay');
                if (overlay) overlay.style.display = 'none';
                const endBtnEl = document.getElementById('btn-session-end');
                if (endBtnEl) endBtnEl.classList.remove('ended');

                // Reset response time display
                const responseTimeEl = document.getElementById('response-time');
                if (responseTimeEl) responseTimeEl.innerText = '0.0s';

                // Pre-populate Conversation So Far floating window with past session history
                ipcRenderer.send('load-convo-history', {
                    sessionName: sessionName,
                    role: sessionData.target_role || '',
                    historyArray: sessionData.history || []
                });

                // Check for disclaimer agreement before resuming
                const agreed = localStorage.getItem('disclaimer_agreed') === 'true';
                if (!agreed) {
                    await customAlert("You must agree to the Terms & Ethical Usage Policy before resuming a session.");
                    const overlay = document.getElementById('setup-overlay');
                    if (overlay) overlay.style.display = 'flex';
                    const pastModal = document.getElementById('past-sessions-modal');
                    if (pastModal) pastModal.style.display = 'none';
                    return;
                }

                console.log(`[SESSION] Resumed past session: ${sessionName}`);
            };
        }

    } catch (e) {
        console.error('Error loading past session:', e);
        status.innerText = 'Error loading session. Is backend running?';
        status.style.color = 'rgba(255, 107, 107, 0.5)';
        const statusDot = document.getElementById('status-dot');
        if (statusDot) statusDot.className = 'dot error';
    }
};

// Delete past session function  
window.deletePastSession = async function (sessionName) {
    const confirmed = await customConfirm(`Delete session "${sessionName}"?\n\nThis cannot be undone.`);

    if (!confirmed) return;

    try {
        const res = await fetch(`http://127.0.0.1:5050/session/delete/${encodeURIComponent(sessionName)}`, {
            method: 'DELETE'
        });
        const data = await res.json();

        if (data.status === 'ok') {
            const pastSessionsBtn = document.getElementById('btn-past-sessions');
            if (pastSessionsBtn) {
                pastSessionsBtn.click(); // Refresh list
            }
        } else {
            await customAlert(`Failed to delete session:\n${data.error || 'Unknown error'}`);
        }
    } catch (e) {
        console.error('Error deleting session:', e);
        await customAlert(`Error deleting session:\n${e.message}`);
    }
};

async function handleCreateSession() {
    console.log('[DEBUG] Start Session button clicked!');
    const sessionNameInput = document.getElementById('setup-session-name');
    const fileInput = document.getElementById('setup-resume');
    const apiKeyInput = document.getElementById('setup-apikey');
    const jdInput = document.getElementById('setup-jobdesc');
    const status = document.getElementById('setup-status');
    const startBtn = document.getElementById('btn-start-session');

    // Validate session name
    const sessionName = sessionNameInput ? sessionNameInput.value.trim() : '';
    console.log('[DEBUG] Session name:', sessionName);

    // Helper to show validation status
    function showStatus(msg, isError = true) {
        if (status) {
            status.innerText = msg;
            status.style.color = isError ? "rgba(255, 107, 107, 0.5)" : "rgba(100, 255, 150, 0.4)";
        }
    }

    if (!sessionName) {
        showStatus('Session name is required');
        return;
    }

    // Validate disclaimer agreement
    const disclaimerCheck = document.getElementById('setup-disclaimer-agree');
    if (disclaimerCheck && !disclaimerCheck.checked) {
        showStatus('You must agree to the Terms & Ethical Usage Policy first');
        return;
    }

    // Persist agreement
    localStorage.setItem('disclaimer_agreed', 'true');

    // Sanitize session name (remove invalid folder characters)
    const sanitizedSessionName = sessionName.replace(/[<>:"/\\|?*]/g, '_');

    if (!fileInput.files || fileInput.files.length === 0) {
        showStatus('Resume is required');
        return;
    }

    const apiKey = apiKeyInput ? apiKeyInput.value.trim() : '';
    if (!apiKey) {
        showStatus('API key is required');
        return;
    }

    const roleInput = document.getElementById('setup-role');
    const targetRole = roleInput ? roleInput.value.trim() : '';
    if (!targetRole) {
        showStatus('Target Role is required');
        return;
    }

    const langInput = document.getElementById('setup-language');
    let targetLang = langInput ? langInput.value.trim() : '';
    if (!targetLang) {
        showStatus('Output Language is required');
        return;
    }

    // Default invalid output languages to Python
    const validLangs = ['python', 'java', 'c++', 'cpp', 'c#', 'csharp', 'javascript', 'js', 'typescript', 'ts', 'go', 'golang', 'ruby', 'php', 'swift', 'kotlin', 'rust', 'sql', 'bash', 'shell'];
    if (!validLangs.includes(targetLang.toLowerCase())) {
        console.log(`[DEBUG] Unknown target language "${targetLang}". Defaulting to Python.`);
        targetLang = 'Python';
        if (langInput) langInput.value = 'Python';
    }

    // Save globals for this session
    window.sessionTargetRole = targetRole;
    window.sessionTargetLanguage = targetLang;
    localStorage.setItem('target_role', targetRole);
    localStorage.setItem('target_language', targetLang);

    if (!jdInput.value.trim()) {
        showStatus('Job Description is required');
        return;
    }

    // Validate license
    const licenseInput = document.getElementById('setup-license');
    const savedLicense = localStorage.getItem('valid_license_key');

    // If license is already saved and validated, skip validation
    if (savedLicense) {
        isLicensed = true;
        SESSION_DURATION_MS = FULL_SESSION_DURATION_MS;
        console.log('[DEBUG] Using saved license - Full 2-hour session');
        showStatus("License validated - Full session", false);
    } else {
        // No saved license - check what user entered
        const licenseKey = licenseInput ? licenseInput.value.trim() : '';
        console.log('[DEBUG] License key:', licenseKey ? '(provided)' : '(empty)');
        const licenseStatus = await validateLicense(licenseKey);
        console.log('[DEBUG] License status:', licenseStatus);

        if (licenseKey && licenseStatus === 'invalid') {
            // User entered something but it's wrong - show error and stop
            showStatus("Please enter a valid license key");
            return;
        }

        // Set session duration based on license
        if (licenseStatus === 'valid') {
            isLicensed = true;
            SESSION_DURATION_MS = FULL_SESSION_DURATION_MS;
            console.log('[DEBUG] Licensed: Full 2-hour session');
            // Save valid license to localStorage - never ask again
            localStorage.setItem('valid_license_key', licenseKey);
            showStatus("License validated - Full session", false);
            const demoInfoText = document.getElementById('demo-info-text');
            if (demoInfoText) demoInfoText.style.display = 'none';
        } else {
            // Demo mode - no license provided
            // Check for demo cooldown
            const remainingMs = getRemainingDemoCooldown();
            if (remainingMs > 0) {
                const timeStr = formatCooldownTime(remainingMs);
                showStatus(`Demo cooldown active. Try again in ${timeStr}.`);
                return;
            }

            isLicensed = false;
            SESSION_DURATION_MS = DEMO_SESSION_DURATION_MS;
            console.log('Demo: 12-minute session');
            showStatus("Demo: 12-minute session", false);
            if (status) status.style.color = "rgba(228, 147, 61, 0.6)"; // Muted orange for demo
        }
    }

    // Small delay so user sees the license status
    await new Promise(resolve => setTimeout(resolve, 500));

    try {
        startBtn.disabled = true;
        if (status) status.style.color = "#aaa";

        // 0. Create session folder first
        showStatus("Creating session...", false);
        const createSessionRes = await fetch('http://127.0.0.1:5050/session/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_name: sanitizedSessionName })
        });
        const createSessionJson = await createSessionRes.json();

        if (createSessionJson.status !== 'ok') {
            throw new Error(createSessionJson.error || "Failed to create session");
        }

        currentSessionName = sanitizedSessionName;

        // 1. Validate API Key
        status.innerText = "Validating API key...";
        status.style.color = "#aaa"; // Neutral during validation
        const validateRes = await fetch('http://127.0.0.1:5050/validate-api-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey })
        });
        const validateJson = await validateRes.json();

        if (!validateJson.valid) {
            throw new Error(validateJson.error || "Invalid API key");
        }
        status.style.color = "rgba(100, 255, 150, 0.4)"; // Green only after success

        // 2. Upload Resume (to session folder)
        status.innerText = "Uploading resume...";
        const fd = new FormData();
        fd.append('file', fileInput.files[0]);
        fd.append('session_name', sanitizedSessionName);

        const upRes = await fetch('http://127.0.0.1:5050/session/resume', { method: 'POST', body: fd });
        const upJson = await upRes.json();

        if (upJson.status !== 'ok') {
            throw new Error("Resume upload failed: " + (upJson.error || 'Unknown error'));
        }

        // 3. Save session data (job description, api key, etc.)
        status.innerText = "Saving session data...";
        const sessionData = {
            session_name: sanitizedSessionName,
            openai_api_key: apiKey,
            job_description: jdInput.value.trim(),
            resume_text: upJson.resume_text || '',
            target_role: targetRole,
            target_language: targetLang,
            created_at: new Date().toISOString()
        };

        const saveRes = await fetch('http://127.0.0.1:5050/session/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sessionData)
        });

        const saveJson = await saveRes.json();
        if (saveJson.status !== 'ok') {
            throw new Error("Session save failed: " + (saveJson.error || 'Unknown error'));
        }

        // 4. Session created - hide overlay
        sessionCreated = true;
        status.innerText = isLicensed ? "Session created!" : "Demo session created (12 min)";
        status.style.color = "rgba(100, 255, 150, 0.4)";

        // Update timer display to show correct duration
        const timerText = document.getElementById('session-timer-text');
        if (timerText) {
            if (isLicensed) {
                timerText.innerText = '2:00:00';
            } else {
                timerText.innerText = '0:12:00';
            }
        }

        setTimeout(() => {
            const overlay = document.getElementById('setup-overlay');
            overlay.style.display = 'none';
            // Clear conversation area for fresh sessions
            const convoArea = document.getElementById('conversation-area');
            if (convoArea) convoArea.innerHTML = '';
            // Reset end button state
            const endBtnEl = document.getElementById('btn-session-end');
            if (endBtnEl) endBtnEl.classList.remove('ended');

            // Reset API cost display
            const apiCostEl = document.getElementById('api-cost');
            if (apiCostEl) {
                apiCostEl.innerText = '$0.00';
                apiCostEl.style.color = 'rgba(120, 200, 180, 0.85)';
            }
            // Reset response time display
            const responseTimeEl = document.getElementById('response-time');
            if (responseTimeEl) responseTimeEl.innerText = '0.0s';
        }, 1200);

    } catch (e) {
        console.error('Session Creation Error:', e);
        status.innerText = `Error: ${e.message}`;
        status.style.color = "rgba(255, 107, 107, 0.5)";
        startBtn.disabled = false;
        startBtn.style.opacity = '1';
    }
}

async function startSessionTimer() {
    if (!sessionCreated) {
        window.showSessionError();
        return;
    }

    const timerText = document.getElementById('session-timer-text');
    const startBtn = document.getElementById('btn-session-start');
    const stopBtn = document.getElementById('btn-session-stop');
    const endBtn = document.getElementById('btn-session-end');
    const statusText = document.getElementById('status-text');
    const statusDot = document.getElementById('status-dot');

    if (timerInterval) {
        // Already running
        return;
    }

    // Ping backend to ensure it's still alive before fully starting the session
    try {
        const pingRes = await fetch('http://127.0.0.1:5050/usage', { method: 'GET' });
        if (!pingRes.ok) throw new Error("Backend offline");
    } catch (e) {
        console.error('Backend connection error when starting session:', e);
        customAlert('Cannot connect to backend server. Make sure the Interview Assistant backend is running.');
        if (statusText) statusText.innerText = 'Backend Error';
        if (statusDot) statusDot.className = 'dot error';
        return;
    }

    sessionEndTime = Date.now() + SESSION_DURATION_MS;
    sessionStartTimestamp = Date.now(); // Track start time for duration calculation
    window.isSessionActive = true;

    // Update button states
    startBtn.classList.add('active');
    stopBtn.classList.remove('paused');
    if (endBtn) endBtn.classList.remove('ended');
    statusText.innerText = isLicensed ? 'Session Running' : 'Demo (12 mins)';
    if (statusDot) statusDot.className = 'dot connected';

    timerInterval = setInterval(() => {
        const remaining = sessionEndTime - Date.now();

        if (remaining <= 0) {
            clearInterval(timerInterval);
            timerInterval = null;

            // 5-minute Demo and 2-hour Licensed sessions both expire here.
            resetSessionUI();

            if (isLicensed) {
                customAlert('Session time expired! (2 hours)\n\nThe current session has been closed. Please create a new session.');
                const statusText = document.getElementById('status-text');
                if (statusText) statusText.innerText = 'Session Expired';
            } else {
                // Demo expired - show license prompt
                showLicensePrompt();
                const statusText = document.getElementById('status-text');
                if (statusText) statusText.innerText = 'Demo Expired';
            }
            return;
        }
        const hours = Math.floor(remaining / (1000 * 60 * 60));
        const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((remaining % (1000 * 60)) / 1000);

        const timeStr = `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        timerText.innerText = timeStr;

        // Timer color: green(normal) → yellow(last 30 min) → red(last 10 min)
        const timerBox = document.getElementById('session-timer');
        const thirtyMin = 30 * 60 * 1000;
        const tenMin = 10 * 60 * 1000;
        if (timerBox) {
            if (remaining <= tenMin) {
                // Critical: last 10 minutes — red glow
                timerBox.style.color = 'rgba(255, 107, 107, 1)'; // Solid subtle red for readability
                timerBox.style.borderColor = 'rgba(255, 68, 68, 0.5)';
                timerBox.style.background = 'rgba(255, 50, 50, 0.1)';
                timerBox.style.boxShadow = '0 0 12px rgba(255, 50, 50, 0.25)';
            } else if (remaining <= thirtyMin) {
                // Warning: last 30 minutes — yellow
                timerBox.style.color = '#f0c040';
                timerBox.style.borderColor = 'rgba(240, 192, 64, 0.4)';
                timerBox.style.background = 'rgba(240, 192, 64, 0.06)';
                timerBox.style.boxShadow = '0 0 8px rgba(240, 192, 64, 0.15)';
            } else {
                // Normal: green / cyan
                timerBox.style.color = '#00e6c8';
                timerBox.style.borderColor = 'rgba(0, 230, 200, 0.3)';
                timerBox.style.background = 'rgba(0, 230, 200, 0.05)';
                timerBox.style.boxShadow = '0 0 6px rgba(0, 230, 200, 0.1)';
            }
        }

    }, 1000);
}

function stopSessionTimer() {
    if (!sessionCreated) {
        window.showSessionError();
        return;
    }
    const startBtn = document.getElementById('btn-session-start');
    const stopBtn = document.getElementById('btn-session-stop');
    const statusText = document.getElementById('status-text');
    const statusDot = document.getElementById('status-dot');

    window.isSessionActive = false;

    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }

    // Update button states
    startBtn.classList.remove('active');
    stopBtn.classList.add('paused');
    statusText.innerText = 'Session Paused';
    if (statusDot) statusDot.className = 'dot';
}

function resetSessionUI() {
    // Reset usage for next session
    fetch('http://127.0.0.1:5050/usage/reset', { method: 'POST' }).catch(() => { });

    // Clear conversation history on backend
    fetch('http://127.0.0.1:5050/conversation/clear', { method: 'POST' }).catch(() => { });

    // Clear and hide floating conversation window when session ends
    ipcRenderer.send('clear-convo-history');
    ipcRenderer.send('hide-convo-window');

    // Get DOM elements
    const fileInput = document.getElementById('setup-resume');
    const apiKeyInput = document.getElementById('setup-apikey');
    const jdInput = document.getElementById('setup-jobdesc');
    const sessionNameInput = document.getElementById('setup-session-name');
    const status = document.getElementById('setup-status');
    const sessionStartBtn = document.getElementById('btn-start-session');
    const overlay = document.getElementById('setup-overlay');

    // Reset file input
    if (fileInput) {
        fileInput.value = '';
        fileInput.classList.remove('selected');
    }
    const detachBtn = document.getElementById('resume-detach-btn');
    if (detachBtn) detachBtn.style.display = 'none';

    // Reset filename display
    const resumeFilename = document.getElementById('resume-filename');
    if (resumeFilename) {
        resumeFilename.textContent = 'No file chosen';
        resumeFilename.style.color = 'rgba(255, 255, 255, 0.4)';
    }

    // Reset other inputs (keep API key from localStorage)
    if (sessionNameInput) sessionNameInput.value = '';
    if (apiKeyInput) {
        const savedKey = localStorage.getItem('openai_api_key');
        apiKeyInput.value = savedKey || '';
    }
    if (jdInput) jdInput.value = '';
    if (status) {
        status.innerText = '';
        status.style.color = '#aaa';
    }

    // Reset the start button to disabled state
    if (sessionStartBtn) {
        sessionStartBtn.disabled = false;
        sessionStartBtn.style.opacity = '0.5';
        sessionStartBtn.onclick = handleCreateSession;
        if (typeof checkAllInputs === 'function') checkAllInputs();
    }

    // Clear transcript, response, and conversation areas
    const transcriptArea = document.getElementById('transcript-area');
    const responseArea = document.getElementById('response-area');
    const conversationArea = document.getElementById('conversation-area');
    const modelBadge = document.querySelector('.model-signature');
    if (transcriptArea) transcriptArea.innerHTML = '';
    if (responseArea) responseArea.innerHTML = '';
    if (conversationArea) conversationArea.innerHTML = '';
    if (modelBadge) modelBadge.remove();

    // Reset timer display
    const timerText = document.getElementById('session-timer-text');
    if (timerText) timerText.innerText = '2:00:00';

    const timerBox = document.getElementById('session-timer');
    if (timerBox) {
        timerBox.style.color = 'rgba(255,255,255,0.8)';
        timerBox.style.borderColor = 'rgba(255,255,255,0.12)';
        timerBox.style.background = 'rgba(255,255,255,0.03)';
        timerBox.style.boxShadow = 'none';
    }

    // Reset session control buttons
    const startBtn = document.getElementById('btn-session-start');
    const stopBtn = document.getElementById('btn-session-stop');
    const endBtn = document.getElementById('btn-session-end');
    if (startBtn) startBtn.classList.remove('active');
    if (stopBtn) stopBtn.classList.remove('paused');
    if (endBtn) endBtn.classList.add('ended');

    // Reset status indicator
    const statusText = document.getElementById('status-text');
    const statusDot = document.getElementById('status-dot');
    if (statusText) statusText.innerText = 'Ready';
    if (statusDot) statusDot.className = 'dot';

    // Reset status bar metrics
    const ttftEl = document.getElementById('response-time-ttft');
    const ttEl = document.getElementById('response-time-tt');
    const costEl = document.getElementById('api-cost');
    if (ttftEl) ttftEl.innerText = '--s';
    if (ttEl) ttEl.innerText = '--s';
    if (costEl) costEl.innerText = '$0.00';

    // Reset session state variables
    window.isSessionActive = false;
    sessionCreated = false;
    sessionTimerStarted = false;
    currentSessionName = null;
    sessionEndTime = null;
    sessionStartTimestamp = null;

    // Show the setup overlay again and reset disclaimer only if not persistent
    if (overlay) {
        overlay.style.display = 'flex';
        const discCheck = document.getElementById('setup-disclaimer-agree');
        if (discCheck) {
            const alreadyAgreed = localStorage.getItem('disclaimer_agreed') === 'true';
            discCheck.checked = alreadyAgreed;
            discCheck.disabled = !alreadyAgreed;
        }
    }

    // Restore license badge if saved license exists
    const savedLicenseKey = localStorage.getItem('valid_license_key');
    const licenseBadge = document.getElementById('license-status-badge');
    if (savedLicenseKey && licenseBadge) {
        licenseBadge.textContent = 'Licensed';
        licenseBadge.style.color = 'rgba(100, 255, 150, 0.4)';
        const licInput = document.getElementById('setup-license');
        if (licInput) {
            licInput.value = 'License Active';
            licInput.disabled = true;
        }
        const demoInfoText = document.getElementById('demo-info-text');
        if (demoInfoText) demoInfoText.style.display = 'none';
    }

    // Set demo cooldown timestamp ONLY IF NOT LICENSED
    // This starts the 47-min timer exactly when the session ends
    if (!isLicensed) {
        localStorage.setItem('last_demo_timestamp', Date.now().toString());
        console.log('[DEBUG] Demo cooldown started');
    }
}

async function endSession() {
    if (!sessionCreated) return;

    if (await customConfirm("End current session and create a new one?")) {
        // Calculate session duration
        let sessionDuration = 'N/A';
        if (sessionStartTimestamp) {
            const durationMs = Date.now() - sessionStartTimestamp;
            const hours = Math.floor(durationMs / 3600000);
            const minutes = Math.floor((durationMs % 3600000) / 60000);
            const seconds = Math.floor((durationMs % 60000) / 1000);
            if (hours > 0) {
                sessionDuration = `${hours}h ${minutes}m ${seconds}s`;
            } else if (minutes > 0) {
                sessionDuration = `${minutes}m ${seconds}s`;
            } else {
                sessionDuration = `${seconds}s`;
            }
        }

        // Get API usage cost
        let apiCost = '$0.00';
        try {
            const usageRes = await fetch('http://127.0.0.1:5050/usage');
            if (usageRes.ok) {
                const usage = await usageRes.json();
                const costVal = usage.total_cost || 0;
                if (costVal < 1.00) {
                    apiCost = (costVal * 100).toFixed(2) + '¢';
                } else {
                    apiCost = '$' + costVal.toFixed(2);
                }
            }
        } catch (e) { }

        // Show session summary popup
        await customAlert(`Session Summary\n\nDuration: ${sessionDuration}\nAPI Usage: ${apiCost}`);

        // Stop the timer if running
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }

        resetSessionUI();
    }
}

// AUTO-DISPLAY HWID ON SETUP SCREEN
async function updateHWIDDisplay() {
    try {
        const hwid = await getHardwareID();
        console.log('[DEBUG] Fetched HWID for display:', hwid);

        const setupDisplay = document.getElementById('hwid-setup-display');
        if (setupDisplay) {
            setupDisplay.style.display = 'block';
            setupDisplay.querySelector('span').textContent = hwid;

            if (hwid === "Backend Offline") {
                setupDisplay.querySelector('span').style.color = "rgba(255, 107, 107, 0.5)";
                setupDisplay.style.cursor = 'default';
                setupDisplay.onclick = null;
            } else {
                setupDisplay.querySelector('span').style.color = "rgba(100, 255, 150, 0.4)";
                setupDisplay.title = 'Click to Copy';
                setupDisplay.style.cursor = 'pointer';
                setupDisplay.onclick = () => {
                    navigator.clipboard.writeText(hwid);
                    const span = setupDisplay.querySelector('span');
                    span.textContent = 'COPIED';
                    setTimeout(() => { span.textContent = hwid; }, 1000);
                };
            }
            console.log('[DEBUG] HWID display updated on setup screen');
        } else {
            console.warn('[DEBUG] hwid-setup-display element not found');
        }
    } catch (e) {
        console.error("Error displaying HWID on setup screen:", e);
    }
}

// Initial call
updateHWIDDisplay();

// Inject API cost and Model Selector elements into status bar dynamically
(function () {
    const statusBar = document.getElementById('status-bar');
    if (statusBar) {
        const rightSide = statusBar.querySelector('div:last-child');
        if (rightSide) {
            // Model Selector, Time, Cost (Grouped Left-Aligned)
            const middleDiv = document.createElement('div');
            // flex margin-right: auto serves to push the rest to the right
            middleDiv.id = "status-bar-middle";
            middleDiv.style.cssText = 'display: flex; align-items: center; gap: 15px; flex: 1; justify-content: center; z-index: 10; font-size: 10px;';
            middleDiv.innerHTML = `
                <!-- Model -->
                <div style="display: flex; align-items: center; gap: 4px; position: relative;">
                    <span style="color: rgba(255, 255, 255, 0.4);"></span>
                    <button id="model-selector-btn" style="background: rgba(120, 200, 180, 0.05); border: 1px solid rgba(120, 200, 180, 0.85); border-radius: 4px; padding: 2px 8px; color: rgba(120, 200, 180, 0.85); font-size: 10px; cursor: pointer; font-weight: 500; font-family: inherit; white-space: nowrap; min-width: max-content;"
                        onmouseover="this.style.background='rgba(120, 200, 180, 0.1)'; this.style.color='#fff'" onmouseout="this.style.background='rgba(120, 200, 180, 0.05)'; this.style.color='rgba(120, 200, 180, 0.85)'">
                        GPT-4o
                    </button>
                    <div id="model-dropdown" style="display: none; position: absolute; bottom: 100%; left: 0; margin-bottom: 5px; background: rgba(30,30,30,0.98); border: 1px solid rgba(255,255,255,0.15); border-radius: 6px; min-width: 220px; z-index: 10003; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
                    </div>
                </div>

                <!-- Unified Stats Group -->
                <div style="display: flex; align-items: center; gap: 10px; background: rgba(0, 0, 0, 0.2); border: 1px solid rgba(255, 255, 255, 0.05); padding: 4px 14px; border-radius: 6px; box-shadow: inset 0 1px 4px rgba(0,0,0,0.3); font-family: 'Consolas', 'Courier New', monospace; font-size: 9px; white-space: nowrap; letter-spacing: 0.5px;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span style="color: rgba(255, 255, 255, 0.35); text-transform: uppercase;">TTFT:</span>
                        <span id="response-time-ttft" style="color: rgba(120, 200, 180, 0.9); font-weight: 500; min-width: 28px;">--s</span>
                        <span style="color: rgba(255, 255, 255, 0.15); margin: 0 2px;">|</span>
                        <span style="color: rgba(255, 255, 255, 0.35); text-transform: uppercase;">TT:</span>
                        <span id="response-time-tt" style="color: rgba(120, 200, 180, 0.9); font-weight: 500; min-width: 28px;">--s</span>
                    </div>
                    
                    <div style="width: 1px; height: 12px; background: rgba(255, 255, 255, 0.15); margin: 0 2px;"></div>
                    
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="color: rgba(255, 255, 255, 0.35); text-transform: uppercase;">In:</span>
                        <span id="api-usage-input" style="color: rgba(255, 255, 255, 0.7); font-weight: 500;">0</span>
                        <span style="color: rgba(255, 255, 255, 0.15); margin: 0 2px;">|</span>
                        <span style="color: rgba(255, 255, 255, 0.35); text-transform: uppercase;">Out:</span>
                        <span id="api-usage-output" style="color: rgba(255, 255, 255, 0.7); font-weight: 500;">0</span>
                        <span style="color: rgba(255, 255, 255, 0.15); margin: 0 2px;">|</span>
                        <span style="color: rgba(255, 255, 255, 0.35); text-transform: uppercase;">Cost:</span>
                        <span id="api-cost" style="color: rgba(120, 200, 180, 0.9); font-weight: 600; min-width: 36px; display: inline-block; text-align: right;">$0.00</span>
                    </div>
                </div>
            `;
            statusBar.insertBefore(middleDiv, statusBar.children[1]); // Insert as 2nd child (between left and right)
        }

        // Initialize model selector
        const savedModel = localStorage.getItem('selectedModel');
        window.selectedModel = savedModel || 'gpt-4o'; // Default to saved or GPT-4o

        const modelBtn = document.getElementById('model-selector-btn');
        const modelDropdown = document.getElementById('model-dropdown');

        if (modelBtn && modelDropdown) {
            // Fetch models from backend with retry (backend may still be starting in built exe)
            function fetchModelsWithRetry(attempts, delay) {
                fetch('http://127.0.0.1:5050/models')
                    .then(res => res.json())
                    .then(data => {
                        if (data.models) {
                            modelDropdown.innerHTML = data.models.map(m => {
                                return `
                            <div class="model-option" data-model="${m.id}" style="padding: 8px 12px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.2s;">
                                <div style="color: rgba(255,255,255,0.9); font-size: 11px; font-weight: 500;">${m.name}</div>
                                <div style="color: rgba(255,255,255,0.4); font-size: 9px; margin-top: 2px;">
                                    ${m.speed} · ${m.cost} · ${m.accuracy} — ${m.description}
                                </div>
                            </div>
                        `}).join('');

                            modelDropdown.querySelectorAll('.model-option').forEach(opt => {
                                opt.addEventListener('mouseenter', () => opt.style.background = 'rgba(255,255,255,0.08)');
                                opt.addEventListener('mouseleave', () => opt.style.background = 'transparent');
                                opt.addEventListener('click', () => {
                                    const modelId = opt.dataset.model;
                                    window.selectedModel = modelId;
                                    localStorage.setItem('selectedModel', modelId); // Persist choice
                                    modelBtn.textContent = opt.querySelector('div').textContent.trim();
                                    modelDropdown.style.display = 'none';
                                    console.log('[MODEL] Selected:', modelId);
                                });
                            });

                            // Set default if no existing preference
                            if (data.default && !savedModel) {
                                window.selectedModel = data.default;
                                modelBtn.textContent = (data.models.find(m => m.id === data.default) || { name: 'GPT-4o' }).name;
                            } else if (savedModel && data.models) {
                                const found = data.models.find(m => m.id === savedModel);
                                if (found) {
                                    modelBtn.textContent = found.name;
                                }
                            }
                            console.log('[MODEL] Models loaded successfully');
                        }
                    })
                    .catch(e => {
                        console.warn(`[MODEL] Failed to load models (${attempts} retries left):`, e.message || e);
                        if (attempts > 1) {
                            setTimeout(() => fetchModelsWithRetry(attempts - 1, delay), delay);
                        } else {
                            console.error('[MODEL] All retries exhausted - models not loaded');
                        }
                    });
            }
            fetchModelsWithRetry(10, 2000);

            // Toggle dropdown
            modelBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                modelDropdown.style.display = modelDropdown.style.display === 'none' ? 'block' : 'none';
            });

            // Close on outside click
            document.addEventListener('click', () => {
                modelDropdown.style.display = 'none';
            });
        }
    }
})();


// Ethical Usage Modal Logic
(function () {
    const modal = document.getElementById('ethical-modal');
    const openBtn = document.getElementById('btn-ethical-open');
    const closeBtn = document.getElementById('close-ethical-modal');
    const agreeBtn = document.getElementById('btn-ethical-agree-modal');
    const discCheck = document.getElementById('setup-disclaimer-agree');

    // Initialize from persistence
    if (discCheck) {
        const alreadyAgreed = localStorage.getItem('disclaimer_agreed') === 'true';
        discCheck.checked = alreadyAgreed;
        discCheck.disabled = !alreadyAgreed;
    }

    if (modal && openBtn && closeBtn && agreeBtn && discCheck) {
        openBtn.addEventListener('click', () => {
            modal.style.display = 'flex';
        });

        const closeAndAgree = () => {
            modal.style.display = 'none';
            discCheck.disabled = false;
            discCheck.checked = true;
            localStorage.setItem('disclaimer_agreed', 'true'); // Persist immediately on explicit agreement
        };

        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
            // Don't enable checkbox here if not already agreed
        });

        agreeBtn.addEventListener('click', closeAndAgree);

        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.style.display = 'none';
        });
    }
})();

// Update Button Logic
console.log('[DEBUG] Executing Update Button Logic block...');
let updateBtnAttached = false;
const mountInterval = setInterval(() => {
    if (updateBtnAttached) {
        clearInterval(mountInterval);
        return;
    }
    const updateBtn = document.getElementById('check-update-btn');
    if (updateBtn) {
        console.log('[DEBUG] Attaching click listener to updateBtn');
        updateBtnAttached = true;
        updateBtn.addEventListener('click', () => {
            console.log('[DEBUG] updateBtn clicked!');
            updateBtn.textContent = 'Checking...';
            updateBtn.style.pointerEvents = 'none';

            // We use standard require if window.ipcRenderer isn't ready yet, as a fallback
            const ipc = window.ipcRenderer || (typeof require !== 'undefined' ? require('electron').ipcRenderer : null);

            if (ipc) {
                ipc.send('manual-update-check');
            } else {
                console.log('Update check triggered (dev style - no IPC)');
                updateBtn.textContent = 'Check for updates';
                updateBtn.style.pointerEvents = 'auto';
            }

            // Fallback timeout in case no IPC response
            setTimeout(() => {
                if (updateBtn.textContent === 'Checking...') {
                    updateBtn.textContent = 'Error checking';
                    updateBtn.style.pointerEvents = 'auto';
                }
            }, 10000);
        });
        clearInterval(mountInterval);
    }
}, 500);

