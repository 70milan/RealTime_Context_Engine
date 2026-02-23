const { app, BrowserWindow, Tray, Menu, nativeImage, globalShortcut, screen, ipcMain, desktopCapturer, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');

let tray = null;
let win = null;
let isRecording = false;
let isMiniMode = false;
let backendProcess = null;
let lastMiniPosition = null; // Remember where the mini icon was dragged to

// ============ SINGLE INSTANCE LOCK ============
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  console.log('[STEALTH] Another instance is already running. Quitting this instance.');
  app.quit();
} else {
  // Find existing instance and show/focus it instead
  app.on('second-instance', (event, commandLine, workingDirectory) => {
    if (win) {
      if (!win.isVisible()) win.show();
      if (win.isMinimized()) win.restore();

      // If we're in mini mode, don't expand automatically, just show the icon
      // But if we're not in mini mode, ensure it's front and center
      win.focus();

      console.log('[STEALTH] Brought existing application window to front.');
    }
  });
}

// ============ AUTO-UPDATER SETUP ============
autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = false;

function showUpdateOverlay(content) {
  if (!win) return;
  win.webContents.executeJavaScript(`
    (function() {
      let el = document.getElementById('update-overlay');
      if (!el) {
        el = document.createElement('div');
        el.id = 'update-overlay';
        el.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(10,10,10,0.92);z-index:99999;display:flex;align-items:center;justify-content:center;font-family:Segoe UI,Arial,sans-serif;';
        document.body.appendChild(el);
      }
      el.innerHTML = ${content};
    })()
  `);
}

function updateProgressUI(percent) {
  if (!win) return;
  win.webContents.executeJavaScript(`
    const bar = document.getElementById('update-progress-bar');
    const text = document.getElementById('update-progress-text');
    if (bar) bar.style.width = '${percent}%';
    if (text) text.textContent = '${percent}%';
  `);
}

function hideUpdateUI() {
  if (!win) return;
  win.webContents.executeJavaScript(`
    const el = document.getElementById('update-overlay');
    if (el) el.remove();
  `);
}

let updateVersion = '';

autoUpdater.on('checking-for-update', () => {
  console.log('Checking for updates...');
});

autoUpdater.on('update-available', (info) => {
  console.log('Update available:', info.version);
  updateVersion = info.version;

  // Custom in-app prompt matching app design
  const content = `\`
    <div style="background:rgba(30,30,30,0.98);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:30px 36px;text-align:center;max-width:340px;width:90%;">
      <div style="color:rgba(255,255,255,0.5);font-size:12px;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:16px;">Update Available</div>
      <div style="color:rgba(255,255,255,0.8);font-size:16px;font-weight:500;margin-bottom:6px;">Version ${info.version}</div>
      <div style="color:rgba(255,255,255,0.35);font-size:13px;margin-bottom:24px;">A new version is ready to download.</div>
      <div style="display:flex;flex-direction:column;gap:8px;">
        <button id="update-yes-btn" style="width:100%;padding:10px 0;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);border-radius:4px;color:rgba(255,255,255,0.6);font-size:12px;cursor:pointer;text-transform:uppercase;letter-spacing:1px;font-weight:500;transition:all 0.2s;"
          onmouseover="this.style.color='rgba(255,255,255,0.9)';this.style.borderColor='rgba(255,255,255,0.3)';"
          onmouseout="this.style.color='rgba(255,255,255,0.6)';this.style.borderColor='rgba(255,255,255,0.15)';">Download</button>
        <button id="update-no-btn" style="width:100%;padding:10px 0;background:none;border:1px solid rgba(255,255,255,0.08);border-radius:4px;color:rgba(255,255,255,0.35);font-size:12px;cursor:pointer;text-transform:uppercase;letter-spacing:1px;font-weight:500;transition:all 0.2s;"
          onmouseover="this.style.color='rgba(255,255,255,0.6)';this.style.borderColor='rgba(255,255,255,0.15)';"
          onmouseout="this.style.color='rgba(255,255,255,0.35)';this.style.borderColor='rgba(255,255,255,0.08)';">Skip</button>
      </div>
    </div>
  \``;

  showUpdateOverlay(content);

  // Wire up buttons via IPC
  win.webContents.executeJavaScript(`
    document.getElementById('update-yes-btn').addEventListener('click', () => {
      require('electron').ipcRenderer.send('update-accept');
    });
    document.getElementById('update-no-btn').addEventListener('click', () => {
      require('electron').ipcRenderer.send('update-decline');
    });
  `);
});

