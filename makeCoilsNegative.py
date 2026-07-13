import FreeCAD as App
import Part
import Draft

doc = App.ActiveDocument if App.ActiveDocument else App.newDocument()

# 50% infill, need to bake (if doing so, scale up by 2% before printing)

# ================= 1. CALCULATOR SPECS & CONFIG =================
coils_data = {
    'x': [35.242/2, 1.671, 2.999, 52.864/2],
    'y': [28.670/2, 1.573, 2.960, 43.005/2],
    'z': [9.664/2,  5.250, 2.514, 5.514/2]
}

FLANGE_T = 2.0  
STRUT_D = 4.0    
CUBE_SIZE = 110.0        
CUBE_ROD_D = 5.0         
ANCHOR_ROD_D = 2.5       
CAGE_NODE_DIST = 35.0    
WIRE_HOLE_R = 1.0
WIRE_D = 0.175  
WINDING_TOLERANCE = 0.25 * WIRE_D   

# Motor Shaft Config
SHAFT_D = 6.0            
SHAFT_LEN = 20.0         
SHAFT_FLAT = 0.5         

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# --- MOLD CONFIGURATION FOR NEGATIVE SPACE ---
MOLD_MARGIN = 10.0  # Extra thickness around your cage walls (in mm)
SPOUT_RADIUS = 4.0  # Width of the resin pouring hole (8mm diameter)
VENT_RADIUS = 1.5   # Width of air vent escapes (3mm diameter)

# ================= 2. GEOMETRY FUNCTIONS =================

def make_bobbin(r, w, h):
    h_adj = h + WINDING_TOLERANCE
    outer_r = r + w + FLANGE_T
    total_h = h_adj + (FLANGE_T * 2)
    body = Part.makeCylinder(outer_r, total_h, App.Vector(0,0,-total_h/2))
    bore = Part.makeCylinder(r - FLANGE_T, total_h + 2, App.Vector(0,0,-(total_h+2)/2))
    groove = Part.makeCylinder(outer_r + 1, h_adj, App.Vector(0,0,-h_adj/2)).cut(
             Part.makeCylinder(r, h_adj + 1, App.Vector(0,0,-(h_adj+1)/2)))
    bobbin = body.cut(bore).cut(groove)
    hole = Part.makeCylinder(WIRE_HOLE_R, FLANGE_T * 4, App.Vector(r-2, 0, h_adj/2 + FLANGE_T/2), App.Vector(1,0,0))
    return bobbin.cut(hole)

def create_label(text, pos, rot_axis, rot_angle, size=8.0):
    try:
        s = Draft.make_shapestring(text, FONT_PATH, size)
        s.Placement = App.Placement(pos, App.Rotation(rot_axis, rot_angle))
        extrude = Part.makeExtrude(s.Shape, App.Vector(0,0,2.0))
        extrude.translate(App.Vector(0,0,-1.0)) 
        return extrude
    except: return None

# ================= 3. CONSTRUCTION =================
all_parts = []

# Coils construction with "Nesting" logic
for axis, (r, w, h, s) in coils_data.items():
    r_mid = r - 4.0 if axis == 'x' else r + 4.0 
    base_outer = make_bobbin(r, w, h)
    base_mid = make_bobbin(r_mid, w, h)

    for side in [1, 0, -1]:
        if side == 0:
            if axis == 'z': continue 
            c = base_mid.copy()
        else:
            c = base_outer.copy()
            
        c.translate(App.Vector(0, 0, s * side))
        
        if axis == 'x': c.rotate(App.Vector(0,0,0), App.Vector(0,1,0), 90)
        elif axis == 'y': c.rotate(App.Vector(0,0,0), App.Vector(1,0,0), 90)

        all_parts.append(c)

# Main Axial Struts
h_s = CUBE_SIZE / 2.0
all_parts.append(Part.makeCylinder(STRUT_D/2, CUBE_SIZE, App.Vector(-h_s,0,0), App.Vector(1,0,0)))
all_parts.append(Part.makeCylinder(STRUT_D/2, CUBE_SIZE, App.Vector(0,-h_s,0), App.Vector(0,1,0)))
all_parts.append(Part.makeCylinder(STRUT_D/2, CUBE_SIZE, App.Vector(0,0,-h_s), App.Vector(0,0,1)))

# Cube Frame
corners = [App.Vector(x, y, z) for x in [h_s, -h_s] for y in [h_s, -h_s] for z in [h_s, -h_s]]
for i in range(len(corners)):
    for j in range(i + 1, len(corners)):
        if (corners[i] - corners[j]).Length < CUBE_SIZE + 0.1:
            edge = Part.makeCylinder(CUBE_ROD_D/2, CUBE_SIZE, corners[i], corners[j]-corners[i])
            if corners[i].z == corners[j].z == h_s or corners[i].z == corners[j].z == -h_s:
                rail_cut = Part.makeBox(CUBE_SIZE+10, 4, 2, App.Vector(-h_s-5, -2, h_s-1 if corners[i].z > 0 else -h_s-1))
                edge = edge.cut(rail_cut)
            all_parts.append(edge)

