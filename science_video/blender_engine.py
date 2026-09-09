"""Runs inside Blender. Only trusted Python handles validated scene action names."""
import argparse
import json
import math
from pathlib import Path
import random
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


def setup_camera(camera_type, start, end, molecules=False):
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    bpy.context.scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = {"wide": 7.5, "close": 5.8, "macro": 7.5, "medium": 7.5}[camera_type]
    target = (0, 0, 1.3)
    cam.location = (0, -10, 4.0 if not molecules else 2.5)
    aim(cam, target)
    cam.keyframe_insert(data_path="location", frame=start)
    cam.keyframe_insert(data_path="rotation_euler", frame=start)
    cam.location.x = 0.35
    aim(cam, target)
    cam.keyframe_insert(data_path="location", frame=end)
    cam.keyframe_insert(data_path="rotation_euler", frame=end)


def setup_lighting():
    for location, power, size, color in [((2,-4,7), 1100, 5, (0.7,0.9,1)),
                                         ((-3,1,4), 900, 4, (0.25,0.65,1)),
                                         ((0,4,6), 1400, 3, (1,0.7,0.35))]:
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
    label(text, (location[0], -0.25, location[1]), size, mats["text"])


def code_scene(mats, start, end):
    tech_label("PYTHON", (0, 2.8), mats, 0.3)
    lines = [("data = [2, 4, 6]", -1.0), ("for value in data:", 0.0), ("    print(value)", 1.0)]
    for text, y in lines:
        tech_label(text, (-0.1, y), mats, 0.22)
    cursor = cylinder("Execution cursor", (-2.25, 0, 0.07), 0.08, 0.08, mats["ice"])
    cursor.scale.x = 0.2
    cursor.keyframe_insert(data_path="scale", frame=start)
    cursor.scale.x = 2.0
    cursor.keyframe_insert(data_path="scale", frame=end)
    tech_label("Input -> Loop -> Output", (0, -2.7), mats, 0.18)


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


def algorithm_steps(mats, start, end):
    tech_label("ALGORITHM", (0, 2.9), mats, 0.3)
    steps = [("1. Input", -1.6), ("2. Process", 0), ("3. Output", 1.6)]
    for index, (text, x) in enumerate(steps):
        cube = bpy.ops.mesh.primitive_cube_add(size=0.9, location=(x, 0, 1.0))
        box = finish(bpy.context.object, f"Algorithm step {index + 1}", mats["water"])
        box.scale = (0.65, 0.2, 0.65)
        box.keyframe_insert(data_path="scale", frame=start + index * max(1, (end-start)//4))
        box.scale = (1, 1, 1)
        box.keyframe_insert(data_path="scale", frame=start + index * max(1, (end-start)//4) + max(1, (end-start)//5))
        tech_label(text, (x, -0.7), mats, 0.18)
        if index < len(steps) - 1:
            beam((x + 0.5, 0, 1.0), (steps[index + 1][1] - 0.5, 0, 1.0), mats["hydrogen"])
    tech_label("Break a big problem into small steps", (0, -2.0), mats, 0.19)


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
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.025,0.05,0.10,1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.4
    mats = {
        "glass": material("Glass outline", (0.45,0.8,0.9), metallic=0.5),
        "water": material("Water", (0.03,0.40,0.65), transmission=0.6),
        "ice": material("Ice", (0.55,0.9,1), roughness=0.17, transmission=0.15),
        "oil": material("Oil", (0.95,0.60,0.06)),
        "oxygen": material("Oxygen", (0.95,0.15,0.16)),
        "hydrogen": material("Hydrogen", (0.92,0.96,1)),
        "text": material("Labels", (0.8,0.94,1)),
    }
    start, end = spec["start_frame"], spec["end_frame"]
    action = spec["action"]
    topic_image = settings.get("topic_image")
    if topic_image:
        image_path = Path(settings.get("job_folder", "")) / topic_image
        if image_path.is_file():
            topic_image_background(image_path, start, end)
    if action == "show_water_molecules":
        molecules(mats, start, end)
    elif action == "compare_density":
        density(mats, start, end)
    elif action == "show_code":
        code_scene(mats, start, end)
    elif action == "show_data_chart":
        chart_scene(mats, start, end)
    elif action == "show_neural_network":
        neural_network(mats, start, end)
    elif action == "show_algorithm_steps":
        algorithm_steps(mats, start, end)
    elif action in {"show_glass_water_ice", "zoom_into_ice", "return_to_glass", "show_oil_water"}:
        glass_scene(mats, start, end, oil=action == "show_oil_water")
    else:
        raise ValueError(f"Unsupported action: {action}")
    setup_camera(spec["camera"], start, end, action in {"show_water_molecules", "compare_density", "show_code", "show_data_chart", "show_neural_network", "show_algorithm_steps"})
    setup_lighting()
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
            bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
