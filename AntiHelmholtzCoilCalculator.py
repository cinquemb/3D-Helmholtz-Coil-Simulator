#%% imports
import numpy as np
import magpylib as magpy
from scipy.spatial.transform import Rotation as R
from scipy.optimize import minimize
from magpylibUtils import coil

np.set_printoptions(suppress=True)

MU0 = 4*np.pi*1e-7
MM = 1e-3

#vacuum roughing pump: 3.75*10^-2 Torr: https://www.tokopedia.com/indotara-persada/set-vacuum-pump-mesin-pompa-vacuum-orion-vp-rs-1?extParam=ivf%3Dfalse%26keyword%3Droughing+pump+vacuum%26search_id%3D202603260729084734BA6F3DE83D1A8NOP%26src%3Dsearch&t_id=1774510839605&t_st=1&t_pp=search_result&t_efo=search_pure_goods_card&t_ef=goods_search&t_sm=&t_spt=search_result
# cheaper one https://www.tokopedia.com/nw-official-shop/vacuum-pump-ac-air-vacuum-pump-single-stage-vp125-untuk-servis-isi-ulang-freon-kompresor-vakum-berkualitas-pompa-vakum-ac-1-4-pk-1732477640075741175
#%% ---------------- CONFIG ----------------
#https://bntechgo.com/bntechgo-34-awg-magnet-wire-enameled-copper-wire-enameled-magnet-winding-wire-5-0-lb-0-0063-diameter-1-spool-coil-red-temperature-rating-155-degrees-celsius-widely-used-for-transformers-and-inductors/
AllCoilsWireDiameter = 0.160 + 0.015  # 0.16mm copper + ~0.015mm enamel build
wireResistance = 0.851                # Ohm/m for 34 AWG




#this is $35 for 4 channels with 3.6 x 3.6 mm^2 sensitive area... https://www.alibaba.com/product-detail/AFBR-S4N44P044M-New-and-original-Integrated_1601376707497.html?spm=a2700.prosearch.normal_offer.d_image.353d67afpfiP84&priceId=c1a8967ab6ef45bb8066adf55c3dde5e
#AllCoilsWireDiameter = (0.56 + 0.047)*1.09  # mm
#https://www.broadcom.com/products/optical-sensors/silicon-photomultiplier-sipm/high-performance-sipm-nuv-mt
#Still need to use a tophat DOE in the ~1cm cavity in order to sloww the calcim atoms dowm
#https://www.taiheiboeki.co.jp/en/laser-optics/holoor/top-hat_doe/list/#block2759-3515
# 6 850 beam combine to 1 850 nm- >litro -> 844 -> shg -> 422nm --> laser signal stabilizer -> pass thrue 405 DOE -> split into 3 paths with 3 mirrors
#https://www.alibaba.com/product-detail/The-multimode-850nm-500mw-laser-diode_1601428629520.html?spm=a2700.galleryofferlist.normal_offer.d_title.5dc613a0DD74kO&priceId=1e2e65de941d48c0afc617f1c457d5d8
'''
Model   Wavelength
 (nm)   Diameter of incidence
 (mm)   pattern
 Shape  Divergence angle
 θf (mRad)  Pattern Size
 (μm) @EFL100mm Remarks
ST-320-SYA  405 20  circular    0.04    4   Small T
~$3k
'''

'''

2 more non static gradient coils -> drive the x, and y coils with the floquet drive... but y shifted by 90 deg
'''


#wireResistance = 0.07153  # Ohm/m

TARGET_GRADIENT = .2      # T/m
MAX_CURRENT = 0.02         # A

EVEN_LAYERS = 20
ODD_LAYERS  = 19

MIN_CLEARANCE_MM = 3.0
AXIS_CLEARANCE_MM = 2.0

MAX_THICKNESS_RATIO = 1.5  # critical

DZ_MM = 0.02   # larger step = faster + more stable

IDEAL_SPACING_RATIO = 1.0   # spacing ≈ radius

#%% ---------------- CORE ----------------