# --- MOTOR MOUNT (D-SHAFT) ---
motor_pos = App.Vector(h_s, h_s, h_s)
shaft_dir = App.Vector(1, 0, 0)
shaft = Part.makeCylinder(SHAFT_D/2, SHAFT_LEN, motor_pos, shaft_dir)
flat_cutter = Part.makeBox(SHAFT_LEN, SHAFT_D, SHAFT_D/2)
flat_cutter.translate(App.Vector(h_s, h_s - SHAFT_D/2, h_s + (SHAFT_D/2 - SHAFT_FLAT)))
all_parts.append(shaft.cut(flat_cutter))

# SiPM-Clearance Diamond Cage
nodes = [App.Vector(CAGE_NODE_DIST,0,0), App.Vector(-CAGE_NODE_DIST,0,0), App.Vector(0,CAGE_NODE_DIST,0), App.Vector(0,-CAGE_NODE_DIST,0), App.Vector(0,0,CAGE_NODE_DIST), App.Vector(0,0,-CAGE_NODE_DIST)]
for i in range(len(nodes)):
    for j in range(i + 1, len(nodes)):
        d = (nodes[i] - nodes[j]).Length
        if 48.0 < d < 52.0:
            all_parts.append(Part.makeCylinder(2.5/2, d, nodes[i], nodes[j] - nodes[i]))

# Star Anchors
for t in nodes:
    for c in corners:
        dist = (t-c).Length
        if 75.0 < dist < 82.0:
            all_parts.append(Part.makeCylinder(ANCHOR_ROD_D/2, dist, t, c-t))

# Axis Labels
axis_labels = [
    ('X', App.Vector(h_s - 10, 2, 2), App.Vector(0,0,1), 0),
    ('Y', App.Vector(2, h_s - 10, 2), App.Vector(0,0,1), 90),
    ('Z', App.Vector(2, 2, h_s - 10), App.Vector(0,1,0), -90)
]
for text, pos, axis, ang in axis_labels:
    lbl = create_label(text, pos, axis, ang, size=12.0)
    if lbl: all_parts.append(lbl)

# Branding Labels
labels = [('X-L_QUBIT', App.Vector(h_s, -15, -h_s+3), App.Vector(0,1,0), 90),
          ('Y-L_QUBIT', App.Vector(-15, h_s, -h_s+3), App.Vector(1,0,0), -90)]
for text, pos, axis, ang in labels:
    lbl = create_label(text, pos, axis, ang)
    if lbl: all_parts.append(lbl)

all_parts.append(Part.makeBox(14, 14, 2, App.Vector(-7,-7,-1)))

# ================= 4. COMPONENT FUSE =================
print("Fusing all components...")
fused_cage = all_parts[0]
for p in all_parts[1:]:
    fused_cage = fused_cage.fuse(p)

# ================= 5. NEGATIVE MOLD GENERATION =================
print("Generating negative space mold halves with pour spout...")

mold_dim = CUBE_SIZE + (MOLD_MARGIN * 2)
h_mold = mold_dim / 2.0

# Create top and bottom block shapes
mold_block_top = Part.makeBox(mold_dim, mold_dim, h_mold, App.Vector(-h_mold, -h_mold, 0))
mold_block_bottom = Part.makeBox(mold_dim, mold_dim, h_mold, App.Vector(-h_mold, -h_mold, -h_mold))

# --- POUR SPOUT & AIR VENTS CONFIG ---
# Main entry funnel cylinder going from the top face down into the core cavity
pour_spout = Part.makeCylinder(SPOUT_RADIUS, h_mold + 2, App.Vector(0, 0, -1), App.Vector(0, 0, 1))

# Air vents on opposite corners to allow clean fluid flow without locking bubbles
vent1 = Part.makeCylinder(VENT_RADIUS, h_mold + 2, App.Vector(-h_s + 5, -h_s + 5, -1), App.Vector(0, 0, 1))
vent2 = Part.makeCylinder(VENT_RADIUS, h_mold + 2, App.Vector(h_s - 5, h_s - 5, -1), App.Vector(0, 0, 1))

# Combine cutting systems
mold_cutters = pour_spout.fuse(vent1).fuse(vent2)

# Apply cuts to isolate negative geometries
negative_mold_top = mold_block_top.cut(fused_cage).cut(mold_cutters)
negative_mold_bottom = mold_block_bottom.cut(fused_cage)

# Export items back to FreeCAD tree
obj_top = doc.addObject("Part::Feature", "Negative_Mold_Top_Half")
obj_top.Shape = negative_mold_top

obj_bottom = doc.addObject("Part::Feature", "Negative_Mold_Bottom_Half")
obj_bottom.Shape = negative_mold_bottom

doc.recompute()
print("✅ Done! Mold blocks with resin injection gate and air vents ready.")
