const { autoUpdater } = require('electron-updater');

autoUpdater.autoDownload = false;
autoUpdater.allowPrerelease = true;

// Force it to look at the current directory's package.json
autoUpdater.forceDevUpdateConfig = true;

console.log('Starting update check in dev mode...');

autoUpdater.on('error', (err) => {
    console.error('Update Error:', err.message);
});

autoUpdater.on('update-available', (info) => {
    console.log('Update available:', info.version);
});

autoUpdater.on('update-not-available', (info) => {
    console.log('Update not available. Latest version:', info.version);
});

autoUpdater.checkForUpdates().then((res) => {
    console.log('Check finished:', res);
}).catch(err => {
    console.error('Failed call:', err);
});
