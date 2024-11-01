@echo off
cd provider/balcony
pyinstaller --windowed --onefile balcony.py
cd ../pyttsx
pyinstaller --windowed --onefile pyttsx.py
cd ../..
cp provider/balcony/dist/balcony.exe user/STAR
cp provider/pyttsx/dist/pyttsx.exe user/STAR
cd user
nvgt -q -C STAR.nvgt
