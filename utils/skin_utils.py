# Copyright 1998-2019 Epic Games, Inc. All Rights Reserved.

# built-in
import logging

# third-party
from scipy import spatial
from maya.api import OpenMaya, OpenMayaAnim
from maya import cmds

logger = logging.getLogger(__name__)


def get_skin_cluster_from_mesh(mesh):
    """
    Grabs the skinCluster from given mesh.

    :param str mesh: Name of mesh to find skinCluster on.
    :return: Returns the name of the skinCluster if one is found.
    :rtype: str
    """
    history = cmds.listHistory(mesh, pruneDagObjects=True)
    skin_cluster = cmds.ls(history, type="skinCluster")
    if not skin_cluster:
        return
    return skin_cluster[0]


def get_skin_cluster_object(skin_cluster_name):
    """
    Grabs the OpenMaya2 MFnSkinCluster object from given skinCluster name.

    :param str skin_cluster_name: Name of skinCluster.
    :return: Returns the skinCluster object.
    :rtype: MFnSkinCluster
    """
    selection_list = OpenMaya.MGlobal.getSelectionListByName(skin_cluster_name)
    mobject = selection_list.getDependNode(0)
    return OpenMayaAnim.MFnSkinCluster(mobject)


def get_geometry_filter_object(skin_cluster_name):
    """
    Grabs the OpenMaya2 MFnGeometryFilter object from given skinCluster name.

    :param str skin_cluster_name: Name of skinCluster.
    :return: Returns the geometry filter object.
    :rtype: MFnGeometryFilter
    """
    selection_list = OpenMaya.MGlobal.getSelectionListByName(skin_cluster_name)
    mobject = selection_list.getDependNode(0)
    return OpenMayaAnim.MFnGeometryFilter(mobject)


def get_vertex_component():
    """
    Grab's Maya's API's vertex component for using the getWeights and setWeights
    commands. It's a dependency for OpenMaya.

    :return: Returns the kMeshVertComponent
    :rtype: kMeshVertComponent
    """
    single_index_component = OpenMaya.MFnSingleIndexedComponent()
    return single_index_component.create(OpenMaya.MFn.kMeshVertComponent)


def get_dag_path_object(node):
    """
    Grabs the dag path object from the output geometry node.

    :param str node: Name of the node.
    :return: Returns the dagPath object.
    :rtype: MDagPath
    """
    selection_list = OpenMaya.MGlobal.getSelectionListByName(node)
    return selection_list.getDagPath(0)


def get_kdtree_from_points(points):
    """
    Returns a KDTree from the point list passed in.

    :param list points: The list of points to build the KDTree from.
    :return: Returns a KDTree.
    :rtype: cKDTree
    """
    points = [[p.x, p.y, p.z] for p in points]
    return spatial.cKDTree(points)


def get_closest_point_in_kdtree(kdtree, mvector):
    """
    Gets closest point to the passed in mvector in the KDTree.

    :param cKDTree kdtree: KDTree to find closest point in.
    :param MVector mvector: The MVector point to find the closest point for.
    :return: Returns the closest point found in the KDTree.
    :rtype: tuple
    """
    positions = [mvector.x, mvector.y, mvector.z]
    out = kdtree.query(positions)

    # Return is a tuple containing the vertex id, MVector position, and distance.
    return out[1], OpenMaya.MVector(kdtree.data[out[1]].tolist()), out[0]


def convert_points_to_mvectors(points):
    """
    Converts a list of points to MVectors.

    :param list points: The list of points to convert to MVectors.
    :return: Returns a list of MVectors
    :rtype: list(MVector)
    """
    return [OpenMaya.MVector(point) for point in points]


def create_skin_cluster(mesh, influences, normalize_method=1):
    """
    Creates a skinCluster on the given mesh with the given influences.

    :param str mesh: Name of mesh to create skinCluster on.
    :param list influences: The list of influences to build skinCluster with.
    :param int normalize_method: Determines the normalization method. Maya's
    documentation is wrong, the setting is 0, 1 and 2. The docs say 0, 2 and 3.
        0 = none
        1 = interactive (default)
        2 = post
    """
    cmds.skinCluster(
        influences,
        mesh,
        toSelectedBones=True,
        normalizeWeights=normalize_method,
        name="{mesh}_skinCluster".format(mesh=mesh.split("|")[-1])
    )


def find_between(value, first, last):
    """
    Convenience method for finding the value between two characters in a
    string.

    :param str value: The full string value.
    :param str first: The first character before what you want to find.
    :param str last: The last character after what you want to find.
    :return: Returns the characters between the first and last values.
    :rtype: str
    """
    if first in value and last in value:
        start = value.rindex(first) + len(first)
        end = value.rindex(last, start)
        return value[start:end]


