from maya.api import OpenMaya, OpenMayaAnim
from maya import cmds

def create_skin_cluster_from_geometry(geometry, influences):
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

def get_skin_cluster_from_geometry(geometry):
    history = cmds.listHistory(geometry, pdo=True)
    skin_cluster = cmds.ls(history, type='skinCluster')
    if not len(skin_cluster):
        return
    return skin_cluster[0]

def get_skin_cluster_object(skin_cluster_name):
    selection_list = OpenMaya.MGlobal.getSelectionListByName(skin_cluster_name)
    mobject = selection_list.getDependNode(0)
    return OpenMayaAnim.MFnSkinCluster(mobject)

def get_geometry_filter_object(skin_cluster_name):
    selection_list = OpenMaya.MGlobal.getSelectionListByName(skin_cluster_name)
    mobject = selection_list.getDependNode(0)
    return OpenMayaAnim.MFnGeometryFilter(mobject)

