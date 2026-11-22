@echo off
"C:\Blender\blender-4.2.3-windows-x64\blender.exe" --background --python-expr "print('BLENDER_ALIVE')" > "%TEMP%\bo2.txt" 2>&1
echo EXITCODE:%ERRORLEVEL%
