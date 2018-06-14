# built-in
from datetime import datetime

from maya.api import OpenMaya
from maya import cmds


def get_dag_path_object(output_geometry):
    """
    Grabs the dag path object from the output geometry node.
    :param str output_geometry: Name of the output geometry.
    :return:  Returns the dagPath object.
    """
    selection_list = OpenMaya.MGlobal.getSelectionListByName(output_geometry)
    dag_path = selection_list.getDagPath(0)
    return dag_path


def get_components(output_geometry):
    """
    Grabs the components of the output geometry.
    :param str output_geometry: Name of the output geometry.
    :return: Returns a list of components.
    """
    selection_list = OpenMaya.MGlobal.getSelectionListByName(output_geometry)
    components = selection_list.getComponent(0)
    return components


def get_input_geometry(skin_cluster_object):
    """
    Grabs the input geometry associated with a given MFnSkinCluster object.
    :param MFnSkinCluster skin_cluster_object: MFnSkinCluster object.
    :return: Returns the fullPath to the input geometry.
    """
    geometry_array = skin_cluster_object.getInputGeometry()
    dag_node = OpenMaya.MFnDagNode(geometry_array[0])
    return dag_node.fullPathName()


def get_output_geometry(skin_cluster_object):
    """
    Grabs the output geometry associated with a given MFnSkinCluster object.
    :param MFnSkinCluster skin_cluster_object: MFnSkinCluster object.
    :return: Returns the fullPath to the output geometry.
    """
    geometry_array = skin_cluster_object.getOutputGeometry()
    dag_node = OpenMaya.MFnDagNode(geometry_array[0])
    return dag_node.fullPathName()


def find_all_incoming(start_nodes, max_depth=None):
    """
    Recursively finds all unique incoming dependencies for the specified node.
    :param list start_nodes: List of nodes you want to find connections for.
    :param in max_depth: The depth to search.
    :return: Returns all connections associated based on the parameters given.
    """
    dependencies = set()
    _find_all_connections(start_nodes, dependencies, max_depth, 0, source=True, destination=False)
    return list(dependencies)


def find_all_outgoing(start_nodes, max_depth=None):
    """
    Recursively finds all unique outgoing dependents for the specified node.
    :param list start_nodes: List of nodes you want to find connections for.
    :param in max_depth: The depth to search.
    :return: Returns all connections associated based on the parameters given.
    """
    dependents = set()
    _find_all_connections(start_nodes, dependents, max_depth, 0, source=False, destination=True)
    return list(dependents)


def _find_all_connections(start_nodes, nodes, max_depth, depth, **kwargs):
    """
    Recursively finds all unique node dependents/dependencies for the specified node based on the arguments.
    :param list start_nodes: List of nodes you want to find connections for.
    :param set nodes: Dependency set.
    :param in depth: The depth to search.
    :param dict list_connections_kwargs: Additional list_connections_kwargs for listConnection options.
    """
    if max_depth and depth > max_depth:
        return
    connections = cmds.listConnections(list(start_nodes), **kwargs)
    if not connections:
        return
    # l = long, but long is a built in data type so defaulting to l.
    non_visited = set(cmds.ls(connections, l=True)).difference(nodes)
    nodes.update(non_visited)
    if non_visited:
        _find_all_connections(non_visited, nodes, max_depth, depth + 1, **kwargs)


def get_geometry_from_blind_data_node(blind_data_node):
    """
    Convenience method for getting the geometry associated with a polyBlindData node.
    :param str blind_data_node: Name of polyBlindData node.
    :return: Returns the name of the geometry or None.
    """
    geometry = cmds.ls(find_all_outgoing([blind_data_node]), type="transform")
    return geometry[0] if geometry else None


def get_blind_data_node_from_id(blind_data_id):
    """
    Convenience method for getting the polyBlindData node associated with an ID.
    :param int/str blind_data_id: The ID used when creating the polyBlindData node.
    :return: Returns the name of the polyBlindData node or None.
    """
    if not isinstance(blind_data_id, int):
        if blind_data_id.isdigit():
            blind_data_id = int(blind_data_id)
        else:
            format_args = [blind_data_id, type(blind_data_id)]
            message = "{} is not of the right type, expected int or string of int, got {}!".format(*format_args)
            return OpenMaya.MGlobal.displayWarning(message)
    blind_data_node = [node for node in cmds.ls(type="polyBlindData") \
                       if blind_data_id == int(cmds.getAttr("{}.typeId".format(node)))]
    return blind_data_node[0] if blind_data_node else None


def is_blind_data_match(geometry, blind_data_id):
    """
    Convenience method for testing whether a blind data ID is associated with a piece of geometry.
    :param str geometry: Name of geometry to test against.
    :param int blind_data_id: ID to check.
    :return: True if match, False if not.
    """
    # If the ID is default, return True.
    current_year = datetime.now().year
    if blind_data_id == current_year:
        return True

    # Otherwise, check if it's a match.
    blind_data_node = get_blind_data_node_from_id(blind_data_id)
    if blind_data_node:
        associating_geometry = get_geometry_from_blind_data_node(blind_data_node)
        if associating_geometry == geometry:
            return True
    return False


def get_all_blind_data_ids():
    """
    Convenience method for retrieving all current polyBlindData ID's.
    :return: Returns a list of all existing polyBlindData ID's in the current scene.
    """
    return [cmds.getAttr("{}.typeId".format(node)) for node in cmds.ls(type="polyBlindData")]
