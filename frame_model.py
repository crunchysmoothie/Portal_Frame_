from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class NodeLoad:
    direction: str
    magnitude: float
    case: Optional[str] = None

@dataclass
class MemberLoad:
    direction: str
    w1: float
    w2: float
    x1: Optional[float] = None
    x2: Optional[float] = None
    case: Optional[str] = None

@dataclass
class Node:
    name: str
    x: float
    y: float
    z: float
    loads: List[NodeLoad] = field(default_factory=list)

@dataclass
class Member:
    name: str
    i_node: str
    j_node: str
    material: str
    type: str
    length: float
    loads: List[MemberLoad] = field(default_factory=list)

@dataclass
class PortalFrame:
    frame_data: List[Dict]
    nodes: Dict[str, Node]
    members: List[Member]
    supports: Dict[str, Dict]
    materials: Dict[str, Dict]
    rotational_springs: List[Dict]
    serviceability_load_combinations: List[Dict]
    load_combinations: List[Dict]
    geometry_parameters: Dict
    steel_grade: List[Dict]
    wind_data: List[Dict] = field(default_factory=list)
    wind_zones_0U: List[Dict] = field(default_factory=list)
    wind_zones_0D: List[Dict] = field(default_factory=list)
    wind_zones_90: List[Dict] = field(default_factory=list)

def load_portal_frame(path: str) -> 'PortalFrame':
    import json
    with open(path) as f:
        data = json.load(f)

    nodes = {}
    for n in data.get('nodes', []):
        nodes[n['name']] = Node(n['name'], n['x'], n['y'], n['z'])

    members = []
    for m in data.get('members', []):
        members.append(Member(m['name'], m['i_node'], m['j_node'],
                               m['material'], m['type'].lower(), m['length']))

    # attach loads
    for nl in data.get('nodal_loads', []):
        node = nodes.get(nl['node'])
        if node:
            node.loads.append(NodeLoad(nl['direction'], nl['magnitude'], nl.get('case')))

    for ml in data.get('member_loads', []):
        target = next((m for m in members if m.name == ml['member']), None)
        if target:
            target.loads.append(MemberLoad(ml['direction'], ml['w1'], ml['w2'],
                                          ml.get('x1'), ml.get('x2'), ml.get('case')))

    return PortalFrame(
        frame_data=data.get('frame_data', []),
        nodes=nodes,
        members=members,
        supports={s['node']: {k: s.get(k, False) for k in ('DX','DY','DZ','RX','RY','RZ')} for s in data.get('supports', [])},
        materials={m['name']: {'E': m['E'], 'G': m['G'], 'nu': m['nu'], 'rho': m['rho']} for m in data.get('materials', [])},
        rotational_springs=data.get('rotational_springs', []),
        serviceability_load_combinations=data.get('serviceability_load_combinations', []),
        load_combinations=data.get('load_combinations', []),
        geometry_parameters=data.get('geometry_parameters', {}),
        steel_grade=data.get('steel_grade', []),
        wind_data=data.get('wind_data', []),
        wind_zones_0U=data.get('wind_zones_0U', []),
        wind_zones_0D=data.get('wind_zones_0D', []),
        wind_zones_90=data.get('wind_zones_90', [])
    )
