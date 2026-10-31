// format.js — the ONE place AI/transcript text is turned into HTML.
//
// SECURITY: injected HTML could run script in the app window (and, before the
// preload/contextIsolation change, reach Node via require('child_process')).
// AI answers and transcribed speech are attacker-influenceable (a spoken or
// on-screen "<img onerror=...>" gets echoed back), so we escape EVERYTHING
// first and only then add our own tags. Never insert un-escaped text with
// innerHTML — use escapeHtml() or textContent.

window.escapeHtml = function (value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
};

// variant: 'response' (main answer panel, with [copy] buttons) or 'convo' (compact chat bubbles)
function renderMarkdownLite(text, variant) {
    if (!text) return '';
    const codeBlocks = [];
    const inlineCodeBlocks = [];

    // Normalize line endings (GPT-5/reasoning models may use \r\n or \r), then escape it all
    let formatted = window.escapeHtml(String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n'));

    // Fenced code blocks: 3+ backticks, optional language, content, closing backticks.
    // Content is already escaped; the language is limited to [A-Za-z0-9_#+-].
    formatted = formatted.replace(/`{3,}\s*([a-zA-Z0-9_#\+\-]+)?\s*\n([\s\S]*?)\n?\s*`{3,}/g, (match, lang, code) => {
        const language = lang || 'plaintext';
        const trimmedCode = code.replace(/^\n+|\n+$/g, '');
        const placeholder = `___CODE_BLOCK_${codeBlocks.length}___`;
        if (variant === 'response') {
            const copyBtnHtml = `<span class="copy-code-btn" onclick="copyCodeBlock(this)" style="position:absolute;top:8px;right:12px;color:rgba(255,255,255,0.4);font-size:11px;cursor:default;z-index:10;font-family:monospace;">[copy]</span>`;
            codeBlocks.push(`<div style="position:relative;margin:8px 0;">${copyBtnHtml}<pre style="margin:0;padding-top:36px;"><code class="language-${language}">${trimmedCode}</code></pre></div>`);
        } else {
            codeBlocks.push(`<pre style="background:rgba(0,0,0,0.4);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:8px;margin:4px 0;overflow-x:auto;"><code class="language-${language}" style="font-size:10px;line-height:1.3;">${trimmedCode}</code></pre>`);
        }
        return placeholder;
    });

    // Inline code: `code`
    formatted = formatted.replace(/`([^`]+)`/g, (match, code) => {
        const placeholder = `___INLINE_CODE_${inlineCodeBlocks.length}___`;
        inlineCodeBlocks.push(variant === 'response'
            ? `<code>${code}</code>`
            : `<code style="background:rgba(255,255,255,0.08);padding:1px 4px;border-radius:6px;font-size:10px;">${code}</code>`);
        return placeholder;
    });

    // Bold **text** → <strong>; drop markdown heading markers (### Python: → Python:)
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/^#{1,6}\s+/gm, '');
    formatted = formatted.replace(/\n/g, '<br>');

    codeBlocks.forEach((block, i) => { formatted = formatted.replace(`___CODE_BLOCK_${i}___`, () => block); });
    inlineCodeBlocks.forEach((code, i) => { formatted = formatted.replace(`___INLINE_CODE_${i}___`, () => code); });
    return formatted;
}

window.formatConvoText = (text) => renderMarkdownLite(text, 'convo');
window.formatResponseText = (text) => renderMarkdownLite(text, 'response');
