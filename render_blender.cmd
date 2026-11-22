@echo off
set PATH=C:\Blender\blender-4.2.3-windows-x64\4.2\python\bin;%PATH%
"C:\Blender\blender-4.2.3-windows-x64\blender.exe" --background --python build_scene.py -- media\blender_assets\narration.wav media\blender_assets\rhubarb.csv media\shorts\prototype-2.5d.mp4 > blender_render.log 2>&1
echo EXIT:%ERRORLEVEL%
