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
