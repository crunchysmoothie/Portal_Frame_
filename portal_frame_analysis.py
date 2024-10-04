from PyNite import FEModel3D
from PyNite.Visualization import Renderer
import member_database as mdb

# Create a new model
frame = FEModel3D()

# Define the nodes
frame.add_node('N1', 0, 0, 0)
frame.add_node('N2', 0, 5000, 0)
frame.add_node('N3', 4000, 7000, 0)
frame.add_node('N4', 8000, 5000, 0)
frame.add_node('N5', 8000, 0, 0)

# Define the supports
frame.def_support('N1', True, True, True, True, True, True)
frame.def_support('N5', True, True, True, True, True, True)

# Create members (all members will have the same properties in this example)
member_db = mdb.load_member_database()
rafter_section_name = '254x146x31'
rmem_properties = mdb.member_properties(rafter_section_name, member_db)
column_section_name = '356x171x45'
cmem_properties = mdb.member_properties(column_section_name, member_db)

RIx = rmem_properties['Ix']*10**6
RIy = rmem_properties['Iy']*10**6
RJ = rmem_properties['J']*10**3
RA = rmem_properties['A']*10**3

CIx = cmem_properties['Ix']*10**6
CIy = cmem_properties['Iy']*10**6
CJ = cmem_properties['J']*10**3
CA = cmem_properties['A']*10**3

# Define a material
E = 200
G = 80
nu = 0.3
rho = 7.8E-9
frame.add_material('Steel', E, G, nu, rho)

frame.add_member('M1', 'N1', 'N2', 'Steel', CIy, CIx, CJ, CA)
frame.add_member('M2', 'N2', 'N3', 'Steel', RIy, RIx, RJ, RA)
frame.add_member('M3', 'N3', 'N4', 'Steel', RIy, RIx, RJ, RA)
frame.add_member('M4', 'N4', 'N5', 'Steel', CIy, CIx, CJ, CA)

# Add nodal loads
frame.add_node_load('N3', 'FY', -50)

# Add distributed loads
frame.add_member_dist_load('M1', 'Fy', -6/1000, -6/1000)

# Analyze the model
frame.analyze(check_statics=True)

# Render the deformed shape
rndr = Renderer(frame)
rndr.annotation_size = 250
rndr.render_loads = True
rndr.deformed_shape = True
rndr.deformed_scale = 100
rndr.render_model()

print(frame.members['M1'].max_moment('Mz')/1000,
      frame.members['M1'].min_moment('Mz')/1000)
print(frame.members['M2'].max_moment('Mz')/1000,
      frame.members['M2'].min_moment('Mz')/1000)
# Correct the direction parameter to 'dx', 'dy', or 'dz'
print(frame.nodes['N3'].DY)
print(frame.nodes['N3'].DX)

def lightest_section():
      rafter = '254x146x31'
      column = '356x171x45'
      return rafter, column

