// streaming-ai.js - Stream AI response handler
// Override btnGenerate to use streaming endpoint

window.shouldClearTranscriptOnNextInput = false;

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
                                        ttftEl.innerText = ttft.toFixed(1) + 's';
                                    }
                                }
                                fullResponse += data.chunk;
                                responseArea.innerText = fullResponse;
                                responseArea.scrollTop = responseArea.scrollHeight;
                            }

                            if (data.done) {
                                console.log('[STREAM] Complete');
                                // Use backend TTFT if available (more accurate)
                                if (data.ttft && data.ttft > 0) {
                                    ttft = data.ttft;
                                    if (ttftEl) {
                                        ttftEl.innerText = ttft.toFixed(1) + 's';
                                    }
                                }
                                if (data.total_time && data.total_time > 0) {
                                    totalTime = data.total_time;
                                    if (ttEl) {
                                        ttEl.innerText = totalTime.toFixed(1) + 's';
                                    }
                                }
                                // Capture per-response cost and tokens
                                if (data.response_cost !== undefined) {
                                    responseCost = data.response_cost;
                                }
                                if (data.response_in_tokens !== undefined) {
                                    responseInTokens = data.response_in_tokens;
                                }
                                if (data.response_out_tokens !== undefined) {
                                    responseOutTokens = data.response_out_tokens;
                                }
                                // Update API cost display with color gradient
                                if (data.usage && data.usage.total_cost !== undefined) {
                                    const apiCostEl = document.getElementById('api-cost');
                                    const apiInEl = document.getElementById('api-usage-input');
                                    const apiOutEl = document.getElementById('api-usage-output');

                                    if (apiInEl && data.usage.input_tokens !== undefined) {
                                        apiInEl.innerText = data.usage.input_tokens.toLocaleString();
                                    }
                                    if (apiOutEl && data.usage.output_tokens !== undefined) {
                                        apiOutEl.innerText = data.usage.output_tokens.toLocaleString();
                                    }

                                    if (apiCostEl) {
                                        const cost = data.usage.total_cost;
                                        // Show cents when under $1, dollars when $1+
                                        if (cost < 1.00) {
                                            apiCostEl.innerText = (cost * 100).toFixed(2) + '¢';
                                        } else {
                                            apiCostEl.innerText = '$' + cost.toFixed(2);
                                        }
                                        // Color gradient: green < $0.10, orange $0.10-$0.50, red > $0.50
                                        if (cost < 0.10) {
                                            apiCostEl.style.color = 'rgba(120, 200, 180, 0.85)'; // soft teal
                                        } else if (cost < 0.50) {
                                            apiCostEl.style.color = 'rgba(200, 170, 120, 0.85)'; // muted amber
                                        } else {
                                            apiCostEl.style.color = 'rgba(200, 130, 130, 0.85)'; // soft rose
                                        }
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

            // === Capture to Conversation So Far ===
            const convoArea = document.getElementById('conversation-area');
            if (convoArea) {
                const pairDiv = document.createElement('div');
                pairDiv.style.cssText = 'border: 1px solid rgba(255,255,255,0.06); border-radius: 4px; padding: 8px; background: rgba(255,255,255,0.02);';
                pairDiv.dataset.cost = responseCost || 0;
                pairDiv.dataset.inTokens = responseInTokens || 0;
                pairDiv.dataset.outTokens = responseOutTokens || 0;
                pairDiv.dataset.responseTime = ttft || 0;
                pairDiv.dataset.totalTime = totalTime || 0;
                pairDiv.dataset.timestamp = new Date().toISOString();

                // Input (transcript/question)
                const inputText = transcript || '(screenshot analysis)';
                const entryTime = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
                const qDiv = document.createElement('div');
                qDiv.style.cssText = 'color: #bbb; font-size: 11px; line-height: 1.4; margin-bottom: 6px; padding: 4px 8px; border-left: 2px solid #666; border-radius: 2px;';
                const formattedInput = window.formatConvoText ? window.formatConvoText(inputText) : inputText.substring(0, 200);
                qDiv.innerHTML = '<strong style="color: rgba(255,255,255,0.4); font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px;">Input</strong> <span style="color: rgba(255,255,255,0.25); font-size: 9px;">' + entryTime + '</span><br>' + formattedInput;
                pairDiv.appendChild(qDiv);

                // AI response (truncated for readability)
                const cleanResponse = fullResponse.replace(/\n{3,}/g, '\n').replace(/\[Model Used:.*\]/, '').trim();
                const rDiv = document.createElement('div');
                rDiv.style.cssText = 'color: #ddd; font-size: 11px; line-height: 1.4; padding: 4px 8px; border-left: 2px solid rgba(100,255,150,0.4); border-radius: 2px; max-height: 200px; overflow-y: auto;';
                // Build AI label with model and response time
                let aiLabel = 'AI';
                if (usedModel) aiLabel += ' (' + usedModel.toUpperCase() + ')';
                if (ttft > 0 && totalTime > 0) {
                    aiLabel += ` [${ttft.toFixed(1)}s START / ${totalTime.toFixed(1)}s TOTAL]`;
                } else if (ttft > 0) {
                    aiLabel += ' [' + ttft.toFixed(1) + 's]';
                }
                const formattedConvo = window.formatConvoText ? window.formatConvoText(cleanResponse) : cleanResponse.substring(0, 300);
                rDiv.innerHTML = '<strong style="color: rgba(100,255,150,0.4); font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px;">' + aiLabel + '</strong> <span style="color: rgba(255,255,255,0.25); font-size: 9px;">' + entryTime + '</span><br>' + formattedConvo;
                pairDiv.appendChild(rDiv);

                // Highlight code blocks in conversation entry
                rDiv.querySelectorAll('pre code').forEach((block) => {
                    if (typeof hljs !== 'undefined') hljs.highlightElement(block);
                });

                convoArea.appendChild(pairDiv);
                convoArea.scrollTop = convoArea.scrollHeight;
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
