"""Runs inside Blender. Only trusted Python handles validated scene action names."""
import argparse
import json
import math
from pathlib import Path
import random
import re
import sys

import bpy
from mathutils import Vector


def material(name, color, metallic=0, roughness=0.3, transmission=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Transmission Weight"].default_value = transmission
    return mat


def topic_image_background(path, start, end):
    image = bpy.data.images.load(str(path), check_existing=True)
    mat = bpy.data.materials.new("Topic image background")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    shader.inputs["Roughness"].default_value = 1
    links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 1.4, 1.5), rotation=(math.pi / 2, 0, 0))
    plane = finish(bpy.context.object, "Animated topic image", mat)
    plane.scale = (2.2, 3.8, 1)
    plane.keyframe_insert(data_path="scale", frame=start)
    plane.scale = (2.28, 3.94, 1)
    plane.keyframe_insert(data_path="scale", frame=end)


def finish(obj, name, mat):
    obj.name = name
    obj.data.materials.append(mat)
    if obj.type == "MESH":
        for poly in obj.data.polygons:
            poly.use_smooth = True
    return obj


def sphere(name, location, radius, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=radius, location=location)
    return finish(bpy.context.object, name, mat)


def cylinder(name, location, radius, depth, mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=radius, depth=depth, location=location)
    return finish(bpy.context.object, name, mat)


def ring(location, radius, mat):
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=0.035,
                                   major_segments=64, minor_segments=8, location=location)
    return finish(bpy.context.object, "Glass rim", mat)


def create_glass(mats):
    # An outlined open vessel keeps submerged ice visible in the scientific cutaway.
    ring((0, 0, 0.08), 1.05, mats["glass"])
    ring((0, 0, 2.45), 1.05, mats["glass"])
    cylinder("Glass base", (0, 0, 0.04), 1.05, 0.08, mats["glass"])
    for angle in (0, math.pi/2, math.pi, 3*math.pi/2):
        cylinder("Glass edge", (1.05*math.cos(angle), 1.05*math.sin(angle), 1.25), 0.015, 2.4, mats["glass"])


def create_water(mats):
    # A translucent surface and wire vessel form an intentional scientific cutaway.
    water = cylinder("Water surface", (0, 0, 1.7), 1.01, 0.025, mats["water"])
    ring((0, 0, 1.7), 1.01, mats["water"])
    return water


def create_ice(mats):
    # 0.8-unit cube: surface 1.7; ~92% of cube height below surface.
    bpy.ops.mesh.primitive_cube_add(size=0.8, location=(0, 0, 1.364))
    ice = finish(bpy.context.object, "Floating ice (schematic)", mats["ice"])
    bevel = ice.modifiers.new("Soft ice edges", "BEVEL")
    bevel.width = 0.08
    bevel.segments = 3
    ice.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return ice


def create_molecule(location, mats):
    root = bpy.data.objects.new("H2O", None)
    bpy.context.collection.objects.link(root)
    root.location = location
    for name, pos, size, mat in [("Oxygen", (0,0,0), 0.13, mats["oxygen"]),
                                  ("Hydrogen", (0.14,0,0.10), 0.075, mats["hydrogen"]),
                                  ("Hydrogen", (-0.14,0,0.10), 0.075, mats["hydrogen"])]:
        atom = sphere(name, pos, size, mat)
        atom.parent = root
    return root


def label(text, location, size, mat):
    bpy.ops.object.text_add(location=location, rotation=(math.pi/2, 0, 0))
    obj = bpy.context.object
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.001
    obj.data.materials.append(mat)


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


def setup_camera(camera_type, start, end, diagram=False):
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    bpy.context.scene.camera = cam
    cam.data.type = "ORTHO"
    requested_scale = {"wide": 7.5, "close": 5.8, "macro": 7.5, "medium": 7.5}[camera_type]
    # A 9:16 orthographic frame is much narrower than it is tall. Do not let
    # a storyboard's "close" camera crop a labelled diagram at either side.
    cam.data.ortho_scale = max(requested_scale, 8.2) if diagram else requested_scale
    target = (0, 0, 1.3)
    cam.location = (0, -10, 4.0 if not diagram else 2.5)
    aim(cam, target)


def setup_lighting():
    for location, power, size, color in [((2,-4,7), 1350, 5, (0.25,0.9,1.0)),
                                         ((-3,1,4), 1050, 4, (0.55,0.22,1.0)),
                                         ((0,4,6), 1500, 3, (1.0,0.38,0.18))]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy, light.data.shape, light.data.size = power, "DISK", size
        light.data.color = color
        aim(light, (0,0,1))


