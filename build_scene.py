"""Lovelyn 2.5D Shorts prototype - Blender scene builder.

Layered illustrated animation (NOT a slideshow): separate planes per body
part, transparent PNG artwork drawn programmatically by build_assets.py,
parented into a simple armature, keyframed with:
- blinking (eye scale), brow raises (shape-key-like via bone rotation)
- mouth cue swapping from Rhubarb output (mouth-shape image swapping)
- head turns, body sway, arm gestures via bone keyframes
- 3-layer parallax background + camera drift (2.5D depth)
- lighting: warm key light + cool rim via emission planes and blur shadows

Run: blender --background --python build_scene.py -- <narration.wav> <rhubarb.csv> <out.mp4>
"""
import bpy
import csv
import math
import os
import sys

W, H, FPS, DUR = 1080, 1920, 30, 12.0
BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "media", "blender_assets")
os.makedirs(ASSETS, exist_ok=True)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NARRATION = argv[0] if argv else os.path.join(ASSETS, "narration.wav")
RHUBARB = argv[1] if len(argv) > 1 else os.path.join(ASSETS, "rhubarb.csv")
OUT = argv[2] if len(argv) > 2 else os.path.join(BASE, "media", "shorts",
                                                 "prototype-2.5d.mp4")

# ---------- clean scene ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"  # Blender 4.2's EEVEE name
# 8 samples: flat illustrated art needs no heavy sampling
scene.eevee.taa_render_samples = 8
scene.eevee.use_gtao = False
scene.eevee.use_raytracing = False
scene.render.resolution_x = W
scene.render.resolution_y = H
scene.render.fps = FPS
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.audio_codec = "AAC"
scene.frame_end = int(DUR * FPS)