def get_missing_influences_in_scene(influences):
    """
    Gets the influences that are not in the scene.

    :param list influences: The influences to compare with.
    :return: Returns a list of the missing influences.
    :rtype: list
    """
    scene_joints = cmds.ls(type="joint", long=True)
    return list(set(influences) - set(scene_joints))


def get_selected_meshes():
    """
    This method grabs the currently selected meshes.

    :return: Returns a list of valid meshes.
    :rtype: list
    """
    meshes = cmds.ls(selection=True, dag=True, type="mesh")
    if not meshes:
        logger.warning("No meshes are selected!")
        return []
    return list(set(cmds.listRelatives(meshes, parent=True, fullPath=True)))


def get_selected_verts():
    """
    Convenience method for grabbing the current vert selection. This method
    also ensures that the selected vert info isn't trunked using python
    indexing. i.e., .vtx[5:10].

    :return: Returns the selected verts.
    selected on it.
    :rtype: tuple(list(str), list(int))
    """
    # Ensures verts aren't chunked into indexes.
    selected_verts = cmds.filterExpand(selectionMask=31)
    if not selected_verts:
        logger.warning("No verts are selected!")
    return [int(find_between(vert, "[", "]")) for vert in selected_verts]


def get_skin_selection():
    """
    Convenience method for grabbing the current vert selection. This method
    also ensures that the selected vert info isn't trunked using python
    indexing. i.e., .vtx[5:10].

    :return: Returns the selected verts.
    selected on it.
    :rtype: tuple(list(str), list(int))
    """
    selected_verts = cmds.filterExpand(selectionMask=31)
    if selected_verts:
        meshes = [selected_verts[0].split(".vtx")[0]]  # Grabs the mesh name.
        selected_verts = [
            int(find_between(vert, "[", "]")) for vert in selected_verts
        ]
    else:
        meshes = get_selected_meshes()
    return meshes, selected_verts


def get_all_blind_data_ids():
    """
    Convenience method for retrieving all current polyBlindData ID's.

    :return: Returns a list of all existing polyBlindData ID's.
    :rtype: str
    """
    return [
        cmds.getAttr(
            "{}.typeId".format(node)
        ) for node in cmds.ls(
            type="polyBlindData"
        )
    ]


def get_blind_data_node_from_id(blind_data_id):
    """
    Convenience method for getting the polyBlindData node associated with an ID.

    :param int blind_data_id: The ID used when creating the polyBlindData node.
    :return: Returns the name of the polyBlindData node.
    :rtype: str
    """
    blind_data_node = [
        node for node in cmds.ls(type="polyBlindData")
        if blind_data_id == int(cmds.getAttr("{}.typeId".format(node)))
    ]
    return blind_data_node[0] if blind_data_node else None


def get_mesh_from_blind_data_node(blind_data_node):
    """
    Convenience method for getting the mesh associated with a polyBlindData node.

    :param str blind_data_node: Name of polyBlindData node.
    :return: Returns the name of the mesh.
    :rtype: str
    """
    mesh = cmds.ls(find_all_outgoing([blind_data_node]), type="transform")
    return mesh[0] if mesh else None


def get_mesh_from_blind_data_id(blind_data_id):
    """
    Convenience method for getting the mesh from the ID of a blind data node.

    :param int blind_data_id: Blind data ID used to find the mesh.
    :return: Returns the name of the mesh.
    :rtype: str
    """
    blind_data_node = get_blind_data_node_from_id(blind_data_id)
    return get_mesh_from_blind_data_node(blind_data_node)


def find_all_outgoing(start_nodes, max_depth=None):
    """
    Recursively finds all unique outgoing dependents for the specified node.

    :param list start_nodes: List of nodes you want to find connections for.
    :param in max_depth: The depth to search.
    :return: Returns all connections associated based on the parameters given.
    """
    dependents = set()
    _find_all_connections(
        start_nodes, dependents, max_depth, 0, source=False, destination=True
    )
    return list(dependents)


def _find_all_connections(start_nodes, nodes, max_depth, depth, **kwargs):
    """
    Recursively finds all unique node dependents/dependencies for the specified
    node based on the arguments.

    :param list start_nodes: List of nodes to find connections for.
    :param set nodes: Dependency set.
    :param in depth: The depth to search.
    :param dict list_connections_kwargs: Additional list_connections_kwargs
    for listConnection options.
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
        _find_all_connections(
            non_visited, nodes, max_depth, depth + 1, **kwargs
        )

