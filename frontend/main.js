const { app, BrowserWindow, Tray, Menu, nativeImage, globalShortcut, screen, ipcMain, desktopCapturer, dialog } = require('electron');
const path = require('path');
const { spawn, execSync, exec } = require('child_process');
let autoUpdater = null;

let tray = null;
let win = null;
let convoWin = null;
let isRecording = false;
let isMiniMode = false;
let backendProcess = null;
let lastMiniPosition = null; // Remember where the mini icon was dragged to
let isQuitting = false; // Track explicit quit to prevent close aborting

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

// This will be initialized in app.whenReady
let updateLogger = null;

function initAutoUpdater() {
  try {
    autoUpdater = require('electron-updater').autoUpdater;
    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = false;
    autoUpdater.allowPrerelease = true;

    // Custom logger to send all update logs to the renderer
    updateLogger = {
      info: (msg) => {
        console.log('[UPDATE] ' + msg);
        if (win && !win.isDestroyed()) win.webContents.send('update-log', 'INFO: ' + msg);
      },
      warn: (msg) => {
        console.warn('[UPDATE] ' + msg);
        if (win && !win.isDestroyed()) win.webContents.send('update-log', 'WARN: ' + msg);
      },
      error: (msg) => {
        console.error('[UPDATE] ' + msg);
        if (win && !win.isDestroyed()) win.webContents.send('update-log', 'ERROR: ' + msg);
      }
    };
    // BYPASS NSIS CERTIFICATE CHECK IN WINDOWS
    autoUpdater.verifyUpdateCodeSignature = async (publisherName, installPath) => {
      console.log('[UPDATE] Bypassing code signature verification for', publisherName);
      return null; // Return null to indicate the signature is valid
    };

    autoUpdater.logger = updateLogger;

    // Prevent attaching multiple listener instances
    autoUpdater.removeAllListeners();
    ipcMain.removeAllListeners('update-accept');
    ipcMain.removeAllListeners('update-decline');
    ipcMain.removeAllListeners('update-restart');
    ipcMain.removeAllListeners('update-later');

    // Re-wire events here...
    setupAutoUpdaterEvents();
  } catch (err) {
    console.error('Failed to initialize auto-updater:', err);
  }
}

