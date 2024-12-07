# -*- mode: python ; coding: utf-8 -*-


a_user = Analysis(
	['user\\STAR.py'],
	pathex=[],
	binaries=[],
	datas=[('user/audio', 'audio')],
	hiddenimports=['_cffi_backend'],
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=[],
	noarchive=False,
	optimize=0,
)
pyz_user = PYZ(a_user.pure)

exe_user = EXE(
	pyz_user,
	a_user.scripts,
	[],
	exclude_binaries=True,
	name='STAR',
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
	contents_directory='.',
)

a_coagulator = Analysis(
	['coagulator\\coagulator.py'],
	pathex=[],
	binaries=[],
	datas=[],
	hiddenimports=[],
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=[],
	noarchive=False,
	optimize=0,
)
pyz_coagulator = PYZ(a_coagulator.pure)

exe_coagulator = EXE(
	pyz_coagulator,
	a_coagulator.scripts,
	[],
	exclude_binaries=True,
	name='coagulator',
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
	contents_directory='.',
)

a_balcony = Analysis(
	['provider\\balcony.py'],
	pathex=[],
	binaries=[("provider\\balcon.exe", ".")],
	datas=[],
	hiddenimports=[],
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=[],
	noarchive=False,
	optimize=0,
)
pyz_balcony = PYZ(a_balcony.pure)

exe_balcony = EXE(
	pyz_balcony,
	a_balcony.scripts,
	[],
	exclude_binaries=True,
	name='balcony',
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
	contents_directory='.',
)

a_sammy = Analysis(
	['provider\\sammy.py'],
	pathex=[],
	binaries=[("provider\\sam.exe", ".")],
	datas=[],
	hiddenimports=[],
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=[],
	noarchive=False,
	optimize=0,
)
pyz_sammy = PYZ(a_sammy.pure)

exe_sammy = EXE(
	pyz_sammy,
	a_sammy.scripts,
	[],
	exclude_binaries=True,
	name='sammy',
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
	contents_directory='.',
)

coll = COLLECT(
	exe_user,
	a_user.binaries,
	a_user.datas,
	exe_coagulator,
	a_coagulator.binaries,
	a_coagulator.datas,
	exe_balcony,
	a_balcony.binaries,
	a_balcony.datas,
	exe_sammy,
	a_sammy.binaries,
	a_sammy.datas,
	strip=False,
	upx=True,
	upx_exclude=["balcon.exe", "sam.exe"],
	name='STAR',
)
