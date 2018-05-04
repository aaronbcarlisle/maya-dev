# third-party
from maya.api import OpenMaya
from maya import cmds
from scipy import spatial

from colossus.Utils.DCC.maya import maya_utils

def get_ws_point_list(dag_path):
    shape_dag_path = maya_utils.get_dag_path_object(dag_path)
    mesh = OpenMaya.MFnMesh(shape_dag_path)
    ws_positions = mesh.getPoints(OpenMaya.MSpace.kWorld)

    # Return MVectors for the vertex world space positions.
    return [OpenMaya.MVector(p) for p in ws_positions]

def get_vertex_normal_point_list(dag_path):
    mesh_object = OpenMaya.MFnMesh(dag_path)
    point_array = mesh_object.getVertexNormals(False, space=OpenMaya.MSpace.kWorld)

    # Return MVectors for the vertex normal positions.
    return [OpenMaya.MVector(point_array[p]) for p in xrange(len(point_array))]

def KDTree_from_point_list(point_list):
    if type(point_list[0]) == OpenMaya.MVector:
        point_list = [[p.x, p.y, p.z] for p in point_list]

    return spatial.cKDTree(point_list)

def get_node_ws_matrix(node):
    ws_matrixx = cmds.xform(node, q=True, ws=True, m=True)
    matrix = OpenMaya.MMatrix(ws_matrixx)
    return OpenMaya.MTransformationMatrix(matrix)

def get_closest_position_in_KDTree(KDTree, mvector):
    positions = [mvector.x, mvector.y, mvector.z]
    out = KDTree.query(positions)

    # Return is a tuple containg the vertex id, the MVector position, and the distance.
    return out[1], OpenMaya.MVector(KDTree.data[out[1]].tolist()), out[0]


