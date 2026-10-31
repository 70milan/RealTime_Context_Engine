// update-signature.js — verifies a downloaded update before it is installed.
//
// The installer must carry an intact Authenticode signature from OUR signing
// certificate (pinned by thumbprint). Anything else — unsigned, tampered, or
// signed by any other cert, including the retired ones whose keys leaked — is
// rejected. Returns null when OK, or an error string (electron-updater's contract).
const { execFile } = require('child_process');

// Current signing cert (CN=mjulez70, created 2026-10-30, expires 2029-10-30).
// When rotating, add the new thumbprint here one release BEFORE switching the
// build to the new cert, then remove the old one.
const TRUSTED_SIGNER_THUMBPRINTS = ['79CFED1588EA80B24F3E3828C19C8A5B17C3E623'];

// Get-AuthenticodeSignature reports a self-signed cert whose root isn't trusted
// on this PC as 'UnknownError' even when the file hash is intact; a modified file
// is 'HashMismatch'. Since the signer is pinned, an untrusted root is acceptable.
const ACCEPTED_STATUS = new Set(['Valid', 'UnknownError']);

function verifyUpdateSignature(filePath) {
    return new Promise((resolve) => {
        // Path goes through an env var, never into the command string
        const ps = "$s = Get-AuthenticodeSignature -LiteralPath $env:UPDATE_FILE; " +
            "[pscustomobject]@{ Status = [string]$s.Status; Thumb = [string]$s.SignerCertificate.Thumbprint } | ConvertTo-Json -Compress";
        execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], {
            env: { ...process.env, UPDATE_FILE: filePath },
            timeout: 30000,
            windowsHide: true
        }, (err, stdout) => {
            if (err) return resolve(`Update signature check failed: ${err.message}`);
            let r;
            try { r = JSON.parse(String(stdout).trim()); } catch (e) { return resolve('Update signature check returned unreadable output'); }
            const thumb = (r.Thumb || '').toUpperCase();
            if (ACCEPTED_STATUS.has(r.Status) && TRUSTED_SIGNER_THUMBPRINTS.includes(thumb)) return resolve(null);
            resolve(`Update rejected: signature status=${r.Status || 'none'}, signer=${thumb || 'none'}`);
        });
    });
}

module.exports = { verifyUpdateSignature, TRUSTED_SIGNER_THUMBPRINTS };
