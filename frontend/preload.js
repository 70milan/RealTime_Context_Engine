// preload.js — the only bridge between the web pages and Electron.
//
// Windows run with contextIsolation on and nodeIntegration off, so page scripts
// (and any HTML that slips into innerHTML) cannot call require() or reach Node.
// Pages get window.ipcBridge, which only talks on the channels listed here.
// (Not exposed as 'ipcRenderer': bridged globals can't be redeclared, and the
// page scripts declare their own `const ipcRenderer = window.ipcBridge`.)
const { contextBridge, ipcRenderer } = require('electron');

// renderer -> main
const SEND = new Set([
    'clear-convo-history', 'close-app', 'convo-update', 'hide-convo-window',
    'load-convo-history', 'log-error', 'set-convo-title', 'toggle-convo-window',
    'manual-update-check', 'update-accept', 'update-decline', 'update-restart', 'update-later',
    'expand-from-mini', 'focus-main-window', 'focus-convo-window',
]);
const INVOKE = new Set(['export-conversation', 'GET_SOURCES', 'get-app-version', 'reset-app', 'get-log-path']);
const SEND_SYNC = new Set(['get-backend-token']);

// main -> renderer
const ON = new Set([
    'backend-log', 'clear-convo-history', 'debug-log', 'load-convo-history',
    'render-convo-update', 'set-convo-title', 'update-check-result', 'update-log',
]);

// Edge resizing. The windows are not OS-resizable, so Windows never shows its
// resize arrows. Invisible strips on the edges (outside any drag region) start a
// resize in main.js instead, and the cursor stays the normal arrow.
const EDGE_PX = 6;
const EDGES = {
    n: `top:0;left:${EDGE_PX}px;right:${EDGE_PX}px;height:${EDGE_PX}px;`,
    s: `bottom:0;left:${EDGE_PX}px;right:${EDGE_PX}px;height:${EDGE_PX}px;`,
    w: `left:0;top:${EDGE_PX}px;bottom:${EDGE_PX}px;width:${EDGE_PX}px;`,
    e: `right:0;top:${EDGE_PX}px;bottom:${EDGE_PX}px;width:${EDGE_PX}px;`,
    nw: `top:0;left:0;width:${EDGE_PX}px;height:${EDGE_PX}px;`,
    ne: `top:0;right:0;width:${EDGE_PX}px;height:${EDGE_PX}px;`,
    sw: `bottom:0;left:0;width:${EDGE_PX}px;height:${EDGE_PX}px;`,
    se: `bottom:0;right:0;width:${EDGE_PX}px;height:${EDGE_PX}px;`,
};
window.addEventListener('DOMContentLoaded', () => {
    const style = document.createElement('style');
    style.textContent =
        '.wrh-edge{position:fixed;z-index:2147483647;background:transparent;-webkit-app-region:no-drag;cursor:default!important;}' +
        'body.mini .wrh-edge{display:none;}';
    document.head.appendChild(style);
    for (const [edge, pos] of Object.entries(EDGES)) {
        const el = document.createElement('div');
        el.className = 'wrh-edge';
        el.style.cssText = pos;
        el.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            e.stopPropagation();
            ipcRenderer.send('edge-resize-start', edge);
            const end = () => {
                ipcRenderer.send('edge-resize-end');
                window.removeEventListener('mouseup', end, true);
                window.removeEventListener('blur', end);
            };
            window.addEventListener('mouseup', end, true);
            window.addEventListener('blur', end);
        });
        document.body.appendChild(el);
    }
});

function check(set, channel) {
    if (!set.has(channel)) throw new Error(`IPC channel not allowed: ${channel}`);
}

contextBridge.exposeInMainWorld('ipcBridge', {
    send: (channel, ...args) => { check(SEND, channel); ipcRenderer.send(channel, ...args); },
    invoke: (channel, ...args) => { check(INVOKE, channel); return ipcRenderer.invoke(channel, ...args); },
    sendSync: (channel, ...args) => { check(SEND_SYNC, channel); return ipcRenderer.sendSync(channel, ...args); },
    // The real IpcRendererEvent can't cross the bridge; listeners get an empty stand-in
    on: (channel, listener) => { check(ON, channel); ipcRenderer.on(channel, (_event, ...args) => listener({}, ...args)); },
});
