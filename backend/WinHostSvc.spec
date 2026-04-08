# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['WinHostSvc.py'],
    pathex=[],
    binaries=[],
    datas=[('public_key.pem', '.')],
    hiddenimports=['tiktoken', 'tiktoken_ext', 'tiktoken_ext.openai_public', 'regex', 'cryptography'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WinHostSvc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