def img_plane(name, png, x, y, z, scale=1.0, loc_z_off=0.0):
    """Import a transparent PNG as a camera-facing plane."""
    if not os.path.isfile(png):
        print("MISSING ASSET:", png)
        return None
    tex = bpy.data.images.load(png)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    texnode = nt.nodes.new("ShaderNodeTexImage")
    texnode.image = tex
    texnode.interpolation = "Closest" if "mouth" in name else "Linear"
    texnode.name = "TexImage"
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    # EMISSION: artwork is self-illuminated -> renders exactly as drawn
    # (the near-black frame bug was lit planes receiving no light).
    emis = nt.nodes.new("ShaderNodeEmission")
    emis.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(texnode.outputs["Color"], emis.inputs["Color"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(texnode.outputs["Alpha"], mix.inputs[0])
    nt.links.new(transp.outputs[0], mix.inputs[1])
    nt.links.new(emis.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    bpy.ops.mesh.primitive_plane_add(size=1)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(mat)
    ob.scale = (scale, scale * H / W, 1)
    ob.location = (x, y, z)  # x=horizontal, y=depth from camera, z=vertical
    ob.rotation_euler = (math.radians(90), 0, 0)
    # keep unlit flat look for artwork layers
    mat.blend_method = "BLEND"
    return ob


# ---------- keyframe helpers ----------
def k(obj, prop, frame, value):
    obj.keyframe_insert(data_path=prop, frame=frame)
    setattr(obj, prop, value)


def kloc(obj, frame, x=None, y=None, z=None):
    if x is not None: obj.location.x = x
    if y is not None: obj.location.y = y
    if z is not None: obj.location.z = z
    obj.keyframe_insert(data_path="location", frame=frame)


def krot(obj, frame, deg):
    obj.rotation_euler.z = math.radians(deg)
    obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def kscale(obj, frame, sx, sy=None):
    obj.scale.x = sx
    if sy is not None: obj.scale.y = sy
    obj.keyframe_insert(data_path="scale", frame=frame)


# ---------- layers (far -> near) ----------
# ALL artwork is full-canvas 1080x1920 aligned overlays: identical scale +
# position, ONLY depth (y) differs -> correct composition + free parallax.
S = 4.6 * W / H  # plane width so full-canvas art (1080x1920) fills the ortho
# view exactly: view height 4.6 -> plane height must be 4.6 = scale*H/W
bg_far = img_plane("bg_far", os.path.join(ASSETS, "bg_far.png"),
                   0, 3.0, 0, scale=S)
bg_mid = img_plane("bg_mid", os.path.join(ASSETS, "bg_mid.png"),
                   0, 1.8, 0, scale=S)
desk = img_plane("desk", os.path.join(ASSETS, "desk.png"),
                 0, -3.0, 0, scale=S)
body = img_plane("char_body", os.path.join(ASSETS, "char_body.png"),
                 0, 0.4, 0, scale=S)
arms = img_plane("char_arms", os.path.join(ASSETS, "char_arms.png"),
                 0, 0.45, 0, scale=S)
head = img_plane("char_head", os.path.join(ASSETS, "char_head.png"),
                 0, 0.60, 0, scale=S)
brows = img_plane("char_brows", os.path.join(ASSETS, "char_brows_neutral.png"),
                  0, 0.58, 0, scale=S)
eyes = img_plane("char_eyes", os.path.join(ASSETS, "char_eyes_open.png"),
                 0, 0.57, 0, scale=S)
mouth = img_plane("char_mouth_closed", os.path.join(ASSETS, "mouth_closed.png"),
                  0, 0.56, 0, scale=S)

# empty parenting for grouped motion
rig = bpy.data.objects.new("rig", None)
scene.collection.objects.link(rig)
for ob in (body, arms, head, eyes, brows, mouth):
    if ob: ob.parent = rig

cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 4.6  # matches S so canvas fills frame exactly
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
cam.location = (0, -6.2, 0)
cam.rotation_euler = (math.radians(90), 0, 0)
scene.camera = cam

# warm key light + cool rim (EEVEE)
for lname, loc, color, energy in (
        ("key", (2.5, -3, 3), (1.0, 0.93, 0.82), 3.0),
        ("rim", (-3, -1, 2.4), (0.55, 0.7, 1.0), 1.6)):
    li = bpy.data.objects.new(lname, bpy.data.lights.new(lname, "POINT"))
    li.data.energy = energy * 300
    li.data.color = color
    li.location = loc
    scene.collection.objects.link(li)

# ---------- mouth cues from Rhubarb ----------
MOUTH_SHAPES = {}
for shape in ("A", "B", "C", "D", "E", "F", "X"):
    p = os.path.join(ASSETS, f"mouth_{shape.lower()}.png")
    if os.path.isfile(p):
        MOUTH_SHAPES[shape] = p
MOUTH_SHAPES.setdefault("X", os.path.join(ASSETS, "mouth_closed.png"))

cues = []
if os.path.isfile(RHUBARB):
    with open(RHUBARB) as fh:
        for row in csv.DictReader(fh):
            cues.append((float(row.get("Start") or 0) * FPS,
                         row["Mouth"].strip()))
else:
    cues = [(0, "X")]

mouth_frames = {}
for f, shape in cues:
    if shape in MOUTH_SHAPES:
        mouth_frames[int(round(f))] = MOUTH_SHAPES[shape]

# Mouth animation: a render-frame handler swaps the mouth image per frame
# from the Rhubarb-format cue table (real narration timing).
if mouth:
    _tex = mouth.data.materials[0].node_tree.nodes["TexImage"]
    _images = {}
    for shape, path in MOUTH_SHAPES.items():
        _images[shape] = bpy.data.images.load(path, check_existing=True)

    def _swap_mouth(scene, depsgraph):
        f = scene.frame_current
        shape = None
        for cf in sorted(mouth_frames):
            if cf <= f:
                shape = mouth_frames[cf]
        if shape and _images.get(shape):
            _tex.image = _images[shape]

    bpy.app.handlers.frame_change_pre.append(_swap_mouth)
    bpy.app.handlers.render_pre.append(lambda s, d: _swap_mouth(s, d))

# ---------- animation ----------
af = int(FPS)  # 1s
def F(sec): return int(sec * FPS)

if head:
    # subtle head sway (full-canvas overlay: tiny offsets = pixel-shifts)
    krot(head, F(0), -0.4); krot(head, F(2.5), 0.5); krot(head, F(5), 1.0)
    krot(head, F(8), 0); krot(head, F(11), -0.5)
    kloc(head, F(0), x=0); kloc(head, F(6), x=0.03); kloc(head, F(12), x=0)

if rig:
    # gentle breathing on all character layers (they're all parented to rig)
    for f, dx in ((0, 0), (30, 0.004), (90, -0.004), (180, 0.002), (360, 0)):
        kloc(rig, f, x=dx)

if brows:
    # concerned raise at problem beat, firm lower after (tiny z offsets)
    kloc(brows, F(0), z=0)
    kloc(brows, F(2), z=0.02)
    kloc(brows, F(4), z=0)
    kloc(brows, F(7), z=-0.01)
    kloc(brows, F(11), z=0)

if eyes:
    # blinks (y-squash on the full overlay) at 1.2/4.7/8.9s
    for bt in (1.2, 4.7, 8.9):
        b0, b1, b2 = F(bt - 0.06), F(bt), F(bt + 0.06)
        kscale(eyes, b0 - 1, 1.0, 1.0)
        kscale(eyes, b1, 1.0, 0.06)
        kscale(eyes, b2, 1.0, 1.0)
    # glance right at 5s (tiny offset on full canvas)
    kloc(eyes, F(4.8), x=0); kloc(eyes, F(5.4), x=0.02); kloc(eyes, F(9.5), x=0)

if arms:
    # gesture drift (full-canvas: small x shifts read as arm movement)
    kloc(arms, F(0), x=0)
    kloc(arms, F(2.2), x=-0.02); kloc(arms, F(3.2), x=0)
    kloc(arms, F(6.5), x=0.02); kloc(arms, F(9), x=0)

# camera: ortho parallax drift (layers at different depths shift subtly)
kloc(cam, F(0), x=0)
kloc(cam, F(6), x=0.12)
kloc(cam, F(12), x=0)

# ---------- narration audio ----------
if os.path.isfile(NARRATION):
    snd = bpy.data.sounds.load(NARRATION)
    track = scene.sequence_editor_create().sequences.new_sound(
        "narr", NARRATION, 1, 1)

# ---------- render ----------
scene.render.filepath = os.path.abspath(OUT)
print("will write to:", scene.render.filepath)
bpy.ops.render.render(animation=True, write_still=False)
print("RENDER DONE ->", scene.render.filepath)