function setupAutoUpdaterEvents() {
  if (!autoUpdater) return;

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
    win.webContents.executeJavaScript(`{
    const bar = document.getElementById('update-progress-bar');
    const text = document.getElementById('update-progress-text');
    if (bar) bar.style.width = '${percent}%';
    if (text) text.textContent = '${percent}%';
  }`);
  }

  function hideUpdateUI() {
    if (!win) return;
    win.webContents.executeJavaScript(`{
    let el = document.getElementById('update-overlay');
    if (el) el.remove();
  }`);
  }

  let updateVersion = '';

  autoUpdater.on('checking-for-update', () => {
    console.log('Checking for updates...');
  });

  autoUpdater.on('update-available', (info) => {
    console.log('Update available:', info.version);
    updateVersion = info.version;
    if (win) win.webContents.send('update-check-result', 'available');

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
    win.webContents.executeJavaScript(`{
    const yesBtn = document.getElementById('update-yes-btn');
    const noBtn = document.getElementById('update-no-btn');
    if (yesBtn) yesBtn.addEventListener('click', () => {
      require('electron').ipcRenderer.send('update-accept');
    });
    if (noBtn) noBtn.addEventListener('click', () => {
      require('electron').ipcRenderer.send('update-decline');
    });
  }`);
  });

  ipcMain.on('update-accept', async () => {
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

    try {
      updateLogger.info('Manual download initiated...');
      await autoUpdater.downloadUpdate();
    } catch (err) {
      updateLogger.error('Critical failure in downloadUpdate(): ' + err.message);
      if (win) win.webContents.send('update-check-result', 'error', 'Download Failed: ' + err.message);
      hideUpdateUI();
    }
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
    win.webContents.executeJavaScript(`{
    const restartBtn = document.getElementById('update-restart-btn');
    const laterBtn = document.getElementById('update-later-btn');
    if (restartBtn) restartBtn.addEventListener('click', () => {
      require('electron').ipcRenderer.send('update-restart');
    });
    if (laterBtn) laterBtn.addEventListener('click', () => {
      require('electron').ipcRenderer.send('update-later');
    });
  }`);
  });

  ipcMain.on('update-restart', () => {
    console.log('[UPDATE] Restarting for update. Cleaning up backend first...');
    // Mark as quitting so cleanup doesn't abort
    isQuitting = true;

    try {
      // Run cleanup
      cleanupBackend();
    } catch (err) {
      console.error('[UPDATE ERROR] Backend cleanup failed during update-restart:', err);
    }

    // Wait slightly longer (3000ms) for OS to release file locks reliably, then install
    setTimeout(() => {
      console.log('[UPDATE] Attempting quitAndInstall...');
      autoUpdater.quitAndInstall(true, true);
    }, 3000);
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
}

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
    backgroundColor: '#0a0a0aEE',
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

  // Removed auto-open DevTools

  // Force default zoom factor to ignore Electron's persistent zoom cache
  win.webContents.once('dom-ready', () => {
    try {
      win.webContents.setZoomFactor(1.0);
    } catch (e) { }
  });

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
    }
  });

  win.on('focus', () => {
    // When the user clicks the main window, bring it to the front
    console.log('[DEBUG_FOCUS] Main window clicked/focused by OS');
    if (convoWin && !convoWin.isDestroyed() && convoWin.isVisible()) {
      stackWindows(win, convoWin);
    }
  });

  win.on('moved', () => {
    clampWindowToScreen(win);
  });

  win.on('closed', () => {
    win = null;
    app.quit();
  });
}

