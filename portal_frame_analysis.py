from PyNite import FEModel3D
from PyNite.Visualization import Renderer
from PyNite import Reporting
import member_database as mdb
import json


def import_data(file):
    with open(file) as f:
        data = json.load(f)

        # Initialize dictionaries for the imported data
        nodes = {node['name']: {'x': node['x'], 'y': node['y'], 'z': node['z']} for node in data.get('nodes', [])}

        supports = {support['node']: {'DX': support['DX'], 'DY': support['DY'], 'DZ': support['DZ'],
                                      'RX': support['RX'], 'RY': support['RY'], 'RZ': support['RZ']}
                    for support in data.get('supports', [])}

        node_loads = {node_load['node']: {'direction': node_load['direction'], 'magnitude': node_load['magnitude'], 'case': node_load['case']}
                      for node_load in data.get('nodal_loads', [])}

        member_loads = {member_load['member']: {'direction': member_load['direction'],
                                                'w1': member_load['w1'], 'w2': member_load['w2'], 'case': member_load['case']}
                        for member_load in data.get('member_loads', [])}

        materials = {material['name']: {'E': material['E'], 'G': material['G'],
                                        'nu': material['nu'], 'rho': material['rho']}
                     for material in data.get('materials', [])}

        # Return all the items except for members
        return {
            'nodes': nodes,
            'supports': supports,
            'nodal_loads': node_loads,
            'member_loads': member_loads,
            'materials': materials
        }

def lightest_section():
# Create a new model
    frame = FEModel3D()

    data = import_data('input_data.json')

    for node in data['nodes']:
        frame.add_node(node, data['nodes'][node]['x'], data['nodes'][node]['y'], data['nodes'][node]['z'])

    for support in data['supports']:
        frame.def_support(support, data['supports'][support]['DX'], data['supports'][support]['DY'], data['supports'][support]['DZ'],
                          data['supports'][support]['RX'], data['supports'][support]['RY'], data['supports'][support]['RZ'])

    for material in data['materials']:
        frame.add_material(material, data['materials'][material]['E'], data['materials'][material]['G'],
                           data['materials'][material]['nu'], data['materials'][material]['rho'])

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

    frame.add_member('M1', 'N1', 'N2', 'Steel_S355', CIy, CIx, CJ, CA)
    frame.add_member('M2', 'N2', 'N3', 'Steel_S355', RIy, RIx, RJ, RA)
    frame.add_member('M3', 'N3', 'N4', 'Steel_S355', RIy, RIx, RJ, RA)
    frame.add_member('M4', 'N4', 'N5', 'Steel_S355', CIy, CIx, CJ, CA)

    for node_load in data['nodal_loads']:
        frame.add_node_load(node_load, data['nodal_loads'][node_load]['direction'], data['nodal_loads'][node_load]['magnitude'], data['nodal_loads'][node_load]['case'])

    for member_load in data['member_loads']:
        frame.add_member_dist_load(member_load, data['member_loads'][member_load]['direction'],
                                 data['member_loads'][member_load]['w1'], data['member_loads'][member_load]['w2'],
                                   None, None, data['member_loads'][member_load]['case'])

    frame.add_load_combo('Combo 1', factors={'D': 1.0, 'L': 1.0})
    frame.add_load_combo('1.0 DL', factors={'D': 1.0, 'L': 0})
    frame.add_load_combo('1.2 DL + 1.6 LL', factors={'D': 1.2, 'L': 1.6})

    frame.add_member_self_weight('FY', 1, 'D')

    # Analyze the model
    frame.analyze(check_statics=True)

    # # Render the deformed shape
    # rndr = Renderer(frame)
    # rndr.annotation_size = 250
    # rndr.render_loads = True
    # rndr.deformed_shape = True
    # rndr.deformed_scale = 100
    # rndr.render_model()

    print("Member M1 Max Mz:", frame.members['M1'].max_moment('Mz') / 1000, "kN-m")
    print("Member M1 Min Mz:", frame.members['M1'].min_moment('Mz') / 1000, "kN-m")
    print("Member M2 Max Mz:", frame.members['M2'].max_moment('Mz') / 1000, "kN-m")
    print("Member M2 Min Mz:", frame.members['M2'].min_moment('Mz') / 1000, "kN-m")
    print("Node N3 DY Displacement:", frame.nodes['N3'].DY, "mm")
    print("Node N3 DX Displacement:", frame.nodes['N3'].DX, "mm")
    print("Node N4 DZ Displacement:", frame.nodes['N4'].DX, "mm")


    return

lightest_section()
# data = import_data('input_data.json')
