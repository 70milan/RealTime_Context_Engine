// streaming-ai.js - Stream AI response handler
// Override btnGenerate to use streaming endpoint

window.shouldClearTranscriptOnNextInput = false;

/**
 * Returns color thresholds for all status bar metrics based on the active model.
 * Calibrated for a 45-minute technical interview session.
 *
 * Model tiers (by speed + pricing):
 *  - gpt-5+        : reasoning models — slow TTFT (internal thinking), pricey
 *  - gpt-4-turbo   : moderately slow, ~$10/1M in  → full session ~$1.20
 *  - gpt-4 (exact) : slowest classic,  ~$30/1M in  → full session ~$3.00
 *  - gpt-4o / mini : fast, cheap,      ~$2.50/1M in → full session ~$0.35
 *  - gpt-3.5-turbo : fastest, cheapest
 */
function getModelThresholds(model) {
    const m = (model || '').toLowerCase();
    if (m.startsWith('gpt-5')) {
        // Reasoning models: long think time, pricier
        return { ttft: [8, 20], tt: [30, 70], inTok: [20000, 50000], outTok: [5000, 15000], cost: [0.35, 1.00] };
    } else if (m === 'gpt-4' || m.startsWith('gpt-4-0')) {
        // GPT-4 classic: slow, ~$30/1M in — full session ~$3
        return { ttft: [3, 8], tt: [20, 50], inTok: [20000, 50000], outTok: [5000, 15000], cost: [1.00, 2.20] };
    } else if (m.includes('turbo')) {
        // GPT-4-turbo: moderate speed, ~$10/1M in — full session ~$1.20
        return { ttft: [2, 5], tt: [12, 30], inTok: [20000, 50000], outTok: [5000, 15000], cost: [0.40, 0.90] };
    } else {
        // GPT-4o, gpt-4o-mini, gpt-3.5-turbo — fast, cheap (~$0.35 session)
        return { ttft: [1.5, 3], tt: [6, 15], inTok: [20000, 50000], outTok: [5000, 15000], cost: [0.12, 0.28] };
    }
}

function colorByThreshold(value, low, high) {
    return value < low
        ? 'rgba(100, 220, 160, 0.9)'   // green
        : value < high
            ? 'rgba(220, 185, 90, 0.9)'  // yellow
            : 'rgba(220, 110, 110, 0.9)'; // red
}

