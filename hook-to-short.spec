# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = [
    # Audio processing
    'pychorus', 'librosa', 'soundfile', 'scipy', 'scipy.signal',
    # Video
    'moviepy', 'moviepy.video', 'moviepy.audio',
    # Image
    'PIL', 'PIL.Image',
    # Network
    'requests', 'yt_dlp',
    # Google API (YouTube upload)
    'google.oauth2', 'google.oauth2.credentials',
    'google.auth', 'google.auth.transport', 'google.auth.transport.requests',
    'google_auth_oauthlib', 'google_auth_oauthlib.flow',
    'googleapiclient', 'googleapiclient.discovery', 'googleapiclient.http',
    'httplib2',
    # App modules
    'python.mood_detector', 'python.kie_generator', 'python.gemini_generator',
    'python.video_composer', 'python.main',
    'python.uploaders', 'python.uploaders.youtube_uploader',
    'python.uploaders.tiktok_uploader', 'python.uploaders.facebook_uploader',
]

# Collect customtkinter assets (themes, etc.)
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Include the python/ package
datas += [('python', 'python')]


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='Hook-to-Short',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='Hook-to-Short',
)
