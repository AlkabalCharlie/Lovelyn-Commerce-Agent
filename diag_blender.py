"""Verify Blender's DLL deps: copy its own redistributables next to exe."""
import os, shutil
base = r"C:\Blender\blender-4.2.3-windows-x64"
# Blender ships msvcp140 etc. in its own dir usually; check
shipped = [f for f in os.listdir(base) if f.lower().endswith(".dll")]
print("shipped dlls:", shipped[:10])
