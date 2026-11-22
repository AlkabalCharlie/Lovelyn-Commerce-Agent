import sys, os
import bpy

src = open('build_scene.py').read().replace(
    'bpy.ops.render.render(animation=True, write_still=False)', 'pass')
sys.argv = ['build_scene.py', '--', 'media/blender_assets/narration.wav',
            'media/blender_assets/rhubarb.csv', 'probe.mp4']
exec(compile(src, 'build_scene.py', 'exec'))

scene = bpy.context.scene
scene.render.image_settings.file_format = 'PNG'
scene.frame_set(45)
for n in ('bg_far', 'bg_mid'):
    bpy.data.objects[n].hide_render = True
scene.render.filepath = os.path.abspath('media/probe_nobg.png')
bpy.ops.render.render(write_still=True)
print('DONE')
