const JavaScriptObfuscator = require('javascript-obfuscator');
const fs = require('fs');
const path = require('path');

const filesToObfuscate = ['setup.js', 'streaming-ai.js'];
const mode = process.argv[2]; // 'obfuscate' or 'restore'

filesToObfuscate.forEach(file => {
    const filePath = path.join(__dirname, '..', file);
    const bakPath = filePath + '.bak';

    if (mode === 'obfuscate') {
        if (!fs.existsSync(filePath)) return;

        // Backup if not already backed up
        if (!fs.existsSync(bakPath)) {
            fs.copyFileSync(filePath, bakPath);
        }

        const code = fs.readFileSync(filePath, 'utf8');
        console.log(`Obfuscating ${file}...`);

        try {
            const result = JavaScriptObfuscator.obfuscate(code, {
                compact: true,
                controlFlowFlattening: true,
                controlFlowFlatteningThreshold: 0.75,
                deadCodeInjection: true,
                deadCodeInjectionThreshold: 0.4,
                identifierNamesGenerator: 'hexadecimal',
                renameGlobals: false,
                stringArray: true,
                stringArrayEncoding: ['base64'],
                stringArrayThreshold: 0.75,
                unicodeEscapeSequence: false
            });
            fs.writeFileSync(filePath, result.getObfuscatedCode());
            console.log(`[SUCCESS] Obfuscated ${file}`);
        } catch (err) {
            console.error(`[ERROR] Failed to obfuscate ${file}:`, err);
            // Restore immediately on failure
            if (fs.existsSync(bakPath)) {
                fs.copyFileSync(bakPath, filePath);
            }
        }
    } else if (mode === 'restore') {
        if (fs.existsSync(bakPath)) {
            fs.copyFileSync(bakPath, filePath);
            fs.unlinkSync(bakPath);
            console.log(`Restored ${file} from backup.`);
        } else {
            console.log(`No backup found for ${file}, skipping restore.`);
        }
    } else {
        console.log("Usage: node obfuscate.js [obfuscate|restore]");
    }
});