function createConvoWindow() {
  convoWin = new BrowserWindow({
    width: 450,
    height: 600,
    show: false,
    frame: false,
    alwaysOnTop: true,
    transparent: true,
    backgroundColor: '#00000000',
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  convoWin.loadFile(path.join(__dirname, 'convo.html'));

  convoWin.on('focus', () => {
    // When the user clicks the convo window, bring it to the front
    console.log('[DEBUG_FOCUS] Convo window clicked/focused by OS');
    if (win && !win.isDestroyed() && win.isVisible()) {
      stackWindows(convoWin, win);
    }
  });

  convoWin.on('close', (e) => {
    if (!isQuitting) {
      // Prevent actual closing, just hide it so state remains
      e.preventDefault();
      convoWin.hide();
    }
  });

  convoWin.on('closed', () => {
    convoWin = null;
  });
}

// Focus managers to ensure clicked windows go to the top of the alwaysOnTop stack
function stackWindows(frontWin, backWin) {
  if (!frontWin || frontWin.isDestroyed()) return;

  console.log(`[DEBUG_FOCUS] Attempting to stack windows natively. Restoring frontWin visibility.`);

  // Push the background window down to the standard floating layer
  if (backWin && !backWin.isDestroyed() && backWin.isVisible()) {
    backWin.setAlwaysOnTop(true, 'floating');
    console.log(`[DEBUG_FOCUS] Background window pushed to 'floating' layer.`);
  }

  // Pull the active window specifically to the highest possible layer to skip OS focus glitches
  frontWin.setAlwaysOnTop(true, 'screen-saver');
  const logMsg = `[DEBUG_FOCUS] Stacking ${frontWin === win ? 'Main' : 'Convo'} in FRONT (screen-saver layer).`;
  console.log(logMsg);
  if (win && !win.isDestroyed()) win.webContents.send('debug-log', logMsg);

  if (!frontWin.isVisible()) {
    console.log(`[DEBUG_FOCUS] Front window was hidden. showing...`);
    frontWin.show();
  }

  // Prevent infinite loops if stackWindows is called inside a 'focus' event
  if (!frontWin.isFocused()) {
    console.log(`[DEBUG_FOCUS] Triggering native element focus!`);
    frontWin.focus();
  }
}



app.whenReady().then(() => {
  // Start backend first
  startBackend();

  // Wait for backend to initialize
  setTimeout(() => {
    createWindow();
    createConvoWindow();

    // Check for updates after window is created (only in production)
    if (app.isPackaged) {
      setTimeout(() => {
        if (!autoUpdater) initAutoUpdater();
        if (autoUpdater) {
          autoUpdater.checkForUpdates().catch(e => console.error('Update check failed:', e));
        }
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

  // Helper to log shortcut registration
  const registerShortcut = (keys, callback) => {
    const success = globalShortcut.register(keys, callback);
    if (success) {
      console.log(`[SUCCESS] Registered shortcut: ${keys}`);
    } else {
      console.error(`[ERROR] Failed to register shortcut: ${keys}`);
      if (win && !win.isDestroyed()) {
        win.webContents.send('debug-log', `FAILED TO REGISTER SHORTCUT: ${keys}`);
      }
    }
    return success;
  };

  /* ---- Ctrl+F: Maximize AI Response Window ---- */
  registerShortcut('CommandOrControl+F', () => {

    if (!win || win.isDestroyed()) return;
    console.log('🔍 Maximize Response Triggered');
    win.webContents.executeJavaScript(`
      if (window.maximizeResponse) { window.maximizeResponse(); }
    `);
  });

  /* ---- move left / right ---- */
  registerShortcut('CommandOrControl+Alt+Left', () => {
    if (!win || win.isDestroyed()) return;
    const [x, y] = win.getPosition();
    win.setPosition(x - 50, y);
    clampWindowToScreen(win);
  });

  registerShortcut('CommandOrControl+Alt+Right', () => {
    if (!win || win.isDestroyed()) return;
    const [x, y] = win.getPosition();
    win.setPosition(x + 50, y);
    clampWindowToScreen(win);
  });

  /* ---- move up / down ---- */
  registerShortcut('CommandOrControl+Alt+Up', () => {
    if (!win || win.isDestroyed()) return;
    const [x, y] = win.getPosition();
    win.setPosition(x, y - 50);
    clampWindowToScreen(win);
  });

  registerShortcut('CommandOrControl+Alt+Down', () => {
    if (!win || win.isDestroyed()) return;
    const [x, y] = win.getPosition();
    win.setPosition(x, y + 50);
    clampWindowToScreen(win);
  });

  /* ---- move convo left / right ---- */
  registerShortcut('CommandOrControl+Alt+Shift+Left', () => {
    if (!convoWin || convoWin.isDestroyed() || !convoWin.isVisible()) return;
    const [x, y] = convoWin.getPosition();
    convoWin.setPosition(x - 50, y);
    clampWindowToScreen(convoWin);
  });

  registerShortcut('CommandOrControl+Alt+Shift+Right', () => {
    if (!convoWin || convoWin.isDestroyed() || !convoWin.isVisible()) return;
    const [x, y] = convoWin.getPosition();
    convoWin.setPosition(x + 50, y);
    clampWindowToScreen(convoWin);
  });

  /* ---- move convo up / down ---- */
  registerShortcut('CommandOrControl+Alt+Shift+Up', () => {
    if (!convoWin || convoWin.isDestroyed() || !convoWin.isVisible()) return;
    const [x, y] = convoWin.getPosition();
    convoWin.setPosition(x, y - 50);
    clampWindowToScreen(convoWin);
  });

  registerShortcut('CommandOrControl+Alt+Shift+Down', () => {
    if (!convoWin || convoWin.isDestroyed() || !convoWin.isVisible()) return;
    const [x, y] = convoWin.getPosition();
    convoWin.setPosition(x, y + 50);
    clampWindowToScreen(convoWin);
  });

  /* ---- resize convo ---- */
  registerShortcut('CommandOrControl+Alt+Shift+=', () => {
    if (!convoWin || convoWin.isDestroyed() || !convoWin.isVisible()) return;
    const [w, h] = convoWin.getSize();
    const display = screen.getDisplayMatching(convoWin.getBounds());
    const workArea = display.workArea;
    const newW = Math.min(w + 50, workArea.width);
    const newH = Math.min(h + 50, workArea.height);
    convoWin.setSize(newW, newH);
    clampWindowToScreen(convoWin);
  });

  registerShortcut('CommandOrControl+Alt+Shift+-', () => {
    if (!convoWin || convoWin.isDestroyed() || !convoWin.isVisible()) return;
    const [w, h] = convoWin.getSize();
    const newW = Math.max(w - 50, 300);
    const newH = Math.max(h - 50, 400);
    convoWin.setSize(newW, newH);
    clampWindowToScreen(convoWin);
  });

  registerShortcut('CommandOrControl+Alt+Shift+O', () => {
    if (!convoWin || convoWin.isDestroyed() || !convoWin.isVisible()) return;
    convoWin.setSize(450, 600);
    clampWindowToScreen(convoWin);
  });


  /* ---- Ctrl+Alt+C: Toggle Convo Window ---- */
  registerShortcut('CommandOrControl+Alt+C', () => {
    if (!convoWin || convoWin.isDestroyed()) return;
    if (convoWin.isVisible()) {
      convoWin.hide();
    } else {
      if (win && !win.isDestroyed()) {
        const [mwX, mwY] = win.getPosition();
        const [mwW, mwH] = win.getSize();
        convoWin.setPosition(mwX + mwW + 20, mwY);
        clampWindowToScreen(convoWin);
      }
      convoWin.show();
      stackWindows(convoWin, win);
    }
  });


  registerShortcut('CommandOrControl+R', () => {
    if (!win || win.isDestroyed()) return;
    console.log('System Audio Capture Triggered');
    win.webContents.executeJavaScript(`
      if (window.toggleSystemCapture) { window.toggleSystemCapture(); }
    `);
  });

  /* ---- Ctrl+Enter: Generate AI ---- */
  registerShortcut('CommandOrControl+Return', () => {
    if (!win) return;
    console.log('Generate AI Triggered');
    win.webContents.executeJavaScript(`
      if (window.generateAIOnly) { window.generateAIOnly(); }
    `);
  });

  /* ---- Ctrl+M: Toggle Mic Capture ---- */
  registerShortcut('CommandOrControl+M', () => {
    if (!win) return;
    console.log('🎤 Mic Capture Triggered');
    win.webContents.executeJavaScript(`
      if (window.toggleMicCapture) { window.toggleMicCapture(); }
    `);
  });

  /* ---- Ctrl+K: Capture Screen ---- */
  registerShortcut('CommandOrControl+K', () => {
    if (!win) return;
    console.log('Screen Capture Triggered');
    win.webContents.executeJavaScript(`
      if (window.captureScreen) { window.captureScreen(false); }
    `);
  });
  /* ---- Ctrl+S: Capture Screen + Save Context ---- */
  registerShortcut('CommandOrControl+S', () => {
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

      // Save full window position BEFORE minimizing
      const [fx, fy] = win.getPosition();
      const [fw, fh] = win.getSize();
      win.lastNormalBounds = { x: fx, y: fy, width: fw, height: fh };

      const miniPos = lastMiniPosition || { x: fx, y: fy };
      win.setOpacity(1.0);
      win.setBackgroundColor('#00000000');
      win.setBounds({ x: miniPos.x, y: miniPos.y, width: 52, height: 52 });
      win.webContents.setZoomFactor(1.0); // Reset zoom for mini icon
      win.setResizable(false);
      win.webContents.executeJavaScript(`
        document.body.classList.add('mini');
      `);

      // Hide convo window as well
      if (convoWin && convoWin.isVisible()) {
        convoWin.userVisibleBeforeMini = true;
        convoWin.hide();
      } else if (convoWin) {
        convoWin.userVisibleBeforeMini = false;
      }

    } else {
      // Save mini position before expanding
      const [mx, my] = win.getPosition();
      lastMiniPosition = { x: mx, y: my };

      // Expand back
      win.setOpacity(0.95);
      win.setBackgroundColor('#0a0a0aEE');
      win.setResizable(true);

      // Restore the exact position it had before mini mode
      if (win.lastNormalBounds) {
        win.setBounds(win.lastNormalBounds);
        win.webContents.setZoomFactor(win.lastNormalBounds.width / 800);
      } else {
        const bounds = centerTop(800, 600);
        win.setBounds(bounds);
        win.webContents.setZoomFactor(1.0);
      }

      win.webContents.executeJavaScript(`document.body.classList.remove('mini');`);
      isMiniMode = false;

      // Restore convo window if it was open
      if (convoWin && convoWin.userVisibleBeforeMini) {
        convoWin.show();
        convoWin.userVisibleBeforeMini = false;
      }
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
    win.setBackgroundColor('#0a0a0aEE');
    win.setResizable(true);
    const bounds = centerTop(800, 600);
    win.setBounds(bounds);
    win.webContents.setZoomFactor(1.0);
    win.webContents.executeJavaScript(`document.body.classList.remove('mini');`);
    isMiniMode = false;
  });

  /* ---- IPC: Convo Window Control ---- */
  ipcMain.on('toggle-convo-window', () => {
    console.log(`[DEBUG_IPC] Received 'toggle-convo-window' event!`);
    if (!convoWin) return;
    if (convoWin.isVisible()) {
      console.log(`[DEBUG_IPC] Convo window is visible... hiding it.`);
      convoWin.hide();
    } else {
      console.log(`[DEBUG_IPC] Convo window is hidden... computing position then opening.`);
      // Position it generally near the main window, but on the side
      if (win && !win.isDestroyed()) {
        const [mwX, mwY] = win.getPosition();
        const [mwW, mwH] = win.getSize();
        // Attempt to put it to the right of the main window
        convoWin.setPosition(mwX + mwW + 20, mwY);
        clampWindowToScreen(convoWin);
      }
      convoWin.show();
      console.log(`[DEBUG_IPC] Showing convo. Triggering native Focus inside IPC toggle handler!`);
      stackWindows(convoWin, win);
    }
  });

  ipcMain.on('hide-convo-window', () => {
    if (convoWin) convoWin.hide();
  });

  // Window Focus Handlers
  ipcMain.on('focus-main-window', () => {
    if (win && !win.isDestroyed() && win.isVisible()) {
      stackWindows(win, convoWin);
    }
  });

  ipcMain.on('focus-convo-window', () => {
    if (convoWin && !convoWin.isDestroyed() && convoWin.isVisible()) {
      stackWindows(convoWin, win);
    }
  });

  // Relay historical dump to floating window
  ipcMain.on('load-convo-history', (event, payload) => {
    if (convoWin) {
      convoWin.webContents.send('load-convo-history', payload);
    }
  });

  // Relay live response update to floating window
  ipcMain.on('convo-update', (event, payload) => {
    if (convoWin) {
      convoWin.webContents.send('render-convo-update', payload);
    }
  });

  // Relay title sets
  ipcMain.on('set-convo-title', (event, payload) => {
    if (convoWin) {
      convoWin.webContents.send('set-convo-title', payload);
    }
  });

  // Relay clear commands
  ipcMain.on('clear-convo-history', () => {
    if (convoWin) {
      convoWin.webContents.send('clear-convo-history');
    }
  });

  /* ---- IPC: Close App ---- */
  ipcMain.on('close-app', () => {
    app.quit();
  });

  /* ---- IPC: Manual Update Check ---- */
  ipcMain.on('manual-update-check', () => {
    console.log('[UPDATE] Manual check requested from UI');
    try {
      if (!app.isPackaged) {
        console.log('[UPDATE] Skipping real update check in development mode');
        if (win && !win.isDestroyed()) {
          setTimeout(() => {
            win.webContents.send('update-check-result', 'latest');
          }, 1500);
        }
        return;
      }

      if (!autoUpdater) initAutoUpdater();

      if (autoUpdater) {
        autoUpdater.checkForUpdates().catch(err => {
          console.error('[UPDATE ERROR] Manual check failed:', err);
          if (win && !win.isDestroyed()) win.webContents.send('update-check-result', 'error', err.message);
        });
      } else {
        console.error('[UPDATE ERROR] autoUpdater not available after init');
        if (win && !win.isDestroyed()) win.webContents.send('update-check-result', 'error', 'autoUpdater initialization failed.');
      }
    } catch (err) {
      console.error('[UPDATE ERROR] Crash in manual-update-check handler:', err);
      if (win && !win.isDestroyed()) win.webContents.send('update-check-result', 'error', 'Crash in check process.');
    }
  });

  /* ---- IPC: Get App Version ---- */
  ipcMain.handle('get-app-version', () => {
    return app.getVersion();
  });

  if (app.dock) app.dock.hide();
});


// Robust backend cleanup function
function cleanupBackend() {
  console.log('[EXIT] Starting synchronous cleanup...');
  const { execSync } = require('child_process');

  // 1. Kill the tracked backend process if still alive
  if (backendProcess && !backendProcess.killed) {
    try {
      console.log(`[EXIT] Killing tracked PID: ${backendProcess.pid}`);
      if (process.platform === 'win32') {
        execSync(`taskkill /pid ${backendProcess.pid} /T /F`, { stdio: 'ignore' });
      } else {
        backendProcess.kill('SIGKILL');
      }
    } catch (e) {
      console.log(`[EXIT] PID kill failed: ${e.message}`);
    }
  }

  // 2. Kill by Name (Safety net for Windows)
  if (process.platform === 'win32') {
    try {
      console.log('[EXIT] Force killing WinHostSvc.exe by name...');
      execSync('taskkill /IM WinHostSvc.exe /F', { stdio: 'ignore' });
    } catch (e) { }

    // 3. Kill Port 5050 (Crucial for dev mode)
    try {
      console.log('[EXIT] Cleaning up port 5050...');
      const output = execSync('netstat -ano | findstr :5050', { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
      if (output) {
        const lines = output.trim().split('\n');
        lines.forEach(line => {
          const parts = line.trim().split(/\s+/);
          const pid = parts[parts.length - 1];
          if (pid && pid !== '0' && !isNaN(pid)) {
            console.log(`[EXIT] Killing process on port 5050 (PID: ${pid})...`);
            try {
              execSync(`taskkill /PID ${pid} /T /F`, { stdio: 'ignore' });
            } catch (kille) {
              console.log(`[EXIT] Failed to kill PID ${pid} or it was already dead.`);
            }
          }
        });
      }
    } catch (e) {
      // Netstat might fail if no matches found, which is fine
      console.log('[EXIT] No process found port 5050 or netstat failed.');
    }
  }

  if (tray && !tray.isDestroyed()) {
    try { tray.destroy(); tray = null; } catch (e) { }
  }
  console.log('[EXIT] Cleanup complete.');
}

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  cleanupBackend();
});

app.on('before-quit', () => {
  isQuitting = true;
  cleanupBackend();
});

app.on('window-all-closed', () => {
  cleanupBackend(); // Ensure cleanup happens even if quit isn't immediate
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