ipcMain.on('update-accept', () => {
  // Show downloading UI
  const content = `\`
    <div style="background:rgba(30,30,30,0.98);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:30px 36px;text-align:center;max-width:340px;width:90%;">
      <div style="color:rgba(255,255,255,0.5);font-size:12px;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:16px;">Downloading Update</div>
      <div style="color:rgba(255,255,255,0.4);font-size:13px;margin-bottom:18px;">v${updateVersion}</div>
      <div style="width:100%;height:4px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden;">
        <div id="update-progress-bar" style="height:100%;background:rgba(255,255,255,0.4);width:0%;transition:width 0.3s ease;border-radius:2px;"></div>
      </div>
      <div id="update-progress-text" style="color:rgba(255,255,255,0.5);font-size:13px;margin-top:12px;letter-spacing:0.5px;">0%</div>
    </div>
  \``;
  showUpdateOverlay(content);
  autoUpdater.downloadUpdate();
});

ipcMain.on('update-decline', () => {
  console.log('User declined update');
  hideUpdateUI();
});

autoUpdater.on('update-not-available', () => {
  console.log('No updates available');
  if (win) {
    win.webContents.send('update-check-result', 'latest');
  }
});

autoUpdater.on('download-progress', (progress) => {
  const percent = Math.round(progress.percent);
  console.log(`Download progress: ${percent}%`);
  updateProgressUI(percent);
});

autoUpdater.on('update-downloaded', (info) => {
  console.log('Update downloaded:', info.version);

  // Show restart prompt in-app
  const content = `\`
    <div style="background:rgba(30,30,30,0.98);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:30px 36px;text-align:center;max-width:340px;width:90%;">
      <div style="color:rgba(255,255,255,0.5);font-size:12px;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:16px;">Update Ready</div>
      <div style="color:rgba(255,255,255,0.8);font-size:16px;font-weight:500;margin-bottom:6px;">Version ${info.version}</div>
      <div style="color:rgba(255,255,255,0.35);font-size:13px;margin-bottom:24px;">Restart to apply the update.</div>
      <div style="display:flex;flex-direction:column;gap:8px;">
        <button id="update-restart-btn" style="width:100%;padding:10px 0;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);border-radius:4px;color:rgba(255,255,255,0.6);font-size:12px;cursor:pointer;text-transform:uppercase;letter-spacing:1px;font-weight:500;transition:all 0.2s;"
          onmouseover="this.style.color='rgba(255,255,255,0.9)';this.style.borderColor='rgba(255,255,255,0.3)';"
          onmouseout="this.style.color='rgba(255,255,255,0.6)';this.style.borderColor='rgba(255,255,255,0.15)';">Restart Now</button>
        <button id="update-later-btn" style="width:100%;padding:10px 0;background:none;border:1px solid rgba(255,255,255,0.08);border-radius:4px;color:rgba(255,255,255,0.35);font-size:12px;cursor:pointer;text-transform:uppercase;letter-spacing:1px;font-weight:500;transition:all 0.2s;"
          onmouseover="this.style.color='rgba(255,255,255,0.6)';this.style.borderColor='rgba(255,255,255,0.15)';"
          onmouseout="this.style.color='rgba(255,255,255,0.35)';this.style.borderColor='rgba(255,255,255,0.08)';">Later</button>
      </div>
    </div>
  \``;

  showUpdateOverlay(content);

  // Wire up buttons via IPC
  win.webContents.executeJavaScript(`
    document.getElementById('update-restart-btn').addEventListener('click', () => {
      require('electron').ipcRenderer.send('update-restart');
    });
    document.getElementById('update-later-btn').addEventListener('click', () => {
      require('electron').ipcRenderer.send('update-later');
    });
  `);
});