def build_pair(r, s, I, loops, n_layers, axis):
    # Split layers into even/odd for hexagonal packing
    even = np.ceil(n_layers / 2)
    odd = n_layers // 2
    
    m = coil_metrics(r, loops, I, n_layers)

    min_spacing = m["thickness"] + MIN_CLEARANCE_MM
    spacing = max(r * s, min_spacing)

    col = magpy.Collection()
    for z in [-spacing, spacing]:
        col = coil(
            I=I,
            coilIntDiameter=r * MM,
            referencePosition=[0,0,z * MM],
            wireDiameter=AllCoilsWireDiameter * MM,
            loopsInEachEvenLayer=loops,
            evenLayers=even,
            oddLayers=odd,
            collectionToAdd=col
        )

    # anti-Helmholtz flip
    half = len(col.sources)//2
    for i, src in enumerate(col.sources):
        if i >= half:
            src.current *= -1

    # rotate
    if axis == 'x':
        col.rotate(R.from_euler('y', 90, degrees=True), anchor=[0,0,0])
    elif axis == 'y':
        col.rotate(R.from_euler('x', -90, degrees=True), anchor=[0,0,0])
    return col


def build_system(params):
    # params: [rx, sx, lx, nx, ry, sy, ly, ny, rz, sz, lz, nz, I_shared]
    p = params[:-1].reshape(3, 4)
    I_shared = params[-1]
    
    return magpy.Collection(
        build_pair(p[0,0], p[0,1], I_shared, (p[0,2]), (p[0,3]), 'x'),
        build_pair(p[1,0], p[1,1], I_shared, (p[1,2]), (p[1,3]), 'y'),
        build_pair(p[2,0], p[2,1], I_shared, (p[2,2]), (p[2,3]), 'z')
    )

def build_system_fast(params):
    p = params[:-1].reshape(3, 4)
    I_shared = params[-1]
    
    col = magpy.Collection()
    
    for i, axis in enumerate(['x', 'y', 'z']):
        r, s, loops, layers = p[i]
        
        # Calculate total turns as a float (smooth!)
        even = layers / 2
        odd = layers / 2
        total_turns = (even * loops) + (odd * (loops - 1))
        
        # Effective current of the whole bundle
        eff_I = I_shared * total_turns
        
        # Geometry for the "bundle center"
        thickness = layers * (np.sqrt(3)/2 * AllCoilsWireDiameter)
        spacing = max(r * s, thickness + MIN_CLEARANCE_MM)
        
        # Represent the pair as just 2 loops with massive current
        for z in [-spacing, spacing]:
            loop = magpy.current.Circle(
                current=eff_I if z < 0 else -eff_I, # Anti-Helmholtz
                diameter=r * MM,
                position=(0, 0, z * MM)
            )
            
            # Rotate bundle based on axis
            if axis == 'x':
                loop.rotate(R.from_euler('y', 90, degrees=True), anchor=(0,0,0))
            elif axis == 'y':
                loop.rotate(R.from_euler('x', -90, degrees=True), anchor=(0,0,0))
                
            col.add(loop)
            
    return col



def fast_gradient(system):
    step = DZ_MM * MM

    # evaluate all points at once (big speedup)
    pts = np.array([
        [ step,0,0], [-step,0,0],
        [0, step,0], [0,-step,0],
        [0,0, step], [0,0,-step],
        [0,0,0]
    ])

    B = system.getB(pts)

    gx = (B[0,0] - B[1,0])/(2*step)
    gy = (B[2,1] - B[3,1])/(2*step)
    gz = (B[4,2] - B[5,2])/(2*step)

    B0 = B[6]

    return gx, gy, gz, B0


#%% ---------------- GEOMETRY ----------------

