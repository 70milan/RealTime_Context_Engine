// bump-version.js - Runs before each build ("prebuild"): sets the next version and writes
// release-notes.md, which becomes the GitHub release text and the "What's new" list in the
// app's update prompt.
//
// Numbering from 3.0.0 on: the last number counts 0..27, the middle 0..11, then the first
// goes up:  3.0.0 ... 3.0.27, 3.1.0 ... 3.11.27, 4.0.0 ...
// Anything older than 3.0.0 jumps straight to 3.0.0.
//
// Release notes: if release-notes.md already mentions the new version (written by hand),
// it is kept. Otherwise it is generated from the commits since the last release tag
// (build-all.bat tags each published version as vX.Y.Z). With OPENAI_API_KEY set, gpt-4o-mini
// rewrites them as short user-facing bullets; without it, the commit bullets are used as-is.
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const PATCH_MAX = 27;
const MINOR_MAX = 11;
const FIRST = [3, 0, 0];

function nextVersion(version) {
    const [major, minor, patch] = version.split('.').map(Number);
    if (major < FIRST[0]) return FIRST.join('.');
    if (patch < PATCH_MAX) return `${major}.${minor}.${patch + 1}`;
    if (minor < MINOR_MAX) return `${major}.${minor + 1}.0`;
    return `${major + 1}.0.0`;
}

const git = (args) => execSync(`git ${args}`, { cwd: path.join(__dirname, '..'), encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });

// Bullets from the commits since the last release: each commit's "- " body lines (wrapped
// lines joined), or its subject if it has none. Version-bump commits and trailers are skipped.
function commitBullets() {
    let base = '';
    try { base = git('describe --tags --abbrev=0 --match "v*"').trim(); } catch (e) { }
    const range = base ? `${base}..HEAD` : '-n 15 HEAD';
    const log = git(`log ${range} --no-merges --pretty=format:%s%x1f%b%x1e`);
    const bullets = [];
    for (const entry of log.split('\x1e')) {
        const [subject, body = ''] = entry.trim().split('\x1f');
        if (!subject || /^release\s+\d/i.test(subject)) continue;
        const fromBody = [];
        for (const line of body.split('\n')) {
            if (/^(co-authored-by|claude-session|signed-off-by):/i.test(line.trim())) continue;
            if (/^\s*-\s+/.test(line)) fromBody.push(line.replace(/^\s*-\s+/, '').trim());
            else if (/^\s{2,}\S/.test(line) && fromBody.length) fromBody[fromBody.length - 1] += ' ' + line.trim();
        }
        bullets.push(...(fromBody.length ? fromBody : [subject.trim()]));
    }
    return { base, bullets };
}

async function rewriteForUsers(bullets, version) {
    const key = process.env.OPENAI_API_KEY;
    if (!key || !bullets.length) return null;
    try {
        const res = await fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
            body: JSON.stringify({
                model: 'gpt-4o-mini',
                temperature: 0.2,
                messages: [
                    { role: 'system', content: 'You write release notes for a desktop interview-assistant app. Turn the developer change list into at most 8 short bullets for users: what they can now do or what got better, in plain words. Skip internal changes (refactors, tests, build, endpoints) unless users notice them. One line each, starting with "- ". No other text.' },
                    { role: 'user', content: `Version ${version}. Changes:\n` + bullets.map(b => '- ' + b).join('\n') },
                ],
            }),
        });
        const json = await res.json();
        const text = (json.choices && json.choices[0].message.content || '').trim();
        const lines = text.split('\n').map(l => l.trim()).filter(l => l.startsWith('- '));
        return lines.length ? lines : null;
    } catch (e) {
        console.log(`[NOTES] AI rewrite failed (${e.message}); using the commit bullets`);
        return null;
    }
}

async function main() {
    const packagePath = path.join(__dirname, 'package.json');
    const pkg = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
    const oldVersion = pkg.version;
    const newVersion = nextVersion(oldVersion);
    pkg.version = newVersion;
    fs.writeFileSync(packagePath, JSON.stringify(pkg, null, 2) + '\n');
    console.log(`Version bumped: ${oldVersion} -> ${newVersion}`);

    const notesPath = path.join(__dirname, 'release-notes.md');
    const existing = fs.existsSync(notesPath) ? fs.readFileSync(notesPath, 'utf8') : '';
    if (existing.includes(`Version ${newVersion}`)) {
        console.log(`[NOTES] Keeping the hand-written notes for ${newVersion}`);
        return;
    }
    try {
        const dirty = git('status --porcelain --untracked-files=no').split('\n')
            .filter(l => l.trim() && !/package\.json$|release-notes\.md$/.test(l));
        if (dirty.length) console.log(`[NOTES] ${dirty.length} changed file(s) aren't committed: they're in the build but not in these notes. Commit first for complete notes.`);
        const { base, bullets } = commitBullets();
        const lines = (await rewriteForUsers(bullets, newVersion)) || bullets.slice(0, 14).map(b => '- ' + b);
        if (!lines.length) {
            console.log('[NOTES] No commits since the last release: the update prompt will show no "What\'s new".');
            fs.writeFileSync(notesPath, `Version ${newVersion}\n`);
            return;
        }
        fs.writeFileSync(notesPath, `Version ${newVersion}\n\n${lines.join('\n')}\n`);
        console.log(`[NOTES] release-notes.md written from ${base ? 'commits since ' + base : 'the last 15 commits'}${process.env.OPENAI_API_KEY ? ' (rewritten for users)' : ''}:`);
        console.log(lines.map(l => '   ' + l).join('\n'));
    } catch (e) {
        console.log(`[NOTES] Could not generate release notes (${e.message}); keeping release-notes.md as it is`);
    }
}

if (require.main === module) main();
module.exports = { nextVersion, commitBullets };
