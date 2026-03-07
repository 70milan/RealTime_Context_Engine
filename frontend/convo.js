const { ipcRenderer } = require('electron');

let currentSessionStats = {
    sumTtft: 0,
    sumTt: 0,
    validTtft: 0,
    validTt: 0,
    totalIn: 0,
    totalOut: 0,
    totalCost: 0
};

window.copyToClipboard = function (element) {
    // Walk up to aiBubble, find .ai-body sibling
    const aiBubble = element.closest('.ai-bubble');
    if (aiBubble) {
        const bodyEl = aiBubble.querySelector('.ai-body');
        if (bodyEl) {
            navigator.clipboard.writeText(bodyEl.innerText);
            element.textContent = 'copied!';
            setTimeout(() => element.textContent = '[copy]', 2000);
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const closeBtn = document.getElementById('close-btn');
    const convoList = document.getElementById('conversation-list');
    const titleEl = document.getElementById('convo-session-title');

    // Stats Elements
    const avgStatsEl = document.getElementById('convo-avg-stats');
    const avgTtftEl = document.getElementById('avg-ttft');
    const avgTtEl = document.getElementById('avg-tt');
    const avgExchEl = document.getElementById('avg-exchanges');

    const footerEl = document.getElementById('convo-footer');
    const tokensInEl = document.getElementById('tokens-in');
    const tokensOutEl = document.getElementById('tokens-out');
    const costEl = document.getElementById('api-cost');

    // Dragging support (whole window is draggable via CSS -webkit-app-region: drag handled in HTML)
    // The close button hides the window
    closeBtn.addEventListener('click', () => {
        ipcRenderer.send('hide-convo-window');
    });

    const exportBtn = document.getElementById('export-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', async () => {
            // Build a clean multi-line header from stored session data
            const sessionName = titleEl.dataset.sessionName || 'Unknown Session';
            const targetRole = titleEl.dataset.role || '';
            let textContent = `Session:      ${sessionName}\n`;
            if (targetRole) textContent += `Target Role:  ${targetRole}\n`;
            textContent += `Exported:     ${new Date().toLocaleString()}\n`;
            textContent += `--------------------------------------------------\n\n`;

            const pairs = convoList.children;
            for (let i = 0; i < pairs.length; i++) {
                const pair = pairs[i];
                if (pair.classList.contains('empty-state')) continue;

                // Handle date separators
                if (pair.style.textAlign === 'center') {
                    textContent += `\n--- ${pair.innerText} ---\n\n`;
                    continue;
                }

                // Get User bubble text
                const userBubble = pair.querySelector('div[style*="justify-content: flex-end"] div');
                if (userBubble) {
                    // Extract just the question text, ignoring the timestamp inner div
                    const clone = userBubble.cloneNode(true);
                    const timeDiv = clone.querySelector('div');
                    if (timeDiv) timeDiv.remove();
                    textContent += `User:\n${clone.innerText.trim()}\n\n`;
                }

                // Get AI bubble text
                const aiBubble = pair.querySelector('.ai-body');
                if (aiBubble) {
                    textContent += `AI:\n${aiBubble.innerText.trim()}\n\n`;
                }

                if (userBubble || aiBubble) {
                    textContent += `--------------------------------------------------\n\n`;
                }
            }



            try {
                // Determine a default filename based on title
                let safeTitle = titleEl.innerText.replace('Conversation | ', '').replace(/[^a-z0-9]/gi, '_').toLowerCase() || 'conversation';
                const defaultName = `${safeTitle}_export.txt`;

                const response = await ipcRenderer.invoke('export-conversation', textContent, defaultName);
                if (response.success) {
                    const originalHtml = exportBtn.innerHTML;
                    exportBtn.innerHTML = `
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgba(100,255,150,0.9)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    `;
                    setTimeout(() => exportBtn.innerHTML = originalHtml, 2000);
                }
            } catch (err) {
                console.error("Export failed:", err);
            }
        });
    }

    const scrollToBottom = () => {
        // Need to scroll the container not the inner div
        convoList.scrollTop = convoList.scrollHeight;
    };

    const updateStatsDisplay = () => {
        if (currentSessionStats.validTtft > 0) {
            avgStatsEl.style.display = 'flex';
            avgExchEl.textContent = currentSessionStats.validTtft;

            const avgTtft = currentSessionStats.sumTtft / currentSessionStats.validTtft;
            avgTtftEl.textContent = avgTtft.toFixed(1) + 's';

            if (currentSessionStats.validTt > 0) {
                const avgTt = currentSessionStats.sumTt / currentSessionStats.validTt;
                avgTtEl.textContent = avgTt.toFixed(1) + 's';
            }
        }

        if (currentSessionStats.totalCost > 0 || currentSessionStats.totalIn > 0) {
            footerEl.style.display = 'block';
            tokensInEl.textContent = currentSessionStats.totalIn.toLocaleString();
            tokensOutEl.textContent = currentSessionStats.totalOut.toLocaleString();
            costEl.textContent = currentSessionStats.totalCost < 1
                ? (currentSessionStats.totalCost * 100).toFixed(3) + '¢'
                : '$' + currentSessionStats.totalCost.toFixed(3);
        }
    };

    const buildBubblePair = (entry) => {
        const entryTimeStr = entry.timestamp
            ? new Date(entry.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
            : '';

        const pairDiv = document.createElement('div');
        pairDiv.style.cssText = 'margin-bottom: 14px;';

        // User bubble
        if (entry.question) {
            const userRow = document.createElement('div');
            userRow.style.cssText = 'display: flex; justify-content: flex-end; margin-bottom: 6px;';
            const userBubble = document.createElement('div');
            userBubble.style.cssText = [
                'max-width: 75%; background: rgba(60,60,70,0.7);',
                'border: 1px solid rgba(255,255,255,0.08); border-radius: 14px 14px 3px 14px;',
                'padding: 8px 12px; font-size: 11px; color: rgba(255,255,255,0.75); line-height: 1.5; word-break: break-word;'
            ].join('');

            const isScreen = entry.question.startsWith('[USER SHARED A SCREENSHOT]');
            const displayQ = isScreen
                ? (entry.question.replace('[USER SHARED A SCREENSHOT] Question about the screenshot: ', '').trim() || '<em style="color:rgba(255,255,255,0.35);">screen only</em>')
                : entry.question;
            const screenLabel = isScreen ? '📷 SCREEN · ' : '';
            userBubble.innerHTML = `<div style="font-size:9px;color:rgba(255,255,255,0.3);margin-bottom:3px;letter-spacing:0.5px;">${screenLabel}${entryTimeStr}</div>${displayQ}`;
            userRow.appendChild(userBubble);
            pairDiv.appendChild(userRow);
        }

        // AI bubble
        if (entry.response) {
            const aiRow = document.createElement('div');
            aiRow.style.cssText = 'display: flex; justify-content: flex-start; margin-bottom: 5px;';
            const aiBubble = document.createElement('div');
            aiBubble.className = 'ai-bubble';
            aiBubble.style.cssText = [
                'max-width: 80%; background: rgba(30,40,35,0.7);',
                'border: 1px solid rgba(100,255,150,0.12); border-radius: 14px 14px 14px 3px;',
                'padding: 8px 12px; font-size: 11px; color: rgba(220,240,225,0.85); line-height: 1.5;',
                'word-break: break-word; max-height: 300px; overflow-y: auto;',
                'display: flex; flex-direction: column; gap: 6px;'
            ].join('');

            const modelLabel = entry.model ? entry.model.toUpperCase() : 'AI';

            const aiHeader = document.createElement('div');
            aiHeader.style.cssText = 'display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;';
            const copyBtn = document.createElement('span');
            copyBtn.textContent = '[copy]';
            copyBtn.style.cssText = 'font-size:9px;color:rgba(255,255,255,0.25);font-family:monospace;cursor:pointer;padding:1px 5px;border-radius:3px;border:1px solid rgba(255,255,255,0.08);transition:all 0.15s;';
            copyBtn.onmouseover = () => { copyBtn.style.color = '#fff'; copyBtn.style.borderColor = 'rgba(255,255,255,0.25)'; };
            copyBtn.onmouseout = () => { copyBtn.style.color = 'rgba(255,255,255,0.25)'; copyBtn.style.borderColor = 'rgba(255,255,255,0.08)'; };
            copyBtn.onclick = () => window.copyToClipboard(copyBtn);

            const modelSpan = document.createElement('span');
            modelSpan.style.cssText = 'font-size:9px;color:rgba(100,255,150,0.4);letter-spacing:0.5px;';
            modelSpan.textContent = `${modelLabel} · ${entryTimeStr}`;
            aiHeader.appendChild(modelSpan);
            aiHeader.appendChild(copyBtn);

            const aiBody = document.createElement('div');
            aiBody.className = 'ai-body';
            aiBody.style.cssText = 'flex: 1; min-height: 0;';
            aiBody.innerHTML = entry.response;
            aiBody.querySelectorAll('pre code').forEach(b => {
                if (typeof hljs !== 'undefined') hljs.highlightElement(b);
            });

            const aiFooter = document.createElement('div');
            aiFooter.style.cssText = 'display: flex; flex-wrap: wrap; gap: 6px; font-size: 10px; font-family: monospace; color: rgba(255,255,255,0.6); letter-spacing: 0.3px; padding-top: 4px; padding-left: 6px; flex-shrink: 0;';
            const si = [];
            if (entry.response_time > 0) si.push(`TTFT <span style="color:rgba(100,255,150,0.9); font-weight:600;">${parseFloat(entry.response_time).toFixed(1)}s</span>`);
            if (entry.total_time > 0) si.push(`TT <span style="color:rgba(100,255,150,0.9); font-weight:600;">${parseFloat(entry.total_time).toFixed(1)}s</span>`);
            if (entry.input_tokens > 0) si.push(`IN <span style="color:rgba(255,255,255,0.9); font-weight:600;">${Number(entry.input_tokens).toLocaleString()}</span>`);
            if (entry.output_tokens > 0) si.push(`OUT <span style="color:rgba(255,255,255,0.9); font-weight:600;">${Number(entry.output_tokens).toLocaleString()}</span>`);
            if (entry.cost > 0) si.push(`<span style="color:rgba(255,200,100,0.9); font-weight:600;">${entry.cost < 1 ? (entry.cost * 100).toFixed(3) + '¢' : '$' + entry.cost.toFixed(3)}</span>`);
            aiFooter.innerHTML = si.length > 0 ? si.join('<span style="color:rgba(255,255,255,0.4); margin: 0 2px;">·</span>') : '<span style="opacity:0.3">no stats</span>';

            aiBubble.appendChild(aiHeader);
            aiBubble.appendChild(aiBody);

            // Wrap the bubble and footer in a flex column
            const aiCol = document.createElement('div');
            aiCol.style.cssText = 'display: flex; flex-direction: column; max-width: 80%;';

            aiBubble.style.maxWidth = '100%'; // let column handle max width
            aiCol.appendChild(aiBubble);
            aiCol.appendChild(aiFooter);

            aiRow.appendChild(aiCol);
            pairDiv.appendChild(aiRow);
        }

        return pairDiv;
    };

    // -- LOAD FULL HISTORY (from session resume) --
    ipcRenderer.on('load-convo-history', (event, payload) => {
        const divider = '<span style="color: rgba(255,255,255,0.2); margin: 0 8px;">|</span>';
        const roleText = payload.role
            ? divider + ' <span style="color: rgba(255,255,255,0.4);">' + payload.role + '</span>'
            : '';
        titleEl.dataset.sessionName = payload.sessionName || '';
        titleEl.dataset.role = payload.role || '';
        titleEl.innerHTML = payload.sessionName
            ? 'Conversation ' + divider + ' <span style="color: rgba(255,255,255,0.6);">' + payload.sessionName + '</span>' + roleText
            : 'Conversation Window';

        convoList.innerHTML = '';
        currentSessionStats = { sumTtft: 0, sumTt: 0, validTtft: 0, validTt: 0, totalIn: 0, totalOut: 0, totalCost: 0 };

        if (!payload.historyArray || payload.historyArray.length === 0) {
            convoList.innerHTML = '<div class="empty-state">No conversation yet.</div>';
            avgStatsEl.style.display = 'none';
            footerEl.style.display = 'none';
            return;
        }

        let lastDateStr = '';
        payload.historyArray.forEach(entry => {
            if (entry.timestamp) {
                try {
                    const d = new Date(entry.timestamp);
                    const dayStr = d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' });
                    if (dayStr !== lastDateStr) {
                        lastDateStr = dayStr;
                        const sep = document.createElement('div');
                        sep.style.cssText = 'text-align: center; padding: 6px 0; margin: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.06);';
                        sep.innerHTML = '<span style="color: rgba(255,255,255,0.6); font-size: 10px; letter-spacing: 1px; font-weight: 500;">' + dayStr + '</span>';
                        convoList.appendChild(sep);
                    }
                } catch (e) { }
            }

            const pairDiv = buildBubblePair(entry);
            convoList.appendChild(pairDiv);

            if (entry.response_time > 0) { currentSessionStats.sumTtft += parseFloat(entry.response_time); currentSessionStats.validTtft++; }
            if (entry.total_time > 0) { currentSessionStats.sumTt += parseFloat(entry.total_time); currentSessionStats.validTt++; }
            if (entry.input_tokens > 0) currentSessionStats.totalIn += parseInt(entry.input_tokens);
            if (entry.output_tokens > 0) currentSessionStats.totalOut += parseInt(entry.output_tokens);
            if (entry.cost > 0) currentSessionStats.totalCost += parseFloat(entry.cost);
        });

        scrollToBottom();
        updateStatsDisplay();
    });

    // -- LIVE REAL-TIME BUBBLE APPEND --
    // payload.bubble is a fully formed { question, response, metadata } JSON object
    // OR payload.outerHtml is the entire pairDiv outerHTML
    ipcRenderer.on('render-convo-update', (event, payload) => {
        const emptyState = convoList.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        // Build the pair from structured data so copy buttons work natively
        const entry = {
            question: payload.question,
            response: payload.response,
            model: payload.model,
            timestamp: payload.timestamp,
            response_time: payload.ttft,
            total_time: payload.totalTime,
            input_tokens: payload.responseInTokens,
            output_tokens: payload.responseOutTokens,
            cost: payload.responseCost
        };

        const pairDiv = buildBubblePair(entry);
        convoList.appendChild(pairDiv);
        scrollToBottom();

        // Update stats
        if (payload.ttft > 0) { currentSessionStats.sumTtft += parseFloat(payload.ttft); currentSessionStats.validTtft++; }
        if (payload.totalTime > 0) { currentSessionStats.sumTt += parseFloat(payload.totalTime); currentSessionStats.validTt++; }
        if (payload.responseInTokens > 0) currentSessionStats.totalIn += parseInt(payload.responseInTokens);
        if (payload.responseOutTokens > 0) currentSessionStats.totalOut += parseInt(payload.responseOutTokens);
        if (payload.responseCost > 0) currentSessionStats.totalCost += parseFloat(payload.responseCost);

        updateStatsDisplay();
    });

    // -- TITLE UPDATE --
    ipcRenderer.on('set-convo-title', (event, titlePayload) => {
        const divider = '<span style="color: rgba(255,255,255,0.2); margin: 0 8px;">|</span>';
        const roleText = titlePayload.role
            ? divider + ' <span style="color: rgba(255,255,255,0.4);">' + titlePayload.role + '</span>'
            : '';
        titleEl.dataset.sessionName = titlePayload.sessionName || '';
        titleEl.dataset.role = titlePayload.role || '';
        titleEl.innerHTML = titlePayload.sessionName
            ? 'Conversation ' + divider + ' <span style="color: rgba(255,255,255,0.6);">' + titlePayload.sessionName + '</span>' + roleText
            : 'Conversation Window';
    });

    // -- CLEAR (only for when transcript is fully wiped) --
    // We do NOT clear conversation history on Ctrl+Backspace. 
    // The floating window retains conversation across clears.
    ipcRenderer.on('clear-convo-history', () => {
        convoList.innerHTML = '<div class="empty-state">No conversation yet.</div>';
        currentSessionStats = { sumTtft: 0, sumTt: 0, validTtft: 0, validTt: 0, totalIn: 0, totalOut: 0, totalCost: 0 };
        avgStatsEl.style.display = 'none';
        footerEl.style.display = 'none';
    });
});