def animate_ice(ice, start, end):
    for frame, dz in [(start, 0), ((start+end)//2, 0.015), (end, 0)]:
        ice.location.z = 1.364 + dz
        ice.keyframe_insert(data_path="location", frame=frame)


def molecules(mats, start, end):
    rng = random.Random(42)
    label("LIQUID", (-0.85,-0.2,2.8), 0.21, mats["text"])
    label("ICE", (0.85,-0.2,2.8), 0.21, mats["text"])
    label("Equal molecule counts", (0,-0.2,-0.15), 0.17, mats["text"])
    label("Schematic - not to scale", (0,-0.2,-0.4), 0.13, mats["text"])
    for side in (-1, 1):
        for row in range(4):
            for col in range(2):
                spacing = 0.32 if side == -1 else 0.53
                pos = (side*0.85 + (col-0.5)*spacing, 0, 0.6 + row*spacing)
                mol = create_molecule(pos, mats)
                for frame in (start, (start+end)//2, end):
                    mol.location = Vector(pos) + Vector(tuple(rng.uniform(-0.09,0.09) if side == -1 else rng.uniform(-0.01,0.01) for _ in range(3)))
                    mol.keyframe_insert(data_path="location", frame=frame)


def density(mats, start, end):
    for x, height, title, mat in [(-0.65, 2.0, "WATER", mats["water"]), (0.65, 1.834, "ICE", mats["ice"])]:
        bar = cylinder(title, (x,0,height/2), 0.36, height, mat)
        bar.scale.z = 0.05
        bar.location.z = height*0.05/2
        bar.keyframe_insert(data_path="scale", frame=start)
        bar.keyframe_insert(data_path="location", frame=start)
        bar.scale.z = 1
        bar.location.z = height/2
        bar.keyframe_insert(data_path="scale", frame=start+max(1,(end-start)//3))
        bar.keyframe_insert(data_path="location", frame=start+max(1,(end-start)//3))
        label(title, (x,-0.45,-0.3), 0.19, mats["text"])
        label("1.00" if x < 0 else "0.917", (x,-0.1,height+0.2), 0.23, mats["text"])
    label("Density / g per cm3", (0,-0.2,2.9), 0.2, mats["text"])
    label("Approx. near freezing", (0,-0.2,-0.6), 0.15, mats["text"])


def tech_label(text, location, mats, size=0.2):
    # Keep long explanatory labels inside the narrow 9:16 safe frame.
    safe_size = size * min(1.0, 32 / max(32, len(text)))
    label(text, (location[0], -0.25, location[1]), safe_size, mats["text"])


def lesson_kind(spec):
    text = f"{spec.get('caption', '')} {spec.get('narration', '')}".casefold()
    if any(word in text for word in ("list", "mutable", "append", "index")):
        return "python_list"
    if any(word in text for word in ("git", "commit", "branch", "version control")):
        return "git"
    if any(word in text for word in ("token", "language model", "llm", "prompt")):
        return "llm"
    return "general"


def code_scene(mats, start, end, kind="general"):
    # Keep code readable when a topic image is present behind the diagram.
    # This panel sits in front of the background and gives every label a safe,
    # predictable position in the vertical frame.
    panel_material = material("Code panel", (0.025, 0.06, 0.13), metallic=0.15, roughness=0.28)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.12, 0.55))
    panel = finish(bpy.context.object, "Code panel", panel_material)
    panel.scale = (3.05, 0.06, 3.35)
    title, lines, footer = {
        "python_list": ("PYTHON LIST", [("numbers = [2, 4, 6]", 1.25), ("numbers[1] = 9", 0.25), ("print(numbers)", -0.75)],
                        "Change an item after creation"),
        "git": ("GIT WORKFLOW", [("git status", 1.25), ("git add .", 0.25), ("git commit -m 'save'", -0.75)],
                "Track a safe project history"),
    }.get(kind, ("PYTHON", [("data = [2, 4, 6]", 1.25), ("for value in data:", 0.25), ("    print(value)", -0.75)],
                  "Input -> Loop -> Output"))
    tech_label(title, (0, 2.65), mats, 0.29)
    for text, y in lines:
        tech_label(text, (-0.1, y), mats, 0.22)
    cursor = cylinder("Execution cursor", (-2.25, -0.12, 1.25), 0.08, 0.08, mats["ice"])
    cursor.scale.x = 0.2
    cursor.keyframe_insert(data_path="scale", frame=start)
    cursor.scale.x = 2.0
    cursor.keyframe_insert(data_path="scale", frame=end)
    tech_label(footer, (0, -2.35), mats, 0.18)


def chart_scene(mats, start, end):
    tech_label("DATA PATTERN", (0, 2.9), mats, 0.3)
    values = [0.8, 1.4, 2.1, 2.8, 3.5]
    for index, height in enumerate(values):
        x = (index - 2) * 0.75
        bar = cylinder(f"Data bar {index + 1}", (x, 0, 0.05), 0.23, height, mats["water"])
        bar.scale.z = 0.05
        bar.location.z = height * 0.05 / 2
        bar.keyframe_insert(data_path="scale", frame=start)
        bar.keyframe_insert(data_path="location", frame=start)
        bar.scale.z = 1
        bar.location.z = height / 2
        bar.keyframe_insert(data_path="scale", frame=end)
        bar.keyframe_insert(data_path="location", frame=end)
        tech_label(str(index + 1), (x, -1.2), mats, 0.16)
    tech_label("Compare values, spot the trend", (0, -2.3), mats, 0.2)


def beam(start, end, mat):
    midpoint = (Vector(start) + Vector(end)) / 2
    length = (Vector(end) - Vector(start)).length
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.025, depth=length, location=midpoint)
    obj = finish(bpy.context.object, "Neural connection", mat)
    obj.rotation_euler = (Vector(end) - Vector(start)).to_track_quat("Z", "Y").to_euler()
    return obj


def neural_network(mats, start, end):
    tech_label("NEURAL NETWORK", (0, 2.9), mats, 0.27)
    layers = [(-1.7, [-1.0, 0, 1.0]), (0, [-1.4, -0.45, 0.45, 1.4]), (1.7, [-1.0, 0, 1.0])]
    points = []
    for x, heights in layers:
        current = []
        for y in heights:
            current.append((x, 0, y + 1.0))
            sphere("Neural node", (x, 0, y + 1.0), 0.16, mats["ice"])
        points.append(current)
    for left, right in zip(points, points[1:]):
        for source in left:
            for target in right:
                beam(source, target, mats["hydrogen"])
    tech_label("Input -> Learn -> Predict", (0, -1.9), mats, 0.2)
    tech_label("Weights change during training", (0, -2.5), mats, 0.16)
    for node in bpy.context.scene.objects:
        if node.name.startswith("Neural node"):
            node.scale = (0.4, 0.4, 0.4)
            node.keyframe_insert(data_path="scale", frame=start)
            node.scale = (1, 1, 1)
            node.keyframe_insert(data_path="scale", frame=end)


def algorithm_steps(mats, start, end, kind="general"):
    title, labels, footer = {
        "python_list": ("PYTHON LIST", ("1. Create", "2. Change", "3. Updated"), "Lists can be changed after creation"),
        "git": ("GIT WORKFLOW", ("1. Edit", "2. Commit", "3. Restore"), "Save each working version"),
        "llm": ("LLM PIPELINE", ("1. Prompt", "2. Tokens", "3. Next token"), "Repeat prediction to build a response"),
    }.get(kind, ("ALGORITHM", ("1. Input", "2. Process", "3. Output"), "Break a big problem into small steps"))
    tech_label(title, (0, 2.9), mats, 0.3)
    steps = list(zip(labels, (-1.25, 0, 1.25)))
    for index, (text, x) in enumerate(steps):
        cube = bpy.ops.mesh.primitive_cube_add(size=0.9, location=(x, 0, 1.0))
        box = finish(bpy.context.object, f"Algorithm step {index + 1}", mats["water"])
        box.scale = (0.5, 0.2, 0.58)
        box.keyframe_insert(data_path="scale", frame=start + index * max(1, (end-start)//4))
        box.scale = (1, 1, 1)
        box.keyframe_insert(data_path="scale", frame=start + index * max(1, (end-start)//4) + max(1, (end-start)//5))
        tech_label(text, (x, -0.7), mats, 0.145)
        if index < len(steps) - 1:
            beam((x + 0.42, 0, 1.0), (steps[index + 1][1] - 0.42, 0, 1.0), mats["hydrogen"])
    tech_label(footer, (0, -2.0), mats, 0.17)


def grammar_tense_scene(mats, start, end):
    """A clear, reusable timeline for English-tense lessons."""
    tech_label("ENGLISH TENSES", (0, 2.9), mats, 0.3)
    tenses = [("PAST", "I walked", -1.25, mats["hydrogen"]),
              ("PRESENT", "I walk", 0, mats["ice"]),
              ("FUTURE", "I will walk", 1.25, mats["oil"])]
    for index, (title, example, x, mat) in enumerate(tenses):
        bpy.ops.mesh.primitive_cube_add(size=0.9, location=(x, 0, 1.0))
        card = finish(bpy.context.object, f"Tense card {title}", mat)
        card.scale = (0.55, 0.2, 0.64)
        card.keyframe_insert(data_path="scale", frame=start + index * max(1, (end-start)//4))
        card.scale = (1, 1, 1)
        card.keyframe_insert(data_path="scale", frame=start + index * max(1, (end-start)//4) + max(1, (end-start)//5))
        tech_label(title, (x, 0.05), mats, 0.17)
        tech_label(example, (x, -0.75), mats, 0.13)
    beam((-1.25, 0, 1.0), (1.25, 0, 1.0), mats["text"])
    tech_label("When the action happens changes the tense", (0, -2.0), mats, 0.17)


def math_concept_scene(mats, start, end, spec):
    """A reusable, in-frame solve flow for beginner mathematics lessons."""
    text = f"{spec.get('caption', '')} {spec.get('narration', '')}".casefold()
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text)]
    formula = "Understand the idea step by step"
    if "fraction" in text:
        title, labels, footer = "FRACTIONS", ("1. Whole", "2. Parts", "3. Fraction"), "A fraction shows equal parts of a whole"
    elif any(word in text for word in ("percent", "percentage", "%")):
        title, labels, footer = "PERCENTAGES", ("1. Total", "2. Per 100", "3. Result"), "Percentage means parts out of one hundred"
        if "%" in text and len(numbers) >= 2:
            percent, total = numbers[0], numbers[1]
            result = percent * total / 100
            formula = f"{percent:g}% of {total:g} = {result:g}"
        elif "per hundred" in text:
            formula = "x% = x / 100"
        elif "divide" in text and len(numbers) >= 2:
            percent, total = numbers[0], numbers[-1]
            formula = f"({percent:g} / 100) x {total:g} = {percent * total / 100:g}"
        elif "result" in text and numbers:
            formula = f"Answer = {numbers[-1]:g}"
    elif any(word in text for word in ("ratio", "proportion")):
        title, labels, footer = "RATIOS", ("1. Compare", "2. Simplify", "3. Ratio"), "A ratio compares two quantities"
    elif any(word in text for word in ("equation", "algebra", "variable")):
        title, labels, footer = "EQUATIONS", ("1. Unknown", "2. Balance", "3. Solve"), "Keep both sides balanced"
    elif any(word in text for word in ("geometry", "angle", "triangle", "area")):
        title, labels, footer = "GEOMETRY", ("1. Shape", "2. Measure", "3. Result"), "Use the right property for the shape"
    else:
        title, labels, footer = "MATH IDEA", ("1. Given", "2. Solve", "3. Answer"), "Understand the steps, then calculate"
    tech_label(title, (0, 2.9), mats, 0.3)
    tech_label(formula, (0, 2.25), mats, 0.25)
    steps = list(zip(labels, (-1.25, 0, 1.25)))
    for index, (label_text, x) in enumerate(steps):
        bpy.ops.mesh.primitive_cube_add(size=0.9, location=(x, 0, 1.0))
        card = finish(bpy.context.object, f"Math card {index + 1}", (mats["hydrogen"], mats["ice"], mats["oil"])[index])
        card.scale = (0.5, 0.2, 0.58)
        card.keyframe_insert(data_path="scale", frame=start + index * max(1, (end-start)//4))
        card.scale = (1, 1, 1)
        card.keyframe_insert(data_path="scale", frame=start + index * max(1, (end-start)//4) + max(1, (end-start)//5))
        tech_label(label_text, (x, -0.7), mats, 0.145)
        if index < len(steps) - 1:
            beam((x + 0.42, 0, 1.0), (steps[index + 1][1] - 0.42, 0, 1.0), mats["text"])
    tech_label(footer, (0, -2.0), mats, 0.17)


def glass_scene(mats, start, end, oil=False):
    create_glass(mats)
    create_water(mats)
    if oil:
        cylinder("Oil layer", (0,0,1.95), 1.0, 0.45, mats["oil"])
        label("OIL", (0,-1.15,2.0), 0.18, mats["text"])
    else:
        animate_ice(create_ice(mats), start, end)
        label("ICE", (0,-1.15,1.35), 0.17, mats["text"])
    label("WATER", (0,-1.15,0.55), 0.17, mats["text"])
    label("Cutaway view", (0,-0.2,-0.35), 0.14, mats["text"])


def build_scene(spec, settings):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if settings.get("fast", False) else "CYCLES"
    scene.view_settings.view_transform = "AgX"
    scene.cycles.samples = 12 if settings["preview"] else 16
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.05 if settings["preview"] else 0.03
    scene.cycles.use_denoising = True
    scene.render.resolution_x = settings["width"]
    scene.render.resolution_y = settings["height"]
    scene.render.resolution_percentage = 100
    scene.render.fps = settings["fps"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("Midnight studio")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.012,0.025,0.075,1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.55
    mats = {
        "glass": material("Glass outline", (0.10,0.88,1.0), metallic=0.7, roughness=0.18),
        "water": material("Water", (0.04,0.34,1.0), metallic=0.2, roughness=0.16, transmission=0.35),
        "ice": material("Ice", (0.38,0.96,1.0), metallic=0.25, roughness=0.12, transmission=0.1),
        "oil": material("Oil", (1.0,0.45,0.05), metallic=0.35, roughness=0.2),
        "oxygen": material("Oxygen", (1.0,0.15,0.38), metallic=0.25),
        "hydrogen": material("Hydrogen", (0.82,0.36,1.0), metallic=0.35, roughness=0.18),
        "text": material("Labels", (0.92,0.98,1.0), metallic=0.15),
    }
    start, end = spec["start_frame"], spec["end_frame"]
    action = spec["action"]
    kind = lesson_kind(spec)
    topic_image = settings.get("topic_image")
    # Every supported action builds its own labeled diagram. Do not stack the
    # generated topic image behind it: two independent visual systems can
    # collide, especially for random storyboard actions. The topic image is
    # still saved as a separate post asset; video scenes use one clear diagram.
    if action == "show_water_molecules":
        molecules(mats, start, end)
    elif action == "compare_density":
        density(mats, start, end)
    elif action == "show_code":
        code_scene(mats, start, end, kind)
    elif action == "show_data_chart":
        chart_scene(mats, start, end)
    elif action == "show_neural_network":
        neural_network(mats, start, end)
    elif action == "show_algorithm_steps":
        algorithm_steps(mats, start, end, kind)
    elif action == "show_grammar_tense":
        grammar_tense_scene(mats, start, end)
    elif action == "show_math_concept":
        math_concept_scene(mats, start, end, spec)
    elif action in {"show_glass_water_ice", "zoom_into_ice", "return_to_glass", "show_oil_water"}:
        glass_scene(mats, start, end, oil=action == "show_oil_water")
    else:
        raise ValueError(f"Unsupported action: {action}")
    # Captions are also burned into the final video. Repeat the short scene
    # idea inside the diagram so a still frame remains self-explanatory and a
    # generic local visual cannot appear unrelated to its narration.
    detail = str(spec.get("caption", "")).strip()
    if detail:
        tech_label(detail, (0, 3.45), mats, 0.145)
    setup_camera(spec["camera"], start, end, action in {"show_water_molecules", "compare_density", "show_code", "show_data_chart", "show_neural_network", "show_algorithm_steps", "show_grammar_tense", "show_math_concept"})
    setup_lighting()
    # Blender 4.5 can render keyframed scene objects black after the first frame
    # in background animation mode on this Windows build. Keep the generated
    # diagrams static until that renderer issue is resolved; captions, audio,
    # and scene changes still provide the video timing and progression.
    for obj in scene.objects:
        obj.animation_data_clear()
    scene.frame_start, scene.frame_end = start, end
    scene.frame_set(start)
    return scene


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--still", action="store_true")
    parser.add_argument("--scene-index", type=int)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    job = json.loads(args.job.read_text(encoding="utf-8"))
    folder = args.job.parent
    (folder / "frames").mkdir(exist_ok=True)
    scene_indices = range(len(job["timeline"])) if args.scene_index is None else [args.scene_index]
    for i in scene_indices:
        spec = job["timeline"][i]
        scene = build_scene(spec, job)
        scene.render.filepath = str(folder / "frames" / "frame_")
        bpy.ops.wm.save_as_mainfile(filepath=str(folder / f"scene-{i+1:02d}.blend"))
        if args.still:
            scene.frame_set((spec["start_frame"] + spec["end_frame"]) // 2)
            scene.render.filepath = str(folder / f"still-{i+1:02d}.png")
            bpy.ops.render.render(write_still=True)
        else:
            # Blender 4.5 on this Windows build corrupts every animation frame
            # after the first one in a background process. A fresh scene still
            # is reliable, so render one clear visual per storyboard scene and
            # hold it for that scene's narrated duration.
            scene.frame_set((spec["start_frame"] + spec["end_frame"]) // 2)
            still_folder = folder / "rendered-scenes"
            still_folder.mkdir(exist_ok=True)
            still_path = still_folder / f"scene-{i+1:02d}.png"
            scene.render.filepath = str(still_path)
            bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
