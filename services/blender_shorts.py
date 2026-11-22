"""Lovelyn 2.5D animated Shorts prototype (Blender 4.2, EEVEE).

Cinematic illustrated 2.5D: layered planes with parallax depth, armature-
rigged original character (head/eyes/brows/mouth/arms), shape-keyed mouth
for lip sync, keyframed expressions/blinks/gestures, camera drift, soft
lighting + shadows. Renders PNG frames that shorts assembly turns into MP4
with narration + burned subtitles.

Run:  blender --background --python this_file.py -- <out_frames_dir>
"""
import math
import os
import sys

import bpy

W, H = 1080, 1920
FPS = 30
DUR = 13.0
FRAME_END = int(DUR * FPS)

argv = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "media/blender_frames"
OUT = argv

# ---------------- clean scene ----------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = W
scene.render.resolution_y = H
scene.render.fps = FPS
scene.frame_start = 1
scene.frame_end = FRAME_END
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.join(bpy.path.abspath("//"), OUT) + os.sep
scene.view_settings.view_transform = "Filmic"

# ---------------- helpers ----------------

def plane(name, w, h, loc, color, z=0.0, emission=0.0, parent=None):
    """A flat colored plane standing upright (illustrated layer)."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-w/2, 0, 0), (w/2, 0, 0), (w/2, h, 0), (-w/2, h, 0)],
                     [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (math.radians(90), 0, 0)  # face camera (-Y)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
    bsdf.inputs["Emission Strength"].default_value = emission
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


# ---------------- environment (3 parallax depth layers) ----------------
# Far: night-city skyline silhouette
sky = plane("bg_sky", 24, 14, (0, -9, -2), (14, 16, 30), z=-9, emission=0.35)
city = plane("bg_city", 22, 6.5, (0, -8, -2), (24, 28, 48), z=-8, emission=0.5)
# a few lit windows: small emissive quads on the city layer
for i in range(14):
    x = -8 + i * 1.2
    plane(f"win{i}", 0.35, 0.5, (x, -7.9, -1.4 + (i % 3) * 1.1),
          (255, 196, 0), z=-7.8, emission=2.2)
# Mid: street/wall
mid = plane("bg_mid", 20, 8, (0, -5.5, -1.6), (30, 34, 52), z=-5.5, emission=0.1)
# Near ground
ground = plane("ground", 20, 5, (0, -1.2, -3.1), (24, 36, 32), z=-1)

# Desk with bills (the problem object) - foreground interaction target
desk = plane("desk", 5.5, 0.5, (0, 0.4, -2.6), (94, 64, 44), z=0)
bills = []
for i in range(3):
    b = plane(f"bill{i}", 0.9, 0.55, (-0.6 + i * 0.6, 0.3, -2.45 + i * 0.02),
              (250, 250, 252), z=0)
    bills.append(b)

# ---------------- the character (layered, armature-rigged) ----------------
# Body (torso) plane
torso = plane("torso", 1.35, 1.9, (0, -0.4, -2.2), CHAR_SHIRT := (0.37, 0.51, 0.86), z=0)
# Head group
head = plane("head", 1.0, 1.0, (0, -0.38, -1.15), (0.91, 0.75, 0.60), z=0.01)
hair = plane("hair", 1.06, 0.42, (0, -0.37, -0.70), (0.16, 0.12, 0.10), z=0.02)
eye_l = plane("eye_l", 0.13, 0.10, (-0.2, -0.36, -1.18), (0.05, 0.05, 0.08), z=0.03)
eye_r = plane("eye_r", 0.13, 0.10, (0.2, -0.36, -1.18), (0.05, 0.05, 0.08), z=0.03)
brow_l = plane("brow_l", 0.26, 0.06, (-0.2, -0.355, -1.02), (0.16, 0.12, 0.10), z=0.03)
brow_r = plane("brow_r", 0.26, 0.06, (0.2, -0.355, -1.02), (0.16, 0.12, 0.10), z=0.03)
mouth = plane("mouth", 0.34, 0.16, (0, -0.35, -1.34), (0.45, 0.15, 0.15), z=0.03)
# Arms
arm_l = plane("arm_l", 0.3, 1.1, (-0.85, -0.35, -2.0), CHAR_SHIRT, z=0.02)
arm_r = plane("arm_r", 0.3, 1.1, (0.85, -0.35, -2.0), CHAR_SHIRT, z=0.02)

# Mouth shape keys (visemes) on the mouth plane
def add_shapekey(obj, name, delta):
    obj.shape_key_add(name="Basis")
    sk = obj.shape_key_add(name=name)
    for i, dz in enumerate(delta):
        sk.data[i].co.z += dz

# visemes: closed, AA (wide open), OH (round), MB (pressed)
add_shapekey(mouth, "closed", [0.05, 0.05, -0.02, -0.02])   # thin line
add_shapekey(mouth, "AA", [0, 0, -0.16, -0.16])             # tall open
add_shapekey(mouth, "OH", [-0.06, 0.06, -0.10, -0.10])      # narrower, open
add_shapekey(mouth, "MB", [0.10, -0.10, 0.0, 0.0])          # pressed shut

# ---------------- armature (simple spine + head control) ----------------
arm = bpy.data.armatures.new("rig")
rig = bpy.data.objects.new("rig", arm)
bpy.context.collection.objects.link(rig)
rig.location = (0, -0.4, -2.4)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
spine = arm.edits.new("spine"); spine.head = (0, 0, 0.2); spine.tail = (0, 0, 1.9)
neck = arm.edits.new("neck"); neck.head = (0, 0, 1.9); neck.tail = (0, 0, 2.55)
neck.use_connect = True
bpy.ops.object.mode_set(mode="OBJECT")
for o in (torso, head, hair, eye_l, eye_r, brow_l, brow_r, mouth, arm_l, arm_r):
    pm = o.parent
    o.parent = rig
    o.parent_type = "BONE"
    o.parent_bone = "neck" if o in (head, hair, eye_l, eye_r, brow_l, brow_r,
                                    mouth) else "spine"
    if pm:
        pass
# keep child-bones
for o in (head, hair, eye_l, eye_r, brow_l, brow_r, mouth):
    o.parent = head

# ---------------- lights ----------------
key = bpy.data.objects.new("key", bpy.data.lights.new("key", 'AREA'))
key.data.energy = 900; key.data.size = 4
key.location = (2.5, -3.5, 2.5); key.rotation_euler = (math.radians(55), 0, math.radians(30))
bpy.context.collection.objects.link(key)
rim = bpy.data.objects.new("rim", bpy.data.lights.new("rim", 'AREA'))
rim.data.energy = 350; rim.data.color = (0.6, 0.7, 1.0)
rim.location = (-3, 1.5, 2); rim.rotation_euler = (math.radians(-40), 0, math.radians(-120))
bpy.context.collection.objects.link(rim)
amb = bpy.data.objects.new("amb", bpy.data.lights.new("amb", 'SUN'))
amb.data.energy = 1.2; amb.data.color = (0.7, 0.75, 0.9)
amb.rotation_euler = (math.radians(50), 0, math.radians(20))
bpy.context.collection.objects.link(amb)

# ---------------- camera with drift (subtle push-in + parallax) ----------------
cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam.location = (0, -7.4, 0.2)
cam.rotation_euler = (math.radians(88), 0, 0)
cam.keyframe_insert("location", frame=1)
cam.location = (0, -6.7, 0.35)
cam.keyframe_insert("location", frame=FRAME_END)

# ---------------- ANIMATION ----------------

def key_loc(obj, frame, loc):
    obj.location = loc
    obj.keyframe_insert("location", frame=frame)

def key_scale(obj, frame, sc):
    obj.scale = (sc, sc, sc)
    obj.keyframe_insert("scale", frame=frame)

def key_rot(obj, frame, rot_z):
    obj.rotation_euler.z = rot_z
    obj.keyframe_insert("rotation_euler", frame=frame)

def set_sk(obj, name, frame, value):
    obj.data.shape_keys.key_blocks[name].value = value
    obj.data.shape_keys.key_blocks[name].keyframe_insert("value", frame=frame)

# Beat A (0-2s): worried, looking at bills
key_rot(head, 1, 0.0); key_rot(head, 40, math.radians(-14))
brow_l.location.z = -1.02 - 0.03; brow_l.keyframe_insert("location", frame=1)
brow_r.location.z = -1.02 - 0.03; brow_r.keyframe_insert("location", frame=1)
set_sk(mouth, "closed", 1, 1.0)

# Beat B (2-4.5s): surprise -> bills glow red-ish (problem emphasized)
key_rot(head, 60, math.radians(10))
brow_l.location.z += 0.06; brow_l.keyframe_insert("location", frame=60)
brow_r.location.z += 0.06; brow_r.keyframe_insert("location", frame=60)
key_loc(eye_l, 60, (-0.2, -0.36, -1.18)); key_loc(eye_r, 60, (0.2, -0.36, -1.18))

# Beat C (4.5-8s): discovery + explanation (present gesture)
key_rot(head, 110, 0.0)
key_rot(arm_r, 105, math.radians(120))   # raise, presenting
key_rot(arm_r, 200, math.radians(110))
brow_l.location.z += 0.02; brow_l.keyframe_insert("location", frame=110)
brow_r.location.z += 0.02; brow_r.keyframe_insert("location", frame=110)

# Beat D (8-11s): picks up a bill -> resolves (confident), progress glow
key_rot(arm_l, 240, math.radians(-70))
key_loc(arm_l, 240, (-0.85, 0.0, -2.0))
key_loc(bills[0], 240, (bills[0].location.x, 0.15, -2.0))
key_loc(bills[0], 270, (0.9, -0.3, -1.7))
key_rot(head, 270, math.radians(4))
brow_l.location.z += 0.03; brow_l.keyframe_insert("location", frame=270)
brow_r.location.z += 0.03; brow_r.keyframe_insert("location", frame=270)

# Beat E (11-13s): confident hold, slight nod
key_rot(head, 320, math.radians(-3))
key_rot(head, 390, math.radians(2))

# Blinking (natural: ~every 2.5-3.5s, quick)
blink_f = 70
while blink_f < FRAME_END - 5:
    for e in (eye_l, eye_r):
        e.scale = (1.0, 1.0, 1.0)
        e.keyframe_insert("scale", frame=blink_f - 1)
        e.scale = (1.0, 0.08, 1.0)
        e.keyframe_insert("scale", frame=blink_f)
        e.scale = (1.0, 1.0, 1.0)
        e.keyframe_insert("scale", frame=blink_f + 1)
    blink_f += int(2.7 * FPS)

# Idle breathing (torso subtle scale pulse + sway)
for f in range(1, FRAME_END + 1, 5):
    key_scale(torso, f, 1.0 + 0.012 * math.sin(f / FPS * 2.2))
    key_rot(torso, f, 0.02 * math.sin(f / FPS * 1.1))

# ---------------- LIP SYNC from Rhubarb cue file ----------------
cue_file = os.path.join(os.path.dirname(__file__), "..", "media", "rhubarb_cues.txt")
if os.path.isfile(cue_file):
    MOUTH_MAP = {"A": "AA", "B": "MB", "C": "MB", "D": "AA", "E": "AA",
                 "F": "MB", "G": "AA", "H": "AA", "I": "AA", "J": "OH",
                 "K": "AA", "L": "AA", "M": "MB", "N": "MB", "O": "OH",
                 "P": "MB", "Q": "OH", "R": "OH", "S": "MB", "T": "MB",
                 "U": "OH", "V": "MB", "W": "OH", "X": "AA", "Y": "OH",
                 "Z": "AA", "X": "closed"}
    current = "closed"
    with open(cue_file) as fh:
        for line in fh:
            parts = line.strip().split()
            if len(parts) == 3 and parts[1] in MOUTH_MAP:
                f = int(float(parts[0]) * FPS) + 1
                shape = MOUTH_MAP[parts[1]]
                set_sk(mouth, shape, f, 1.0)
                # close previous
                for s in ("AA", "OH", "MB"):
                    if s != shape:
                        set_sk(mouth, s, f, 0.0)
else:
    print("NOTE: no rhubarb cue file - mouth stays neutral (lip sync step pending)")

# ---------------- render ----------------
os.makedirs(scene.render.filepath, exist_ok=True)
bpy.ops.render.render(animation=True)
print("FRAMES DONE:", scene.render.filepath)
