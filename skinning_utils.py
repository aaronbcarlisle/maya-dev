# third-party
from maya.api import OpenMaya, OpenMayaAnim
from maya import cmds


def create_skin_cluster_from_geometry(geometry, influences):
    """
    Creates a skin cluster from the given geometry and influences (joints).
    :param str geometry: Name of geometry to create skinCluster on.
    :param list influences: The list of influences to build skinCluster with.
    """
    unused_joints = []
    existing_joints = []
    scene_joints = set([joint for joint in cmds.ls(type="joint", l=True)])
    for joint in influences:
        if not joint in scene_joints:
            unused_joints.append(joint)
            continue
        existing_joints.append(joint)

    # TODO: Make a joint remapper.
    if unused_joints and not scene_joints:
        return

    # Create skinCluster using as many matching existing joints.
    cmds.skinCluster(existing_joints, geometry, tsb=True, nw=2, n=geometry + "_skinCluster")[0]


def remove_unused_influences(skin_cluster):
    """
    Removes unused skin influences on given skinCluster.
    :param str skin_cluster: skinCluster object.
    :return list influences_to_remove: Returns a list of the removed influences.
    """
    influences_to_remove = []
    weighted_influences = cmds.skinCluster(skin_cluster, q=True, wi=True)
    all_influences = cmds.skinCluster(skin_cluster, q=True, inf=True)
    for influence in all_influences:
        if influence not in weighted_influences:
            influences_to_remove.append(influence)
    for influence in influences_to_remove:
        cmds.skinCluster(skin_cluster, e=True, ri=influence)
    return influences_to_remove


def get_skin_cluster_from_geometry(geometry):
    """
    Grabs the skinCluster from given geometry.
    :param str geometry: Name of geometry to find skinCluster on.
    """
    history = cmds.listHistory(geometry, pdo=True)
    skin_cluster = cmds.ls(history, type='skinCluster')
    if not len(skin_cluster):
        return
    return skin_cluster[0]


def get_skin_cluster_object(skin_cluster_name):
    """
    Grabs the OpenMaya2 MFnSkinCluster object from given skinCluster name.
    :param str skin_cluster_name: Name of skinCluster.
    """
    selection_list = OpenMaya.MGlobal.getSelectionListByName(skin_cluster_name)
    mobject = selection_list.getDependNode(0)
    return OpenMayaAnim.MFnSkinCluster(mobject)


def get_geometry_filter_object(skin_cluster_name):
    """
    Grabs the OpenMaya2 MFnGeometryFilter object from given skinCluster name.
    :param str skin_cluster_name: Name of skinCluster.
    """
    selection_list = OpenMaya.MGlobal.getSelectionListByName(skin_cluster_name)
    mobject = selection_list.getDependNode(0)
    return OpenMayaAnim.MFnGeometryFilter(mobject)
