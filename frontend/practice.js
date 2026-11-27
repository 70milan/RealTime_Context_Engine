// practice.js - Practice mode: a mock interview on the same screen as a live session
// ("paper trading"). The app asks generated questions out loud, listens to your answer,
// sometimes follows up, and critiques the round at the end.
//
// Two ways to hear your answer:
//   - Groq key saved: your mic is recorded locally and sent to Groq Whisper (free) when you
//     finish; the text appears then.
//   - No Groq key: the mic streams to OpenAI like a live session, so your words appear live.
// An answer ends after ~3 s of silence, on Space, or (coding questions) on Submit.

(function () {
    const API = 'http://127.0.0.1:5050';
    const SILENCE_MS = 3000;        // quiet this long after speaking = answer finished
    const MIN_SPEECH_MS = 400;      // a cough or "um" alone doesn't count as an answer
    const MAX_FOLLOWUPS = 2;        // per main question
    const AFTER_VOICE_MS = 300;     // the interviewer's voice fades before the mic counts

    const $ = (id) => document.getElementById(id);
    const status = (text) => { const el = $('status-text'); if (el) el.innerText = text; };
    const ipc = () => window.ipcRenderer;

    const P = window.practice = {
        active: false,      // session is a practice session
        running: false,     // a round is in progress (not paused)
        focus: 'mixed',
        groq: false,
        hints: false,
        round: 0,
        queue: [],          // [{ kind: 'main' | 'coding', text }]
        idx: 0,             // current main question
        roundStart: null,   // index of this round's first entry in the session file
        nextAudio: null,    // prefetched voice for the next question
    };
    try { P.hints = localStorage.getItem('practice_hints') === 'true'; } catch (e) { }

    // ── Styles for the practice panels (kept with the feature) ─────────────────
    const style = document.createElement('style');
    style.textContent = `
      #practice-indicator, #hints-toggle {
        margin-left: 8px; font-size: 9px; text-transform: uppercase; letter-spacing: 1px;
        padding: 2px 6px; border-radius: 6px; white-space: nowrap; -webkit-app-region: no-drag;
      }
      #practice-indicator { color: #39ff88; border: 1px solid rgba(57, 255, 136, 0.45); }
      #hints-toggle { color: rgba(255,255,255,0.25); border: 1px solid rgba(255,255,255,0.1); }
      #hints-toggle.on { color: #00e6c8; border-color: rgba(0, 230, 200, 0.45); }
      .pr-panel { display: flex; flex-direction: column; gap: 8px; height: 100%; -webkit-app-region: no-drag; }
      .pr-title { font-size: 11px; color: rgba(100,255,150,0.8); letter-spacing: 0.5px; }
      .pr-note { font-size: 10px; color: rgba(255,255,255,0.4); }
      .pr-panel textarea {
        flex: 1; min-height: 120px; resize: none; box-sizing: border-box; width: 100%;
        background: rgba(0,0,0,0.35); color: #e8e8e8; border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px; padding: 8px 10px; font-size: 12px; line-height: 1.5; outline: none;
      }
      .pr-panel textarea.code { font-family: Consolas, 'Courier New', monospace; font-size: 12px; }
      .pr-row { display: flex; gap: 8px; }
      .pr-btn {
        padding: 6px 14px; border-radius: 10px; font-size: 10px; font-weight: 600; letter-spacing: 0.8px;
        text-transform: uppercase; background: rgba(100,255,150,0.1); color: rgba(100,255,150,0.9);
        border: 1px solid rgba(100,255,150,0.3);
      }
      .pr-btn.secondary { background: rgba(255,255,255,0.03); color: rgba(255,255,255,0.55); border-color: rgba(255,255,255,0.12); }
      .pr-btn:disabled { opacity: 0.4; }
      .pr-hint { font-size: 12px; color: rgba(220,240,225,0.85); white-space: pre-wrap; }
      .pr-answer {
        flex: 1; min-height: 40px; overflow-y: auto; white-space: pre-wrap; font-size: 13px; line-height: 1.55;
        color: rgba(215,225,255,0.9); background: rgba(40,50,80,0.25); border: 1px solid rgba(120,160,255,0.15);
        border-radius: 10px; padding: 8px 10px; user-select: text;
      }
      .pr-answer.dim { color: rgba(255,255,255,0.35); font-style: italic; }
      body.practice-mode #transcript-area .seg[data-src="mic"] { display: none; }
      .pr-review { white-space: pre-wrap; font-size: 12px; line-height: 1.55; color: rgba(225,232,255,0.88); overflow-y: auto; flex: 1; }
    `;
    document.head.appendChild(style);

    // ── Response-area panels ───────────────────────────────────────────────────
    const area = () => $('response-area');
    function panel(html) {
        const el = area();
        el.innerHTML = `<div class="pr-panel">${html}</div>`;
        return el.firstElementChild;
    }
    const esc = (t) => window.escapeHtml ? window.escapeHtml(t) : String(t);

    function showEditor(note) {
        const lines = P.queue.map((q, i) => `${i + 1}. ` + (q.kind === 'coding' ? '[Coding] ' : '') + q.text).join('\n');
        const p = panel(`
          <div class="pr-title">Practice round ${P.round} &middot; ${P.queue.length} questions</div>
          <div class="pr-note">${esc(note || 'Edit or delete lines (one question per line, [Coding] marks a coding task), then Start. Numbers are added for you.')}</div>
          <textarea id="pr-editor" spellcheck="false">${esc(lines)}</textarea>
          <div class="pr-row">
            <button class="pr-btn" id="pr-start" type="button">Start round</button>
            <button class="pr-btn secondary" id="pr-new" type="button">New set</button>
          </div>`);
        p.querySelector('#pr-start').onclick = () => {
            if (!window.isSessionActive) $('btn-session-start').click();  // starts the timer, then P.start()
            else P.start();
        };
        p.querySelector('#pr-new').onclick = () => generateRound();
    }

    function readEditor() {
        const ed = $('pr-editor');
        if (!ed) return false;
        P.queue = ed.value.split('\n').map(l => l.trim().replace(/^\d+[.)]\s*/, '')).filter(Boolean).map(l => {
            const coding = /^\[coding\]\s*/i.test(l);
            return { kind: coding ? 'coding' : 'main', text: l.replace(/^\[coding\]\s*/i, '') };
        });
        P.idx = 0;
        return true;
    }

    // ── Backend calls ──────────────────────────────────────────────────────────
    async function post(path, body) {
        const res = await fetch(API + path, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {})
        });
        return res.json();
    }

    async function generateRound() {
        P.round += 1;
        panel(`<div class="pr-title">Practice round ${P.round}</div><div class="pr-note">Writing new questions from your resume and the job description...</div>`);
        status('Generating questions...');
        try {
            const json = await post('/practice/questions', { focus: P.focus });
            if (json.status !== 'ok') throw new Error(json.error || 'Generation failed');
            P.queue = json.questions;
            P.idx = 0;
            P.roundStart = null;
            showEditor();
            status(window.isSessionActive ? 'Round ready' : 'Press Start to begin');
        } catch (e) {
            P.round -= 1;
            panel(`<div class="pr-title">Couldn't generate questions</div><div class="pr-note">${esc(e.message)}</div>
                   <div class="pr-row"><button class="pr-btn" id="pr-retry" type="button">Try again</button></div>`)
                .querySelector('#pr-retry').onclick = () => generateRound();
            status('Generation failed');
        }
    }

    // ── The interviewer's voice ────────────────────────────────────────────────
    let currentAudio = null;
    async function fetchVoice(text) {
        try {
            const res = await fetch(API + '/practice/tts', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text })
            });
            if (!res.ok) return null;
            return URL.createObjectURL(await res.blob());
        } catch (e) { return null; }
    }

    function speak(text, prefetched) {
        return new Promise(async (resolve) => {
            P.speaking = true;
            const done = () => { P.speaking = false; currentAudio = null; setTimeout(resolve, AFTER_VOICE_MS); };
            const url = (await prefetched) || await fetchVoice(text);
            if (!P.running) { P.speaking = false; return resolve(); }
            if (url) {
                const audio = new Audio(url);
                currentAudio = audio;
                audio.onended = () => { URL.revokeObjectURL(url); done(); };
                audio.onerror = () => { URL.revokeObjectURL(url); done(); };
                audio.play().catch(done);
            } else {
                // No internet voice: the built-in Windows voice
                const u = new SpeechSynthesisUtterance(text);
                u.rate = 1.15;  // same 1.15x as the natural voice
                u.onend = done;
                u.onerror = done;
                currentAudio = { pause: () => speechSynthesis.cancel() };
                speechSynthesis.speak(u);
            }
        });
    }

    function stopVoice() {
        if (currentAudio) { try { currentAudio.pause(); } catch (e) { } currentAudio = null; }
        try { speechSynthesis.cancel(); } catch (e) { }
        P.speaking = false;
    }

    // ── Hearing the answer ─────────────────────────────────────────────────────
    // One listen at a time; finish(result) resolves it. Space and Submit call finish too.
    let listen = null;

    function endAnswer() { if (listen && !listen.coding) listen.finishNow(); }

    document.addEventListener('keydown', (e) => {
        if (!P.running || !listen || e.code !== 'Space') return;
        const t = e.target;
        if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.isContentEditable)) return;
        e.preventDefault();
        endAnswer();
    });

    // Groq path: record locally, detect the end by volume, transcribe when done
    function listenLocal(coding) {
        return new Promise(async (resolve) => {
            let stream, ctx, node, src, sink;
            const chunks = [];
            let speechMs = 0, silenceMs = 0, floor = 0.005, finished = false;
            setAnswer(coding ? 'Listening... explain while you type.' : 'Listening... your words appear when you finish.', true);

            const cleanup = () => {
                try { node && (node.onaudioprocess = null); src && src.disconnect(); node && node.disconnect(); sink && sink.disconnect(); } catch (e) { }
                try { stream && stream.getTracks().forEach(t => t.stop()); } catch (e) { }
                try { ctx && ctx.close(); } catch (e) { }
                const bar = $('volume-bar'); if (bar) bar.style.width = '0%';
            };
            const finish = async (keep) => {
                if (finished) return;
                finished = true;
                cleanup();
                listen = null;
                if (!keep) return resolve(null);
                if (speechMs < MIN_SPEECH_MS) { setAnswer('(no answer)', true); return resolve({ said: '' }); }
                setAnswer('Transcribing...', true);
                status('Transcribing your answer...');
                try {
                    const fd = new FormData();
                    fd.append('file', encodeWav(chunks, 16000), 'answer.wav');
                    const json = await (await fetch(API + '/practice/transcribe', { method: 'POST', body: fd })).json();
                    const text = json.status === 'ok' ? json.text : '';
                    setAnswer(text || '(could not transcribe)', !text);
                    resolve({ said: text });
                } catch (e) {
                    setAnswer('(could not transcribe)', true);
                    resolve({ said: '' });
                }
            };
            listen = { coding, finishNow: () => finish(true), cancel: () => finish(false) };

            try {
                stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
                ctx = new AudioContext({ sampleRate: 16000 });
                src = ctx.createMediaStreamSource(stream);
                node = ctx.createScriptProcessor(4096, 1, 1);
                sink = ctx.createGain(); sink.gain.value = 0;
                const frameMs = 4096 / 16000 * 1000;
                node.onaudioprocess = (e) => {
                    if (finished) return;
                    const d = e.inputBuffer.getChannelData(0);
                    chunks.push(new Float32Array(d));
                    let sum = 0;
                    for (let i = 0; i < d.length; i++) sum += d[i] * d[i];
                    const rms = Math.sqrt(sum / d.length);
                    P.level = rms;  // current mic level, for display and tests
                    const bar = $('volume-bar'); if (bar) bar.style.width = Math.min(100, Math.round(rms * 1000)) + '%';
                    // Background level: drops to quiet frames at once, rises slowly and only between words
                    const speaking = rms > Math.max(0.015, floor * 3);
                    floor = rms < floor ? rms : speaking ? floor : floor + (rms - floor) * 0.02;
                    if (speaking) { speechMs += frameMs; silenceMs = 0; } else { silenceMs += frameMs; }
                    if (!coding && speechMs >= MIN_SPEECH_MS && silenceMs >= SILENCE_MS) finish(true);
                };
                src.connect(node); node.connect(sink); sink.connect(ctx.destination);
                status(coding ? 'Explain while you type, then Submit' : 'Listening... (Space = done)');
            } catch (e) {
                finished = true; listen = null;
                micFailed(e.message);
                resolve(null);
            }
        });
    }

    function encodeWav(chunks, rate) {
        const len = chunks.reduce((n, c) => n + c.length, 0);
        const buf = new ArrayBuffer(44 + len * 2);
        const v = new DataView(buf);
        const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
        str(0, 'RIFF'); v.setUint32(4, 36 + len * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
        v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
        v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
        str(36, 'data'); v.setUint32(40, len * 2, true);
        let o = 44;
        for (const c of chunks) for (let i = 0; i < c.length; i++, o += 2) {
            const s = Math.max(-1, Math.min(1, c[i]));
            v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }
        return new Blob([buf], { type: 'audio/wav' });
    }

    // OpenAI path: the live mic channel (words appear as you speak); the end is timed from
    // its speech events. Events from the interviewer's voice are ignored.
    const ignored = new Set();
    window.__practiceHook = (src, data) => {
        if (!P.active || src !== 'mic') return true;
        const id = data.item_id;
        if (data.type === 'speech_started' && (P.speaking || !listen)) { if (id) ignored.add(id); return false; }
        if (id && ignored.has(id)) return false;
        if (listen && listen.onEvent) listen.onEvent(data);
        return true;
    };

    function listenLive(coding) {
        return new Promise(async (resolve) => {
            const items = new Map();   // item_id -> final text (null while still being transcribed)
            const live = new Map();    // item_id -> words so far
            const render = () => {
                const text = [...live.values()].join(' ').trim();
                setAnswer(text || 'Listening... your words appear as you speak.', !text);
            };
            render();
            let talking = 0, lastActivity = Date.now(), finished = false, timer = null;
            const finish = (keep) => {
                if (finished) return;
                finished = true;
                clearInterval(timer);
                listen = null;
                if (!keep) return resolve(null);
                // Wait briefly for transcripts still in flight
                const started = Date.now();
                const wait = setInterval(() => {
                    const pending = [...items.values()].some(t => t === null);
                    if (!pending || Date.now() - started > 4000) {
                        clearInterval(wait);
                        resolve({ said: [...items.values()].filter(Boolean).join(' ').trim() });
                    }
                }, 150);
            };
            listen = {
                coding,
                finishNow: () => finish(true),
                cancel: () => finish(false),
                onEvent: (d) => {
                    if (d.type === 'speech_started') { talking++; items.set(d.item_id, null); lastActivity = Date.now(); }
                    else if (d.type === 'speech_stopped') { talking = Math.max(0, talking - 1); lastActivity = Date.now(); }
                    else if (d.type === 'transcript_delta') { live.set(d.item_id, (live.get(d.item_id) || '') + (d.text || '')); render(); }
                    else if (d.type === 'transcript_final') { items.set(d.item_id, (d.text || '').trim()); live.set(d.item_id, (d.text || '').trim()); lastActivity = Date.now(); render(); }
                }
            };
            const ok = await window.practiceAudio.openMic();
            if (!ok) { finished = true; listen = null; micFailed('could not open the microphone'); return resolve(null); }
            status(coding ? 'Explain while you type, then Submit' : 'Listening... (Space = done)');
            timer = setInterval(() => {
                const spoke = [...items.values()].some(t => t !== '');
                if (!coding && spoke && talking === 0 && Date.now() - lastActivity >= SILENCE_MS) finish(true);
            }, 200);
        });
    }

    // Without a mic the round can't go on: pause it instead of racing through every question
    function micFailed(reason) {
        P.pause();
        panel(`<div class="pr-title">Microphone problem</div><div class="pr-note">${esc(reason)}. Check the mic, then press Start to retry this question.</div>`);
        status('Microphone error');
    }

    const hear = (coding) => (P.groq ? listenLocal(coding) : listenLive(coding));

    function setAnswer(text, dim) {
        const el = $('pr-answer');
        if (!el) return;
        el.textContent = text;
        el.classList.toggle('dim', !!dim);
        el.scrollTop = el.scrollHeight;
    }

    // In practice the two sections read "Question" and "Your answer"
    function setHeaders(top, bottom) {
        const t = document.querySelector('#transcript-section .section-header span');
        const b = document.querySelector('#response-section .section-header span');
        if (t && top) t.textContent = top;
        if (b && bottom) b.textContent = bottom;
    }

    // The model menu can't change what practice uses, so it shows the engine and is locked
    function lockModelMenu(lock) {
        const btn = $('model-selector-btn');
        if (!btn) return;
        if (lock) {
            if (btn.dataset.liveLabel === undefined) btn.dataset.liveLabel = btn.textContent;
            btn.textContent = P.groq ? 'Groq GPT-OSS-120B' : 'GPT-4o-mini';
            btn.style.pointerEvents = 'none';
            btn.style.opacity = '0.75';
        } else if (btn.dataset.liveLabel !== undefined) {
            btn.textContent = btn.dataset.liveLabel;
            delete btn.dataset.liveLabel;
            btn.style.pointerEvents = '';
            btn.style.opacity = '';
        }
    }

    // ── One question: ask it, show hints / code box, hear the answer ───────────
    async function ask(text, kind, prefetched, alive) {
        if (kind !== 'followup') { const t = $('transcript-area'); if (t) t.innerHTML = ''; }
        window.practiceAudio.addLine('system', text);
        const coding = kind === 'coding';

        // Answer panel: hints (if on) and, for coding, the code box
        const p = panel(`
          <div class="pr-title">Question ${P.idx + 1} of ${P.queue.length}${kind === 'followup' ? ' &middot; follow-up' : coding ? ' &middot; coding' : ''}</div>
          ${P.hints ? '<div class="pr-hint" id="pr-hint">Hints...</div>' : '<div class="pr-note">Answer out loud. Space = done, or just stop talking.</div>'}
          <div class="pr-answer dim" id="pr-answer">Waiting for the question...</div>
          ${coding ? `<textarea id="pr-code" class="code" spellcheck="false" placeholder="Type your solution here while you explain it"></textarea>
                     <div class="pr-row"><button class="pr-btn" id="pr-submit" type="button">Submit</button></div>` : ''}`);
        let hint = '';
        if (P.hints) {
            post('/practice/hint', { question: text }).then(j => {
                hint = j.status === 'ok' ? j.hint : '';
                const el = $('pr-hint'); if (el) el.textContent = hint || '(no hint)';
            }).catch(() => { });
        }
        // Submit ends a coding answer, even if clicked while the question is still being read
        let submitted = false;
        if (coding) p.querySelector('#pr-submit').onclick = () => { submitted = true; if (listen) listen.finishNow(); };

        status('Interviewer is asking...');
        await speak(text, prefetched);
        if (!alive()) return null;
        const hearing = hear(coding);
        if (submitted && listen) listen.finishNow();
        const result = await hearing;
        if (!result || !alive()) return null;
        result.code = coding ? ($('pr-code') || {}).value || '' : '';
        result.hint = hint;
        return result;
    }

    async function record(question, result, kind) {
        const number = P.idx + 1;
        try {
            const j = await post('/practice/record', { question, said: result.said, code: result.code, hint: result.hint, kind, number });
            if (j.status === 'ok' && P.roundStart === null) P.roundStart = j.count - 1;
        } catch (e) { }
        // Convo tab: the question and what you said (rendered like a restored practice session)
        if (ipc()) ipc().send('convo-update', {
            question, response: result.hint || '', said: result.said || '', code: result.code || '',
            kind, number, practice: true, model: 'Hint', timestamp: new Date().toISOString()
        });
    }

    // ── The round ──────────────────────────────────────────────────────────────
    let runId = 0;
    async function runRound() {
        const id = ++runId;
        const alive = () => P.running && id === runId;
        while (alive() && P.idx < P.queue.length) {
            const q = P.queue[P.idx];
            const voice = P.nextAudio; P.nextAudio = null;
            const next = P.queue[P.idx + 1];
            if (next) P.nextAudio = fetchVoice(next.text);  // ready before you finish answering

            let result = await ask(q.text, q.kind, voice, alive);
            if (!result || !alive()) return;  // paused or ended
            await record(q.text, result, q.kind);

            let lastQ = q.text;
            for (let f = 0; f < MAX_FOLLOWUPS && alive(); f++) {
                status('Thinking...');
                let follow = '';
                try { follow = (await post('/practice/next', { question: lastQ, answer: result.said, code: result.code })).follow_up || ''; } catch (e) { }
                if (!follow || !alive()) break;
                result = await ask(follow, 'followup', null, alive);
                if (!result || !alive()) return;
                await record(follow, result, 'followup');
                lastQ = follow;
            }
            if (!alive()) return;  // a paused round re-asks this question on Start
            P.idx += 1;
        }
        if (alive()) finishRound();
    }

    async function finishRound() {
        P.running = false;
        if (!P.groq && window.practiceAudio) window.practiceAudio.closeMic();
        setHeaders(null, 'Round review');
        panel(`<div class="pr-title">Round ${P.round} done</div><div class="pr-note">Reviewing your answers with gpt-4o...</div>`);
        status('Reviewing your round...');
        let review = '';
        try {
            const name = typeof currentSessionName !== 'undefined' ? currentSessionName : '';
            const j = await (await fetch(`${API}/session/critique/${encodeURIComponent(name)}?start=${P.roundStart || 0}`, { method: 'POST' })).json();
            review = j.status === 'ok' ? j.review : (j.error || 'Review failed');
        } catch (e) { review = 'Review failed: ' + e.message; }
        const p = panel(`
          <div class="pr-title">Round ${P.round} review</div>
          <div class="pr-review">${esc(review)}</div>
          <div class="pr-row">
            <button class="pr-btn" id="pr-next-round" type="button">Next round</button>
          </div>`);
        p.querySelector('#pr-next-round').onclick = () => { setHeaders(null, 'Your answer'); generateRound(); };
        status('Round reviewed');
    }

    // ── Entry points used by setup.js / index.html ─────────────────────────────
    P.enter = async (focus) => {
        if (!P.active) P.smartBefore = !!window.__smartMode;  // given back when practice ends
        P.active = true;
        window.__practiceMode = true;
        if (window.setSmartMode) window.setSmartMode(false);
        P.focus = focus || 'mixed';
        P.round = 0; P.queue = []; P.idx = 0; P.running = false;
        const smart = $('auto-mode-indicator'); if (smart) smart.style.display = 'none';
        const hints = $('hints-toggle');
        if (hints) { hints.style.display = ''; hints.classList.toggle('on', P.hints); }
        document.body.classList.add('practice-mode');
        setHeaders('Question', 'Your answer');
        try { P.groq = !!(await (await fetch(API + '/practice/status')).json()).groq; } catch (e) { P.groq = false; }
        const badge = $('practice-indicator');
        if (badge) { badge.style.display = ''; badge.textContent = P.groq ? 'Practice · Groq' : 'Practice · OpenAI'; }
        lockModelMenu(true);
        generateRound();
    };

    P.exit = () => {
        P.pause();
        const wasActive = P.active;
        P.active = false;
        window.__practiceMode = false;
        if (wasActive && P.smartBefore && window.setSmartMode) window.setSmartMode(true);
        const smart = $('auto-mode-indicator'); if (smart) smart.style.display = '';
        const badge = $('practice-indicator'); if (badge) badge.style.display = 'none';
        const hints = $('hints-toggle'); if (hints) hints.style.display = 'none';
        if (wasActive) {
            document.body.classList.remove('practice-mode');
            setHeaders('Live Transcript', 'AI Assistant');
            lockModelMenu(false);
        }
    };

    P.start = () => {
        if (!P.active || P.running) return;
        if ($('pr-editor')) readEditor();
        if (!P.queue.length || P.idx >= P.queue.length) return;  // still generating, or round finished
        P.running = true;
        runRound();
    };

    // Pause (also End / expiry, via stopListening): stop the voice and the mic; Start
    // re-asks the current question
    P.pause = () => {
        if (!P.active) return;
        P.running = false;
        runId++;
        stopVoice();
        if (listen) listen.cancel();
        if (P.nextAudio) { P.nextAudio = null; }
        if (window.practiceAudio) window.practiceAudio.closeMic();
    };

    function wireHints() {
        const hints = $('hints-toggle');
        if (hints) hints.onclick = () => {
            P.hints = !P.hints;
            hints.classList.toggle('on', P.hints);
            try { localStorage.setItem('practice_hints', P.hints); } catch (e) { }
        };
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wireHints);
    else wireHints();
})();
