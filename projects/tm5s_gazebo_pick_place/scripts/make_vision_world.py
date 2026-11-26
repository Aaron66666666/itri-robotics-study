"""Generate worlds/vision_world.sdf: the TM5S pick-and-place scene plus a fixed
table camera and two graspable objects (a cup and a bottle) built from the same
primitive shapes the YOLO v3 model was trained on (diff_drive_yolo/tools/dataset).

Both objects are 9 cm in diameter so the parallel gripper (12.2 cm opening) can
grasp either one. The cup is turned to yaw -45 deg (CUP_YAW): with the handle
facing the camera (yaw 0) YOLO scored the cup only 0.12, at -45 deg 0.75
(tested 2026-11-26). At -45 deg the handle also stays ~9 mm clear of the
fingers, which close along world y in the top-down grasp.

Usage: python3 make_vision_world.py [--datagen]   (writes next to pick_place_world.sdf;
--datagen adds a boundingbox camera and class labels for YOLO training data)
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "..", "ros2_ws", "src", "tm5s_gripper_demo", "worlds")
BASE = os.path.join(PKG, "pick_place_world.sdf")
OUT = os.path.join(PKG, "vision_world.sdf")

# Camera on the far (+x) side of the table, looking back at the work area.
CAM_POS = (1.45, 0.50, 1.45)
CAM_TARGET = (0.45, 0.50, 0.72)
CAM_HFOV = 0.9
CAM_W, CAM_H = 640, 480

R = 0.045  # object radius (both objects)
CUP_YAW = -math.pi / 4


def mat(rgba):
    return (f"<material><ambient>{rgba}</ambient><diffuse>{rgba}</diffuse>"
            "<specular>0.3 0.3 0.3 1</specular></material>")


def cyl(name, r, length, z, rgba, collide=True):
    v = (f'<visual name="{name}"><pose>0 0 {z} 0 0 0</pose><geometry><cylinder><radius>{r}</radius>'
         f'<length>{length}</length></cylinder></geometry>{mat(rgba)}</visual>')
    if collide:
        v += (f'<collision name="{name}_c"><pose>0 0 {z} 0 0 0</pose><geometry><cylinder><radius>{r}</radius>'
              f'<length>{length}</length></cylinder></geometry><surface><friction><ode><mu>2.0</mu><mu2>2.0</mu2>'
              '</ode></friction></surface></collision>')
    return v


def box(name, size, xyz, rgba):
    s = " ".join(str(x) for x in size)
    p = " ".join(str(x) for x in xyz)
    return (f'<visual name="{name}"><pose>{p} 0 0 0</pose><geometry><box><size>{s}</size></box></geometry>{mat(rgba)}</visual>'
            f'<collision name="{name}_c"><pose>{p} 0 0 0</pose><geometry><box><size>{s}</size></box></geometry></collision>')


def inertial(mass, r, h):
    ixx = mass * (3 * r * r + h * h) / 12
    izz = mass * r * r / 2
    return (f"<inertial><pose>0 0 {h / 2} 0 0 0</pose><mass>{mass}</mass><inertia><ixx>{ixx:.6f}</ixx><iyy>{ixx:.6f}</iyy>"
            f"<izz>{izz:.6f}</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial>")


def cup(name, x, y, rgba):
    h = 0.105
    body = cyl("body", R, h, h / 2, rgba) + cyl("coffee", R - 0.005, 0.004, h - 0.002, "0.25 0.12 0.04 1", collide=False)
    # Handle on +x side.
    handle = (box("handle_top", (0.0315, 0.012, 0.012), (R + 0.0135, 0, 0.084), rgba)
              + box("handle_side", (0.012, 0.012, 0.0595), (R + 0.0265, 0, 0.0525), rgba)
              + box("handle_bottom", (0.0315, 0.012, 0.012), (R + 0.0135, 0, 0.021), rgba))
    return (f'<model name="{name}"><pose>{x} {y} 0.70 0 0 {CUP_YAW:.4f}</pose><link name="link">{inertial(0.15, R, h)}'
            f'{body}{handle}</link></model>')


BOTTLE_H = 0.16  # total height: body 0.11 + neck 0.035 + cap 0.015


def bottle(name, x, y, rgba, cap_rgba):
    # Short bottle: the fingers reach only 8.5 cm below the gripper body, so the
    # gripper body must clear the top while the fingers still hold the body.
    hb = 0.11
    parts = (cyl("body", R, hb, hb / 2, rgba) + cyl("neck", 0.0225, 0.035, hb + 0.0175, rgba)
             + cyl("cap", 0.024, 0.015, hb + 0.0425, cap_rgba)
             + cyl("label", R + 0.0005, 0.045, 0.06, "0.95 0.95 0.95 1", collide=False))
    return (f'<model name="{name}"><pose>{x} {y} 0.70 0 0 0</pose><link name="link">{inertial(0.2, R, hb)}'
            f'{parts}</link></model>')


def camera():
    dx, dy, dz = (CAM_TARGET[i] - CAM_POS[i] for i in range(3))
    yaw = math.atan2(dy, dx)
    pitch = math.atan2(-dz, math.hypot(dx, dy))
    return f'''<model name="table_camera"><static>true</static>
      <pose>{CAM_POS[0]} {CAM_POS[1]} {CAM_POS[2]} 0 {pitch:.4f} {yaw:.4f}</pose>
      <link name="link">
        <visual name="body"><geometry><box><size>0.06 0.10 0.05</size></box></geometry>{mat("0.1 0.1 0.1 1")}</visual>
        <sensor name="table_camera" type="camera">
          <always_on>1</always_on><update_rate>5</update_rate><visualize>false</visualize>
          <topic>/table_camera/image</topic>
          <camera><horizontal_fov>{CAM_HFOV}</horizontal_fov>
            <image><width>{CAM_W}</width><height>{CAM_H}</height><format>R8G8B8</format></image>
            <clip><near>0.05</near><far>10</far></clip></camera>
        </sensor>
      </link></model>'''


LABEL_PLUGIN = '<plugin filename="gz-sim-label-system" name="gz::sim::systems::Label"><label>{}</label></plugin>'


def bbox_camera():
    """Boundingbox camera at the table camera's pose (labels: COCO id + 1)."""
    dx, dy, dz = (CAM_TARGET[i] - CAM_POS[i] for i in range(3))
    yaw = math.atan2(dy, dx)
    pitch = math.atan2(-dz, math.hypot(dx, dy))
    return f'''<model name="label_camera"><static>true</static>
      <pose>{CAM_POS[0]} {CAM_POS[1]} {CAM_POS[2]} 0 {pitch:.4f} {yaw:.4f}</pose>
      <link name="link"><sensor name="bbox" type="boundingbox_camera"><update_rate>5</update_rate><always_on>1</always_on>
        <topic>/table_camera/boxes</topic>
        <camera><box_type>2d</box_type><horizontal_fov>{CAM_HFOV}</horizontal_fov>
          <image><width>{CAM_W}</width><height>{CAM_H}</height></image><clip><near>0.05</near><far>10</far></clip></camera>
      </sensor></link></model>'''