ipcMain.on('update-restart', () => {
  autoUpdater.quitAndInstall(true, true);
});

ipcMain.on('update-later', () => {
  console.log('User chose to install later');
  hideUpdateUI();
});

autoUpdater.on('error', (err) => {
  console.error('Auto-updater error:', err);
  if (win) {
    win.webContents.send('update-check-result', 'error', err.message);
  }
  hideUpdateUI();
});
// ============ END AUTO-UPDATER ============

function startBackend() {
  const isDev = !app.isPackaged;

  if (isDev) {
    console.log('Development mode: assuming backend runs separately');
    return;
  }

  const backendPath = path.join(process.resourcesPath, 'backend', 'WinHostSvc.exe');
  console.log('Starting backend from:', backendPath);

  backendProcess = spawn(backendPath, [], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    windowsHide: true // STEALTH: Hide the backend console window
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[BACKEND] ${data.toString()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`[BACKEND ERROR] ${data.toString()}`);
  });

  backendProcess.on('error', (err) => {
    console.error('Failed to start backend:', err);
  });

  backendProcess.on('exit', (code) => {
    console.log(`Backend exited with code ${code}`);
  });
}

function clampWindowToScreen(windowToClamp) {
  if (!windowToClamp) return;
  const currentBounds = windowToClamp.getBounds();
  const display = screen.getDisplayMatching(currentBounds);
  const workArea = display.workArea;

  let x = currentBounds.x;
  let y = currentBounds.y;

  if (x < workArea.x) x = workArea.x;
  else if (x + currentBounds.width > workArea.x + workArea.width) x = workArea.x + workArea.width - currentBounds.width;

  if (y < workArea.y) y = workArea.y;
  else if (y + currentBounds.height > workArea.y + workArea.height) y = workArea.y + workArea.height - currentBounds.height;

  if (x !== currentBounds.x || y !== currentBounds.y) {
    windowToClamp.setBounds({ x, y, width: currentBounds.width, height: currentBounds.height });
  }
}

function centerTop(width = 800, height = 600) {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  const x = Math.round((sw - width) / 2);
  const y = Math.round((sh - height) / 2);
  return { x, y, width, height };
}

function createWindow() {
  const bounds = centerTop();
  win = new BrowserWindow({
    ...bounds,
    show: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    transparent: true,
    backgroundColor: '#1e1e1eAA',
    opacity: 0.95,
    resizable: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      backgroundThrottling: false, // Keep running in background
    },
  });

  // STEALTH MODE: Hide from screen capture
  win.setContentProtection(true);

  win.loadFile(path.join(__dirname, 'index.html'));

  // Ensure content scales proportionally to the window width, maintaining a 800px base
  win.on('resize', () => {
    if (isMiniMode || !win) return;
    const [width] = win.getSize();
    // Don't scale if width is less than 400 (which happens during mini mode transition)
    if (width < 380) return;
    try {
      win.webContents.setZoomFactor(width / 800);
    } catch (e) {
      console.error(e);
    }
  });

  // Clamp on move
  win.on('will-move', (e, newBounds) => {
    if (!win) return;
    const display = screen.getDisplayMatching(win.getBounds());
    const workArea = display.workArea;

    let clampedX = newBounds.x;
    let clampedY = newBounds.y;

    if (clampedX < workArea.x) clampedX = workArea.x;
    else if (clampedX + newBounds.width > workArea.x + workArea.width) clampedX = workArea.x + workArea.width - newBounds.width;

    if (clampedY < workArea.y) clampedY = workArea.y;
    else if (clampedY + newBounds.height > workArea.y + workArea.height) clampedY = workArea.y + workArea.height - newBounds.height;

    if (clampedX !== newBounds.x || clampedY !== newBounds.y) {
      e.preventDefault();
      win.setBounds({ x: clampedX, y: clampedY, width: newBounds.width, height: newBounds.height });
    }
  });

  win.on('moved', () => {
    clampWindowToScreen(win);
  });
}

