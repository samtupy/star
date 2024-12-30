@echo off
rem pyinstaller --noconfirm STAR.spec
del /S /Q dist\*.dylib
del /S /Q dist\*.so
rmdir /S /Q dist\STAR\sound_lib\lib\x86
