# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['WinHostSvc.py'],
    pathex=[],
    binaries=[],
    datas=[('public_key.pem', '.')],
    hiddenimports=['cpuinfo', 'tiktoken', 'tiktoken_ext', 'tiktoken_ext.openai_public', 'regex', 'cryptography', 'docx'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Keep the frozen backend lean: the global Python used to build it had the
    # data-science stack installed, and PyInstaller was bundling all of it.
    excludes=['numpy', 'pandas', 'scipy', 'matplotlib', 'IPython', 'jupyter_client',
              'jupyter_core', 'ipykernel', 'notebook', 'PIL', 'torch', 'tensorflow',
              'sklearn', 'pytest', '_pytest', 'tornado', 'zmq', 'tkinter', 'setuptools',
              'pkg_resources', 'sqlalchemy', 'pyarrow', 'numba', 'llvmlite', 'sympy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# One-folder build (exe + _internal/). The old one-file build unpacked ~25 MB
# into %TEMP% on every launch, which was most of the ~6 s startup time.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WinHostSvc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX adds per-launch decompression CPU and trips AV heuristics
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='WinHostSvc',
)