app.whenReady().then(() => {
  // Start backend first
  startBackend();

  // Wait for backend to initialize
  setTimeout(() => {
    createWindow();

    // Check for updates after window is created (only in production)
    if (app.isPackaged) {
      setTimeout(() => {
        autoUpdater.checkForUpdates();
      }, 3000);
    }
  }, 2000);

  // IPC Handler for Screen Sources (Workaround for renderer restriction)
  ipcMain.handle('GET_SOURCES', async (event, types) => {
    const sources = await desktopCapturer.getSources({ types });
    // Return only necessary data to avoid serialization issues with NativeImage
    return sources.map(s => ({
      id: s.id,
      name: s.name
    }));
  });

  /* ---- Ctrl+F: Maximize AI Response Window ---- */
  globalShortcut.register('CommandOrControl+F', () => {
    if (!win) return;
    console.log('🔍 Maximize Response Triggered');
    win.webContents.executeJavaScript(`
      if (window.maximizeResponse) { window.maximizeResponse(); }
    `);
  });

  /* ---- move left / right ---- */
  globalShortcut.register('CommandOrControl+Alt+Left', () => {
    if (!win) return;
    const [x, y] = win.getPosition();
    win.setPosition(x - 50, y);
    clampWindowToScreen(win);
  });

  globalShortcut.register('CommandOrControl+Alt+Right', () => {
    if (!win) return;
    const [x, y] = win.getPosition();
    win.setPosition(x + 50, y);
    clampWindowToScreen(win);
  });

  /* ---- move up / down ---- */
  globalShortcut.register('CommandOrControl+Alt+Up', () => {
    if (!win) return;
    const [x, y] = win.getPosition();
    win.setPosition(x, y - 50);
    clampWindowToScreen(win);
  });

  globalShortcut.register('CommandOrControl+Alt+Down', () => {
    if (!win) return;
    const [x, y] = win.getPosition();
    win.setPosition(x, y + 50);
    clampWindowToScreen(win);
  });

  globalShortcut.register('CommandOrControl+R', () => {
    if (!win) return;
    console.log('System Audio Capture Triggered');
    win.webContents.executeJavaScript(`
      if (window.toggleSystemCapture) { window.toggleSystemCapture(); }
    `);
  });

  /* ---- Ctrl+Enter: Generate AI ---- */
  globalShortcut.register('CommandOrControl+Return', () => {
    if (!win) return;
    console.log('Generate AI Triggered');
    win.webContents.executeJavaScript(`
      if (window.generateAIOnly) { window.generateAIOnly(); }
    `);
  });

  /* ---- Ctrl+M: Toggle Mic Capture ---- */
  globalShortcut.register('CommandOrControl+M', () => {
    if (!win) return;
    console.log('🎤 Mic Capture Triggered');
    win.webContents.executeJavaScript(`
      if (window.toggleMicCapture) { window.toggleMicCapture(); }
    `);
  });

  /* ---- Ctrl+K: Capture Screen ---- */
  globalShortcut.register('CommandOrControl+K', () => {
    if (!win) return;
    console.log('Screen Capture Triggered');
    win.webContents.executeJavaScript(`
      if (window.captureScreen) { window.captureScreen(false); }
    `);
  });
  /* ---- Ctrl+S: Capture Screen + Save Context ---- */
  globalShortcut.register('CommandOrControl+S', () => {
    if (!win) return;
    console.log('Screen Capture Triggered (with context)');
    win.webContents.executeJavaScript(`
      if (window.captureScreen) { window.captureScreen(true); }
    `);
  });

  /* ---- Ctrl+Q: Toggle Mini Mode ---- */
  globalShortcut.register('CommandOrControl+Q', () => {
    if (!win) return;

    if (!isMiniMode) {
      // Switch to Mini Mode - small floating icon
      isMiniMode = true; // Set flag FIRST so resize listener ignores it
      const miniPos = lastMiniPosition || { x: win.getPosition()[0], y: win.getPosition()[1] };
      win.setOpacity(1.0);
      win.setBackgroundColor('#00000000');
      win.setBounds({ x: miniPos.x, y: miniPos.y, width: 50, height: 50 });
      win.webContents.setZoomFactor(1.0); // Reset zoom for mini icon
      win.setResizable(false);
      win.webContents.executeJavaScript(`
        document.body.classList.add('mini');
      `);
    } else {
      // Save mini position before expanding
      const [mx, my] = win.getPosition();
      lastMiniPosition = { x: mx, y: my };
      // Expand back
      win.setOpacity(0.95);
      win.setBackgroundColor('#1e1e1eAA');
      win.setResizable(true);
      const bounds = centerTop(800, 600);
      win.setBounds(bounds);
      win.webContents.setZoomFactor(1.0); // Reset zoom to default 800 width
      win.webContents.executeJavaScript(`document.body.classList.remove('mini');`);
      isMiniMode = false;
    }
  });

  /* ---- Ctrl+Shift+Q: Quit App ---- */
  globalShortcut.register('CommandOrControl+Shift+Q', () => {
    app.quit();
  });

  /* ---- Ctrl+Backspace: Clear Transcript ---- */
  globalShortcut.register('CommandOrControl+Backspace', () => {
    if (!win) return;
    console.log('🧹 Clear Transcript Triggered');
    win.webContents.executeJavaScript(`
      if (window.clearTranscript) { window.clearTranscript(); }
    `);
  });

  /* ---- Ctrl+Shift++: Incrementally Expand Window ---- */
  globalShortcut.register('CommandOrControl+Shift+Plus', () => {
    if (!win || isMiniMode) return;
    const [x, y] = win.getPosition();
    const [width, height] = win.getSize();
    const newWidth = Math.min(width + 80, 1600);
    const newHeight = Math.round(newWidth * (600 / 800));
    // Center the resize operation vertically and horizontally
    win.setBounds({ x: x - 40, y: y - Math.round(((newHeight - height) / 2)), width: newWidth, height: newHeight });
    win.webContents.setZoomFactor(newWidth / 800);
    clampWindowToScreen(win);
  });

  /* ---- Ctrl+Shift+-: Incrementally Contract Window ---- */
  globalShortcut.register('CommandOrControl+Shift+-', () => {
    if (!win || isMiniMode) return;
    const [x, y] = win.getPosition();
    const [width, height] = win.getSize();
    const newWidth = Math.max(width - 80, 400);
    const newHeight = Math.round(newWidth * (600 / 800));
    // Center the resize operation vertically and horizontally
    win.setBounds({ x: x + 40, y: y + Math.round(((height - newHeight) / 2)), width: newWidth, height: newHeight });
    win.webContents.setZoomFactor(newWidth / 800);
    clampWindowToScreen(win);
  });

  /* ---- Ctrl+Shift+O: Reset to Default Size ---- */
  globalShortcut.register('CommandOrControl+Shift+O', () => {
    if (!win || isMiniMode) return;
    const bounds = centerTop(800, 600);
    win.setBounds(bounds);
    win.webContents.setZoomFactor(1.0);
    console.log('🔄 Window reset to default size');
    clampWindowToScreen(win);
  });

  /* ---- Ctrl+Shift+Up: Scroll AI Up ---- */
  globalShortcut.register('CommandOrControl+Shift+Up', () => {
    if (!win) return;
    win.webContents.executeJavaScript(`
      if (window.scrollAIOutput) { window.scrollAIOutput(-1); }
    `);
  });

  /* ---- Ctrl+Shift+Down: Scroll AI Down ---- */
  globalShortcut.register('CommandOrControl+Shift+Down', () => {
    if (!win) return;
    win.webContents.executeJavaScript(`
      if (window.scrollAIOutput) { window.scrollAIOutput(1); }
    `);
  });

  /* ---- Tray ---- */
  const iconPath = path.join(__dirname, 'icon.ico');
  tray = new Tray(nativeImage.createFromPath(iconPath));
  tray.setToolTip('Windows Command Controller');
  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show / Hide', click: () => (win.isVisible() ? win.hide() : win.show()) },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() },
  ]);
  tray.setContextMenu(contextMenu);
  tray.on('click', () => (win.isVisible() ? win.hide() : win.show()));

  /* ---- IPC: Export Conversation ---- */
  ipcMain.handle('export-conversation', async (event, content, defaultName) => {
    const { filePath } = await dialog.showSaveDialog(win, {
      title: 'Export Conversation',
      defaultPath: defaultName || 'conversation_export.txt',
      filters: [
        { name: 'Text Documents', extensions: ['txt'] },
        { name: 'Markdown Documents', extensions: ['md'] },
        { name: 'All Files', extensions: ['*'] }
      ]
    });

    if (filePath) {
      require('fs').writeFileSync(filePath, content, 'utf-8');
      return { success: true, filePath };
    }
    return { success: false };
  });


  /* ---- IPC: Expand from Mini Mode ---- */
  ipcMain.on('expand-from-mini', () => {
    if (!win || !isMiniMode) return;
    // Save mini position before expanding
    const [mx, my] = win.getPosition();
    lastMiniPosition = { x: mx, y: my };
    win.setOpacity(0.95);
    win.setBackgroundColor('#1e1e1eAA');
    win.setResizable(true);
    const bounds = centerTop(800, 600);
    win.setBounds(bounds);
    win.webContents.setZoomFactor(1.0);
    win.webContents.executeJavaScript(`document.body.classList.remove('mini');`);
    isMiniMode = false;
  });

  /* ---- IPC: Close App ---- */
  ipcMain.on('close-app', () => {
    app.quit();
  });

  /* ---- IPC: Manual Update Check ---- */
  ipcMain.on('manual-update-check', () => {
    console.log('[UPDATE] Manual check requested');
    autoUpdater.checkForUpdates();
  });

  /* ---- IPC: Get App Version ---- */
  ipcMain.handle('get-app-version', () => {
    return app.getVersion();
  });

  if (app.dock) app.dock.hide();
});

// Configure logger for autoUpdater
autoUpdater.logger = console;

// Robust backend cleanup function
function cleanupBackend() {
  if (backendProcess && !backendProcess.killed) {
    try {
      console.log('Stopping backend process...');
      if (process.platform === 'win32') {
        // Kill by PID using taskkill
        try {
          require('child_process').execSync(`taskkill /pid ${backendProcess.pid} /T /F`, { stdio: 'ignore' });
        } catch (e) { }
      } else {
        backendProcess.kill('SIGKILL');
      }
    } catch (e) {
      console.log('Backend cleanup error:', e.message);
    }
  }

  // FORCE KILL by name just in case (Windows acting up)
  if (process.platform === 'win32') {
    try {
      require('child_process').execSync('taskkill /IM interview-backend.exe /F', { stdio: 'ignore' });
    } catch (e) { }
  }
}

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  cleanupBackend();
});

app.on('before-quit', () => {
  cleanupBackend();
});

app.on('window-all-closed', () => {
  cleanupBackend(); // Ensure cleanup happens even if quit isn't immediate
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