def main():
    datagen = "--datagen" in sys.argv
    s = open(BASE).read()
    s = s.replace('<world name="tm5s_pick_place">', '<world name="tm5s_vision">')
    sensors = ('<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">'
               '<render_engine>ogre2</render_engine></plugin>')
    s = s.replace('<plugin filename="gz-sim-scene-broadcaster-system"',
                  sensors + '\n    <plugin filename="gz-sim-scene-broadcaster-system"', 1)
    # Move the old cube off the work area (kept so the old demo scripts still find it).
    s = s.replace("<pose>0.40 0.50 0.73 0 0 0</pose>", "<pose>0.95 1.20 0.73 0 0 0</pose>")
    cup_sdf = cup("cup", 0.40, 0.55, "0.92 0.92 0.92 1")
    bottle_sdf = bottle("bottle", 0.50, 0.35, "0.08 0.65 0.12 1", "0.8 0.1 0.1 1")
    if datagen:  # labels for the boundingbox camera: cup 42, bottle 40
        cup_sdf = cup_sdf.replace("</link></model>", "</link>" + LABEL_PLUGIN.format(42) + "</model>")
        bottle_sdf = bottle_sdf.replace("</link></model>", "</link>" + LABEL_PLUGIN.format(40) + "</model>")
    objs = camera() + "\n    " + cup_sdf + "\n    " + bottle_sdf
    if datagen:
        objs += "\n    " + bbox_camera()
    s = s.replace("  </world>", "    " + objs + "\n  </world>")
    out = OUT.replace(".sdf", "_datagen.sdf") if datagen else OUT
    open(out, "w").write(s)
    print("wrote", out)


if __name__ == "__main__":
    main()
