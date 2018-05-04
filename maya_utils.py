from maya.api import OpenMaya
from maya import cmds

def get_dag_path_object(output_geometry):
    selection_list = OpenMaya.MGlobal.getSelectionListByName(output_geometry)
    dag_path = selection_list.getDagPath(0)
    return dag_path

def get_components(output_geometry):
    selection_list = OpenMaya.MGlobal.getSelectionListByName(output_geometry)
    components = selection_list.getComponent(0)
    return components

def get_input_geometry(skin_cluster_object):
    geometry_array = skin_cluster_object.getInputGeometry()
    dag_node = OpenMaya.MFnDagNode(geometry_array[0])
    return dag_node.fullPathName()

def get_output_geometry(skin_cluster_object):
    geometry_array = skin_cluster_object.getOutputGeometry()
    dag_node = OpenMaya.MFnDagNode(geometry_array[0])
    return dag_node.fullPathName()
