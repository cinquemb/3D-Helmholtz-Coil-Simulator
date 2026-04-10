import FreeCAD as App
import Part
import Draft

doc = App.ActiveDocument if App.ActiveDocument else App.newDocument()

# ================= 1. CALCULATOR SPECS & CONFIG =================
coils_data = {
    'x': [35.242/2, 1.671, 2.999, 52.864/2],
    'y': [28.670/2, 1.573, 2.960, 43.005/2],
    'z': [9.664/2,  5.250, 2.514, 5.514/2]
}

FLANGE_T = 2.0  
STRUT_D = 4.0    
CUBE_SIZE = 110.0        # Slightly larger for better SiPM focal distance
CUBE_ROD_D = 5.0         # Heavy-duty frame for industrial stability
ANCHOR_ROD_D = 2.5       
CAGE_NODE_DIST = 35.0    # Optimized for SiPM 45-degree field of view
WIRE_HOLE_R = 1.0
WINDING_TOLERANCE = 0.2 

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

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

def create_label(text, pos, rot_axis, rot_angle):
    try:
        s = Draft.make_shapestring(text, FONT_PATH, 8.0)
        s.Placement = App.Placement(pos, App.Rotation(rot_axis, rot_angle))
        extrude = Part.makeExtrude(s.Shape, App.Vector(0,0,2.0))
        extrude.translate(App.Vector(0,0,-1.0)) 
        return extrude
    except: return None

# ================= 3. CONSTRUCTION =================
all_parts = []

# Coils
for axis, (r, w, h, s) in coils_data.items():
    base = make_bobbin(r, w, h)
    for side in [1, -1]:
        c = base.copy(); c.translate(App.Vector(0, 0, s * side))
        if axis == 'x': c.rotate(App.Vector(0,0,0), App.Vector(0,1,0), 90)
        elif axis == 'y': c.rotate(App.Vector(0,0,0), App.Vector(1,0,0), 90)
        all_parts.append(c)

# Main Axial Struts (Now reaching larger cube)
h_s = CUBE_SIZE / 2.0
all_parts.append(Part.makeCylinder(STRUT_D/2, CUBE_SIZE, App.Vector(-h_s,0,0), App.Vector(1,0,0)))
all_parts.append(Part.makeCylinder(STRUT_D/2, CUBE_SIZE, App.Vector(0,-h_s,0), App.Vector(0,1,0)))
all_parts.append(Part.makeCylinder(STRUT_D/2, CUBE_SIZE, App.Vector(0,0,-h_s), App.Vector(0,0,1)))

# Cube Frame with SiPM Rail Slits
corners = [App.Vector(x, y, z) for x in [h_s, -h_s] for y in [h_s, -h_s] for z in [h_s, -h_s]]
for i in range(len(corners)):
    for j in range(i + 1, len(corners)):
        if (corners[i] - corners[j]).Length < CUBE_SIZE + 0.1:
            edge = Part.makeCylinder(CUBE_ROD_D/2, CUBE_SIZE, corners[i], corners[j]-corners[i])
            # Functional modification: Flatten the top/bottom edges for better SiPM mounting
            if corners[i].z == corners[j].z == h_s or corners[i].z == corners[j].z == -h_s:
                rail_cut = Part.makeBox(CUBE_SIZE+10, 4, 2, App.Vector(-h_s-5, -2, h_s-1 if corners[i].z > 0 else -h_s-1))
                edge = edge.cut(rail_cut)
            all_parts.append(edge)

# SiPM-Clearance Diamond Cage
nodes = [App.Vector(CAGE_NODE_DIST,0,0), App.Vector(-CAGE_NODE_DIST,0,0), App.Vector(0,CAGE_NODE_DIST,0), App.Vector(0,-CAGE_NODE_DIST,0), App.Vector(0,0,CAGE_NODE_DIST), App.Vector(0,0,-CAGE_NODE_DIST)]
for i in range(len(nodes)):
    for j in range(i + 1, len(nodes)):
        d = (nodes[i] - nodes[j]).Length
        if 48.0 < d < 52.0: # Connect adjacent poles
            all_parts.append(Part.makeCylinder(2.5/2, d, nodes[i], nodes[j] - nodes[i]))

# Star Anchors (Rigidity for Floquet Drive)
for t in nodes:
    for c in corners:
        dist = (t-c).Length
        if 75.0 < dist < 82.0:
            all_parts.append(Part.makeCylinder(ANCHOR_ROD_D/2, dist, t, c-t))

# Labels & Central Plate
labels = [('X-L_QUBIT', App.Vector(h_s, -15, -h_s+3), App.Vector(0,1,0), 90),
          ('Y-L_QUBIT', App.Vector(-15, h_s, -h_s+3), App.Vector(1,0,0), -90)]
for text, pos, axis, ang in labels:
    lbl = create_label(text, pos, axis, ang)
    if lbl: all_parts.append(lbl)

all_parts.append(Part.makeBox(14, 14, 2, App.Vector(-7,-7,-1)))

# ================= 4. FINAL FUSE =================
print("Fusing SiPM-Optimized Floquet Rig...")
fused = all_parts[0]
for p in all_parts[1:]:
    fused = fused.fuse(p)

obj = doc.addObject("Part::Feature", "Floquet_SiPM_Cage")
obj.Shape = fused
doc.recompute()
print("✅ Done! Frame is optimized for SiPM imaging and Floquet drive.")