// Global: Format text with code blocks for conversation entries
window.formatConvoText = function (text) {
    if (!text) return '';
    let formatted = text;
    const codeBlocks = [];
    const inlineCodeBlocks = [];

    // Normalize line endings
    formatted = formatted.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    // Fenced code blocks: ```lang\n...\n``` (lenient: handles variations)
    formatted = formatted.replace(/`{3,}\s*([a-zA-Z0-9_#\+\-]+)?\s*\n([\s\S]*?)\n?\s*`{3,}/g, (match, lang, code) => {
        const language = lang || 'plaintext';
        const trimmedCode = code.replace(/^\n+|\n+$/g, '');
        const escapedCode = trimmedCode.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const placeholder = `___CONVO_CODE_${codeBlocks.length}___`;
        codeBlocks.push(`<pre style="background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.1);border-radius:4px;padding:8px;margin:4px 0;overflow-x:auto;"><code class="language-${language}" style="font-size:10px;line-height:1.3;">${escapedCode}</code></pre>`);
        return placeholder;
    });

    // Inline code: `code`
    formatted = formatted.replace(/`([^`]+)`/g, (match, code) => {
        const escapedCode = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const placeholder = `___CONVO_INLINE_${inlineCodeBlocks.length}___`;
        inlineCodeBlocks.push(`<code style="background:rgba(255,255,255,0.08);padding:1px 4px;border-radius:3px;font-size:10px;">${escapedCode}</code>`);
        return placeholder;
    });

    // Remove ** asterisks specifically for language labels before code blocks, or format as bold 
    // We parse basic bold **text** to <strong>text</strong> so asterisks don't show
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Remove markdown headings (e.g., ### Python: -> Python:)
    formatted = formatted.replace(/^#{1,6}\s+/gm, '');

    // Newlines to <br>
    formatted = formatted.replace(/\n/g, '<br>');

    // Restore placeholders
    codeBlocks.forEach((block, i) => {
        formatted = formatted.replace(`___CONVO_CODE_${i}___`, block);
    });
    inlineCodeBlocks.forEach((code, i) => {
        formatted = formatted.replace(`___CONVO_INLINE_${i}___`, code);
    });

    return formatted;
};

function initializeStreamingAI() {
    console.log('[STREAM] Initializing streaming AI...');

    // Store original implementation
    const originalOnClick = btnGenerate.onclick;

    btnGenerate.onclick = async function () {
        if (!window.isSessionActive) {
            window.showSessionError();
            return;
        }

        const transcriptArea = document.getElementById('transcript-area');
        const responseArea = document.getElementById('response-area');
        const transcriptSection = document.getElementById('transcript-section');
        const responseSection = document.getElementById('response-section');
        const btnGenerate = document.getElementById('btn-generate');

        if (!transcriptArea || !responseArea) return;

        const transcript = transcriptArea.innerText.trim();
        if (!transcript && !capturedScreenshot) {
            responseArea.innerText = 'No transcript or screenshot to process.';
            return;
        }

        btnGenerate.classList.add('active');
        responseArea.innerText = 'Generating...';
        const startTime = Date.now();
        const ttftEl = document.getElementById('response-time-ttft');
        const ttEl = document.getElementById('response-time-tt');

        try {
            const requestBody = {
                transcript: transcript || 'Analyze this screenshot',
                role: window.sessionTargetRole || '',
                target_language: window.sessionTargetLanguage || '',
                save_to_context: true,
                text_model: window.selectedModel || 'gpt-3.5-turbo'
            };

            if (capturedScreenshot) {
                requestBody.screenshot = capturedScreenshot;
            }

            // Use STREAMING endpoint
            const res = await fetch('http://127.0.0.1:5050/ai/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            if (!res.ok) {
                throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            }

            // Clear and start streaming
            let fullResponse = '';
            let usedModel = '';
            let responseCost = 0;
            let responseInTokens = 0;
            let responseOutTokens = 0;
            let ttft = 0; // time to first token
            let totalTime = 0;
            let firstChunkReceived = false;

            // Read stream with proper SSE line buffering
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split('\n');
                // Keep the last part in buffer (may be incomplete)
                buffer = parts.pop();

                for (const line of parts) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));

                            if (data.error) {
                                throw new Error(data.error);
                            }

                            if (data.chunk) {
                                if (!firstChunkReceived) {
                                    firstChunkReceived = true;
                                    ttft = (Date.now() - startTime) / 1000;
                                    if (ttftEl) {
                                        const th = getModelThresholds(window.selectedModel);
                                        ttftEl.innerText = ttft.toFixed(1) + 's';
                                        ttftEl.style.color = colorByThreshold(ttft, th.ttft[0], th.ttft[1]);
                                    }
                                }
                                fullResponse += data.chunk;
                                responseArea.innerText = fullResponse;
                                responseArea.scrollTop = responseArea.scrollHeight;
                            }

                            if (data.done) {
                                console.log('[STREAM] Complete');
                                const th = getModelThresholds(window.selectedModel);

                                // Use backend TTFT if available (more accurate)
                                if (data.ttft && data.ttft > 0) {
                                    ttft = data.ttft;
                                    if (ttftEl) {
                                        ttftEl.innerText = ttft.toFixed(1) + 's';
                                        ttftEl.style.color = colorByThreshold(ttft, th.ttft[0], th.ttft[1]);
                                    }
                                }
                                if (data.total_time && data.total_time > 0) {
                                    totalTime = data.total_time;
                                    if (ttEl) {
                                        ttEl.innerText = totalTime.toFixed(1) + 's';
                                        ttEl.style.color = colorByThreshold(totalTime, th.tt[0], th.tt[1]);
                                    }
                                }
                                // Capture per-response cost and tokens
                                if (data.response_cost !== undefined) responseCost = data.response_cost;
                                if (data.response_in_tokens !== undefined) responseInTokens = data.response_in_tokens;
                                if (data.response_out_tokens !== undefined) responseOutTokens = data.response_out_tokens;

                                // Update API cost/token display with model-aware color thresholds
                                if (data.usage && data.usage.total_cost !== undefined) {
                                    const apiCostEl = document.getElementById('api-cost');
                                    const apiInEl = document.getElementById('api-usage-input');
                                    const apiOutEl = document.getElementById('api-usage-output');

                                    if (apiInEl && data.usage.input_tokens !== undefined) {
                                        const inTok = data.usage.input_tokens;
                                        apiInEl.innerText = inTok.toLocaleString();
                                        apiInEl.style.color = colorByThreshold(inTok, th.inTok[0], th.inTok[1]);
                                    }
                                    if (apiOutEl && data.usage.output_tokens !== undefined) {
                                        const outTok = data.usage.output_tokens;
                                        apiOutEl.innerText = outTok.toLocaleString();
                                        apiOutEl.style.color = colorByThreshold(outTok, th.outTok[0], th.outTok[1]);
                                    }
                                    if (apiCostEl) {
                                        const cost = data.usage.total_cost;
                                        apiCostEl.innerText = cost < 1.00 ? (cost * 100).toFixed(2) + '¢' : '$' + cost.toFixed(2);
                                        apiCostEl.style.color = colorByThreshold(cost, th.cost[0], th.cost[1]);
                                    }
                                }
                                // Show which model was used in status bar
                                if (data.model) {
                                    const statusTextEl = document.getElementById('status-text');
                                    if (statusTextEl) {
                                        // Reset status text
                                        statusTextEl.innerText = window.isSessionActive ? 'Session Running' : 'Ready';

                                        // Store model name for convo capture (badge added after formatting)
                                        const displayName = data.model;
                                        usedModel = displayName;
                                    }
                                }
                            }
                        } catch (jsonError) {
                            // Re-throw API errors, only ignore actual JSON parse failures
                            if (jsonError instanceof SyntaxError) {
                                console.warn('[STREAM] Malformed JSON:', line);
                            } else {
                                throw jsonError;
                            }
                        }
                    }
                }
            }

            // If stream ended with no content, show error
            if (!fullResponse.trim()) {
                const modelName = window.selectedModel || 'unknown';
                responseArea.innerText = `Error: No response from model "${modelName}".\n\nThe model may have rejected the request. Try a different model or check the backend console for details.`;
                btnGenerate.classList.remove('active');
                return;
            }

            // Format complete response
            let formattedResponse = fullResponse;
            const codeBlocks = [];
            const inlineCodeBlocks = [];

            // Normalize ALL line endings to \n (GPT-5/reasoning models may use \r\n or \r)
            formattedResponse = formattedResponse.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

            // Match fenced code blocks: 3+ backticks, optional language, content, closing backticks
            // Lenient regex: handles languages with symbols (c++, c#) and whitespace variations
            formattedResponse = formattedResponse.replace(/`{3,}\s*([a-zA-Z0-9_#\+\-]+)?\s*\n([\s\S]*?)\n?\s*`{3,}/g, (match, lang, code) => {
                const language = lang || 'plaintext';
                const trimmedCode = code.replace(/^\n+|\n+$/g, '');
                const escapedCode = trimmedCode.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                const placeholder = `___CODE_BLOCK_${codeBlocks.length}___`;
                const copyBtnHtml = `<span class="copy-code-btn" onclick="copyCodeBlock(this)" style="position: absolute; top: 8px; right: 12px; color: rgba(255,255,255,0.4); font-size: 11px; cursor: pointer; transition: all 0.2s; z-index: 10; font-family: monospace;" onmouseover="this.style.color='#fff';" onmouseout="this.style.color='rgba(255,255,255,0.4)';">[copy]</span>`;
                codeBlocks.push(`<div style="position: relative; margin: 8px 0;">${copyBtnHtml}<pre style="margin: 0; padding-top: 36px;"><code class="language-${language}">${escapedCode}</code></pre></div>`);
                return placeholder;
            });

            formattedResponse = formattedResponse.replace(/`([^`]+)`/g, (match, code) => {
                const escapedCode = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                const placeholder = `___INLINE_CODE_${inlineCodeBlocks.length}___`;
                inlineCodeBlocks.push(`<code>${escapedCode}</code>`);
                return placeholder;
            });

            // Handle Markdown bold **text**
            formattedResponse = formattedResponse.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

            // Remove markdown headings (e.g., ### Python: -> Python:)
            formattedResponse = formattedResponse.replace(/^#{1,6}\s+/gm, '');

            formattedResponse = formattedResponse.replace(/\n/g, '<br>');

            codeBlocks.forEach((block, i) => {
                formattedResponse = formattedResponse.replace(`___CODE_BLOCK_${i}___`, block);
            });

            inlineCodeBlocks.forEach((code, i) => {
                formattedResponse = formattedResponse.replace(`___INLINE_CODE_${i}___`, code);
            });

            responseArea.innerHTML = formattedResponse;

            // Add styled model badge in footer, right-aligned
            // Add styled model badge as a fixed footer, right-aligned
            if (usedModel) {
                const modelBadge = document.createElement('div');
                modelBadge.className = 'model-signature';
                const displayModel = usedModel.replace(/\bgpt\b/gi, 'GPT').toUpperCase();
                let timeString = '';
                if (ttft > 0 && totalTime > 0) {
                    timeString = ` (${ttft.toFixed(1)}s START / ${totalTime.toFixed(1)}s TOTAL)`;
                } else if (ttft > 0) {
                    timeString = ` (${ttft.toFixed(1)}s)`;
                }
                modelBadge.innerHTML = '<span style="color: #FF1493; margin-right: 4px;">—</span><span style="color: #888; font-weight: 500;">' + displayModel + timeString + '</span>';
                responseArea.appendChild(modelBadge);
            }

            responseArea.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });

            transcriptSection.classList.add('compact');
            responseSection.classList.add('expanded');
            responseArea.scrollTop = 0;

            // === Capture to Conversation So Far (WhatsApp-style chat) ===
            const convoArea = document.getElementById('conversation-area');
            if (convoArea) {
                const pairDiv = document.createElement('div');
                pairDiv.style.cssText = 'margin-bottom: 14px;';
                pairDiv.dataset.cost = responseCost || 0;
                pairDiv.dataset.inTokens = responseInTokens || 0;
                pairDiv.dataset.outTokens = responseOutTokens || 0;
                pairDiv.dataset.responseTime = ttft || 0;
                pairDiv.dataset.totalTime = totalTime || 0;
                pairDiv.dataset.timestamp = new Date().toISOString();

                const entryTime = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
                const wasScreenshot = requestBody.screenshot;

                // ── USER BUBBLE (right-aligned) ──────────────────────────────
                const userRow = document.createElement('div');
                userRow.style.cssText = 'display: flex; justify-content: flex-end; margin-bottom: 6px;';
                const userBubble = document.createElement('div');
                userBubble.style.cssText = [
                    'max-width: 75%; background: rgba(60,60,70,0.7);',
                    'border: 1px solid rgba(255,255,255,0.08); border-radius: 14px 14px 3px 14px;',
                    'padding: 8px 12px; font-size: 11px; color: rgba(255,255,255,0.75); line-height: 1.5;',
                    'word-break: break-word;'
                ].join('');
                if (wasScreenshot) {
                    const labelText = transcript
                        ? `<div style="margin-bottom:6px;">${window.formatConvoText ? window.formatConvoText(transcript) : transcript}</div>`
                        : '';
                    userBubble.innerHTML = `<div style="font-size:9px;color:rgba(255,255,255,0.35);margin-bottom:4px;letter-spacing:0.5px;">📷 SCREEN CAPTURE · ${entryTime}</div>${labelText}<img src="${wasScreenshot}" style="max-width:100%;border-radius:6px;border:1px solid rgba(255,255,255,0.12);display:block;">`;
                } else {
                    const formattedInput = window.formatConvoText ? window.formatConvoText(transcript) : transcript;
                    userBubble.innerHTML = `<div style="font-size:9px;color:rgba(255,255,255,0.3);margin-bottom:3px;letter-spacing:0.5px;">${entryTime}</div>${formattedInput}`;
                }
                userRow.appendChild(userBubble);
                pairDiv.appendChild(userRow);

                // ── AI BUBBLE (left-aligned) ─────────────────────────────────
                const th = getModelThresholds(window.selectedModel);
                const aiRow = document.createElement('div');
                aiRow.style.cssText = 'display: flex; justify-content: flex-start; margin-bottom: 5px;';
                const aiBubble = document.createElement('div');
                aiBubble.style.cssText = [
                    'max-width: 80%; background: rgba(30,40,35,0.7);',
                    'border: 1px solid rgba(100,255,150,0.12); border-radius: 14px 14px 14px 3px;',
                    'padding: 8px 12px; font-size: 11px; color: rgba(220,240,225,0.85); line-height: 1.5;',
                    'word-break: break-word; max-height: 300px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;'
                ].join('');

                const modelLabel = usedModel ? usedModel.toUpperCase() : 'AI';
                const cleanResponse = fullResponse.replace(/\n{3,}/g, '\n').replace(/\[Model Used:.*\]/, '').trim();
                const formattedConvo = window.formatConvoText ? window.formatConvoText(cleanResponse) : cleanResponse;

                // Header row: model · time  +  [copy] right-aligned
                const aiHeader = document.createElement('div');
                aiHeader.style.cssText = 'display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;';
                aiHeader.innerHTML = `
                    <span style="font-size:9px;color:rgba(100,255,150,0.4);letter-spacing:0.5px;">${modelLabel} · ${entryTime}</span>
                    <span style="font-size:9px;color:rgba(255,255,255,0.25);font-family:monospace;cursor:pointer;padding:1px 5px;border-radius:3px;border:1px solid rgba(255,255,255,0.08);transition:all 0.15s;"
                          onmouseover="this.style.color='#fff';this.style.borderColor='rgba(255,255,255,0.25)';"
                          onmouseout="this.style.color='rgba(255,255,255,0.25)';this.style.borderColor='rgba(255,255,255,0.08)';"
                          onclick="
                            const txt = this.closest('[data-timestamp]').querySelector('.ai-body').innerText;
                            navigator.clipboard.writeText(txt);
                            this.textContent='copied!';
                            setTimeout(()=>this.textContent='[copy]',2000);
                          ">[copy]</span>`;

                // Body: formatted response
                const aiBody = document.createElement('div');
                aiBody.className = 'ai-body';
                aiBody.style.cssText = 'flex: 1; min-height: 0;';
                aiBody.innerHTML = formattedConvo;
                aiBody.querySelectorAll('pre code').forEach(block => {
                    if (typeof hljs !== 'undefined') hljs.highlightElement(block);
                });

                // Footer: stats strip inside bubble
                const fmt = (v, low, high) => `<span style="color:${colorByThreshold(v, low, high)}">${v.toFixed(1)}s</span>`;
                const costFmt = responseCost < 1 ? (responseCost * 100).toFixed(3) + '¢' : '$' + responseCost.toFixed(3);
                const aiFooter = document.createElement('div');
                aiFooter.style.cssText = 'display: flex; flex-wrap: wrap; gap: 6px; font-size: 9px; font-family: monospace; color: rgba(255,255,255,0.2); letter-spacing: 0.3px; padding-top: 5px; border-top: 1px solid rgba(100,255,150,0.07); flex-shrink: 0;';
                aiFooter.innerHTML = [
                    `TTFT ${ttft > 0 ? fmt(ttft, th.ttft[0], th.ttft[1]) : '<span>--</span>'}`,
                    `TT ${totalTime > 0 ? fmt(totalTime, th.tt[0], th.tt[1]) : '<span>--</span>'}`,
                    `IN <span style="color:rgba(180,180,180,0.4)">${responseInTokens.toLocaleString()}</span>`,
                    `OUT <span style="color:rgba(180,180,180,0.4)">${responseOutTokens.toLocaleString()}</span>`,
                    `<span style="color:rgba(180,180,180,0.35)">${costFmt}</span>`
                ].join('<span style="opacity:0.25"> · </span>');

                aiBubble.appendChild(aiHeader);
                aiBubble.appendChild(aiBody);
                aiBubble.appendChild(aiFooter);
                aiRow.appendChild(aiBubble);
                pairDiv.appendChild(aiRow);

                convoArea.appendChild(pairDiv);
                convoArea.scrollTop = convoArea.scrollHeight;

                // Send live update to the floating conversation window
                ipcRenderer.send('convo-update', {
                    question: wasScreenshot
                        ? ('📷 (screenshot)' + (transcript ? ' ' + transcript : ''))
                        : transcript,
                    response: formattedConvo,
                    model: usedModel,
                    timestamp: new Date().toISOString(),
                    ttft: ttft,
                    totalTime: totalTime,
                    responseInTokens: responseInTokens,
                    responseOutTokens: responseOutTokens,
                    responseCost: responseCost
                });

                // Update cumulative avg TTFT / TT in modal footer
                const allEntries = convoArea.querySelectorAll('[data-response-time]');
                let sumTtft = 0, sumTt = 0, validTtft = 0, validTt = 0;
                allEntries.forEach(el => {
                    const rt = parseFloat(el.dataset.responseTime || 0);
                    const tt = parseFloat(el.dataset.totalTime || 0);
                    if (rt > 0) { sumTtft += rt; validTtft++; }
                    if (tt > 0) { sumTt += tt; validTt++; }
                });
                const avgStatsEl = document.getElementById('conversation-modal-avg-stats');
                const avgTtftEl = document.getElementById('avg-ttft-val');
                const avgTtEl = document.getElementById('avg-tt-val');
                const countEl = document.getElementById('avg-exchange-count');
                if (avgStatsEl) avgStatsEl.style.display = 'flex';
                if (countEl) countEl.textContent = validTtft;
                if (avgTtftEl && validTtft > 0) {
                    const avg = sumTtft / validTtft;
                    avgTtftEl.textContent = avg.toFixed(1) + 's';
                    avgTtftEl.style.color = colorByThreshold(avg, th.ttft[0], th.ttft[1]);
                }
                if (avgTtEl && validTt > 0) {
                    const avg = sumTt / validTt;
                    avgTtEl.textContent = avg.toFixed(1) + 's';
                    avgTtEl.style.color = colorByThreshold(avg, th.tt[0], th.tt[1]);
                }
            }

            if (capturedScreenshot) {
                capturedScreenshot = null;
                const btnScreenEl = document.getElementById('btn-screen');
                if (btnScreenEl) btnScreenEl.style.backgroundColor = '#444';
            }

            btnGenerate.innerText = 'Generate AI';
            btnGenerate.classList.remove('active');
            // Flag transcript to clear on next user input instead of flashing to empty immediately
            window.shouldClearTranscriptOnNextInput = true;
        } catch (e) {
            console.error('AI Generation Error:', e);
            responseArea.innerText = `Error: ${e.message}\n\nCheck if backend is running on port 5050.`;
            const btnGenEl = document.getElementById('btn-generate');
            if (btnGenEl) btnGenEl.classList.remove('active');
        }
    };



    // Scroll helper for global shortcuts
    window.scrollAIOutput = (direction) => {
        const el = document.getElementById('response-area');
        if (el) {
            el.scrollTop += (direction * 50); // increased scroll speed
        }
    };

    console.log('[STREAM] Streaming AI initialized successfully!');
}

// Initialize after DOM loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(initializeStreamingAI, 100);
    });
} else {
    setTimeout(initializeStreamingAI, 100);
}

window.copyCodeBlock = function (btn) {
    const pre = btn.nextElementSibling;
    const code = pre ? pre.querySelector('code') : null;
    if (code) {
        navigator.clipboard.writeText(code.innerText || code.textContent).then(() => {
            btn.innerText = '[copied!]';
            btn.style.color = '#4CAF50';
            setTimeout(() => {
                btn.innerText = '[copy]';
                btn.style.color = 'rgba(255,255,255,0.4)';
            }, 2000);
        });
    }
};
