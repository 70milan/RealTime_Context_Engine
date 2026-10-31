// backend-auth.js — must load before any other script that talks to the backend.
// Fetches the per-launch backend token from the main process and attaches it to
// every request to the local backend, so the backend can reject callers that
// aren't this app (e.g. a web page open in the user's browser).
(function () {
    const BACKEND_ORIGIN = 'http://127.0.0.1:5050';
    let token = '';
    try {
        token = window.ipcBridge.sendSync('get-backend-token') || '';
    } catch (e) {
        console.error('[AUTH] Could not get backend token:', e);
    }

    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (token && url.startsWith(BACKEND_ORIGIN)) {
            const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
            headers.set('X-App-Token', token);
            init = { ...init, headers };
        }
        return nativeFetch(input, init);
    };

    // WebSockets can't carry custom headers, so the token goes in the query string.
    window.backendWsUrl = (path) =>
        `ws://127.0.0.1:5050${path}` + (token ? `?token=${encodeURIComponent(token)}` : '');
})();