def coil_metrics(r, loops, I, n_layers):
    step = np.sqrt(3)/2 * AllCoilsWireDiameter
    thickness = n_layers * step
    width = AllCoilsWireDiameter * loops
    outer_d = r + 2*thickness

    even = int(np.ceil(n_layers / 2))
    odd = int(n_layers // 2)
    turns = (even * loops) + (odd * (loops - 1))
    
    mean_len = np.pi * (r + thickness/2) * MM # more accurate mean length
    wire_len = mean_len * turns
    Res = wire_len * wireResistance
    Pow = I**2 * Res

    return {
        "thickness": thickness, "width": width, "outer_d": outer_d,
        "turns": turns, "wire_len": wire_len, "R": Res, "P": Pow
    }


#%% ---------------- OBJECTIVE ----------------
def nesting_penalty(rx, ry, rz):
    # enforce X > Y > Z + clearance
    return (
        max(0, rz - ry + 2.0) +
        max(0, ry - rx + 2.0)
    )

def objective(x):
    system = build_system_fast(x)
    gx, gy, gz, B0 = fast_gradient(system)

    # avoid divide-by-zero
    if abs(gz) < 1e-6:
        return 1e3

    # enforce correct gradient structure directly
    ratio_penalty = abs(gx/gz + 0.5) + abs(gy/gz + 0.5)

    # maximize gradient
    strength = -abs(gz)

    # nesting
    rx, ry, rz = x[0], x[4], x[8]
    nest = max(0, rz - ry + 2.0) + max(0, ry - rx + 2.0)

   # Z thickness constraint (strong)
    rz, sz, lz, nz = x[8], x[9], x[10], x[11]
    m_z = coil_metrics(rz, lz, x[-1], nz)

    target_spacing = rz * sz
    actual_spacing = max(target_spacing, m_z["thickness"] + MIN_CLEARANCE_MM)

    # force field-limited regime (not boundary-hugging)
    thickness_penalty = max(0, m_z["thickness"] - 0.5 * target_spacing)
    spacing_penalty   = max(0, (m_z["thickness"] + MIN_CLEARANCE_MM) - target_spacing)

    return (
        20.0 * ratio_penalty +
        8000.0 * strength +
        10.0 * nest + 
        300.0 * thickness_penalty + 
        200.0 * spacing_penalty
    )




#%% ---------------- OPTIMIZER ----------------

def optimize():
      # 4 params per axis: [r, s, loops, layers] + 1 shared Current at the end
    x0 = [
        35, 1.0, 10, 20,  # X
        28, 1.0, 10, 20,  # Y
        18, 0.7, 10, 50,  # Z
        0.02              # Shared Current (I)
    ]

    bounds = [
        (20, 50), (0.6, 1.5), (4, 60), (5, 100), # X
        (15, 40), (0.6, 1.5), (4, 60), (5, 100), # Y
        (5, 22), (0.5, 1.5), (6, 30), (5, 100), # Z
        (0.019, 0.02)                          # Shared Current
    ]

    res = minimize(objective, x0, method='L-BFGS-B', bounds=bounds, options={'maxiter': 1000})
    return res.x



#%% ---------------- RUN ----------------

#%% ---------------- RUN ----------------

params = optimize()

# Reshape into a 3x5 matrix: [Axis, Parameter]
# Rows: 0=X, 1=Y, 2=Z
# Cols: 0=r, 1=s, 2=I, 3=loops, 4=layers
p = params[:-1].reshape(3, 4)

# Build the final system for verification
system = build_system(params)
gx, gy, gz, B0 = fast_gradient(system)


#%% ---------------- OUTPUT ----------------

print("\n=== FIELD RESULT ===")
print(f"dBx/dx = {gx:.6f}")
print(f"dBy/dy = {gy:.6f}")
print(f"dBz/dz = {gz:.6f}")
print(f"Trace  = {gx+gy+gz:.6e}")
print(f"Center field = {B0}")

#%% ---------------- FULL BUILD INSTRUCTIONS ----------------


def calculate_inductance(turns, mean_radius_mm, width_mm, thickness_mm):
    """
    Wheeler's formula for multi-layer solenoid inductance.
    L (uH) = (31.6 * N^2 * r1^2) / (6*r1 + 9*l + 10*d)
    where r1 = mean radius, l = axial length (thickness), d = radial depth (width)
    Converted to metric (mm).
    """
    # Convert mm to meters for SI L calculation, or use mm-optimized Wheeler
    # r, l, d in mm -> L in uH
    r = mean_radius_mm
    l = thickness_mm # Axial height
    d = width_mm     # Radial width
    
    numerator = 31.6 * (turns**2) * (r**2)
    denominator = (6 * r) + (9 * l) + (10 * d)
    
    return (numerator / denominator) / 1e6 # Return in Henrys

def print_coil_build(axis, r, s, I, loops, n_layers, floquet_freq_hz=65536):
    # Split layers into even/odd for the winding logic
    even_layers = int(np.ceil(n_layers / 2))
    odd_layers = int(n_layers // 2)
    
    even_turns = int(loops)
    odd_turns  = int(loops) - 1

    # Use the updated metrics function
    m = coil_metrics(r, loops, I, n_layers)

    # Calculate Mean Radius for Inductance
    mean_r = (r + m['outer_d'])/4.0 # (Inner_R + Outer_R) / 2
    
    # Calculate Inductance
    L = calculate_inductance(m['turns'], mean_r, m['width'], m['thickness'])
    
    # Calculate Phase Lag at Floquet Frequency: theta = atan(omega*L / R)
    omega = 2 * np.pi * floquet_freq_hz
    phase_lag_deg = np.degrees(np.arctan2(omega * L, m['R']))
    
    min_spacing = m["thickness"] + MIN_CLEARANCE_MM
    spacing = max(r * s, min_spacing)
    face_gap = spacing - m["thickness"]

    print(f"\n================ {axis.upper()} COIL =================")
    print("Configuration: Anti-Helmholtz pair")

    print("\n--- Geometry ---")
    print(f"Inner diameter:        {r:.3f} mm")
    print(f"Outer diameter:        {m['outer_d']:.3f} mm")
    print(f"Coil width (radial):   {m['width']:.3f} mm")
    print(f"Coil height (axial):   {m['thickness']:.3f} mm")
    print(f"Separation (center):   {spacing:.3f} mm")
    print(f"Separation (face-face): {face_gap:.3f} mm")

    if face_gap < 0.1:
        print("⚠️ WARNING: Extremely tight clearance!")

    print("\n--- Winding ---")
    print(f"Even layers: {even_layers} × {even_turns} turns")
    print(f"Odd layers:  {odd_layers} × {odd_turns} turns")
    print(f"Total turns per coil: {m['turns']}")

    print(f"\n--- Electrical & Magnetic ---")
    print(f"Current:      {I*1000:.3f} mA")
    print(f"Resistance:   {m['R']:.4f} Ohm")
    print(f"Inductance:   {L*1000:.4f} mH")  # <--- NEW
    print(f"Lag @ {floquet_freq_hz/1000:.1f}kHz: {phase_lag_deg:.2f}°") # <--- NEW
    print(f"Voltage Drop: {I * m['R']:.3f} V") # Crucial for your 4-20mA driver

    print("\n--- Wire ---")
    print(f"Wire length per coil: {m['wire_len']:.3f} m")
    print(f"Total wire (pair):    {2*m['wire_len']:.3f} m")

    print("\n--- Orientation ---")
    if axis == 'z':
        print("Axis: Z (standard vertical pair)")
    elif axis == 'x':
        print("Axis: X (horizontal, along magnet bore)")
    elif axis == 'y':
        print("Axis: Y (horizontal, transverse)")

#%% PRINT ALL 3 AXES

# p is your (3, 4) matrix from params[:-1].reshape(3, 4)
I_shared = params[-1]

# Axis X: radius=p[0,0], spacing=p[0,1], loops=p[0,2], layers=p[0,3]
print_coil_build('x', p[0,0], p[0,1], I_shared, p[0,2], p[0,3])

# Axis Y: radius=p[1,0], spacing=p[1,1], loops=p[1,2], layers=p[1,3]
print_coil_build('y', p[1,0], p[1,1], I_shared, p[1,2], p[1,3])

# Axis Z: radius=p[2,0], spacing=p[2,1], loops=p[2,2], layers=p[2,3]
print_coil_build('z', p[2,0], p[2,1], I_shared, p[2,2], p[2,3])


#%% display
#system.show()