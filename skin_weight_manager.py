#------------------------------------------------------------------------------#
#-------------------------------------------------------------------- HEADER --#

"""
:author:
    acarlisle
:description:
    A fast and efficient skinWeight manager using the Python Maya API.

:how import and export weights:
    from epic.rigging import skin_weight_manager

    # export weights
    path = "path/to/export/{0}.json"
    selection = cmds.ls(sl=True)
    if selection:
        for selected_geo in selection:
            path = path.format(selected_geo)
            skin_weight_manager.export_skin_weights(path)

    # import weights
    path = "path/to/export/{0}.json"
    selection = cmds.ls(sl=True)
    removed_unused = None # or True
    if selection:
        for selected_geo in selection:
            path = path.format(selected_geo)
            skin_weight_manager.import_skin_weights(path,
                                   remove_unused=remove_unused)

:how bake and unbake weights:
    from epic.rigging import skin_weight_manager

    # make a selection and run
    skin_weight_manager.vertex_blind_data("bake")
    skin_weight_manager.vertex_blind_data("unbake")

:API reference:
    http://help.autodesk.com/view/MAYAUL/2016/ENU/?guid=__py_ref_index_html

"""

#------------------------------------------------------------------------------#
#------------------------------------------------------------------- IMPORTS --#

# built-in
import os
import re

# third-party
from maya import cmds
from maya import OpenMaya, OpenMayaAnim

# external
from epic.utils.string_utils import remove_namespace
from epic.utils.maya_utils import find_skin_clusters, get_mobject
from epic.utils.maya_utils import remove_unused_influences, get_selected_geometry
from epic.utils.system_utils import json_save, json_load, win_path_convert

#------------------------------------------------------------------------------#
#------------------------------------------------------------------- GLOBALS --#

# blind data ID
BLIND_DATA_ID = 201607

ATTRIBUTES = ['skinningMethod', 'normalizeWeights', 'dropoffRate',
              'maintainMaxInfluences', 'maxInfluences','bindMethod',
              'useComponents', 'normalizeWeights', 'weightDistribution',
              'heatmapFalloff']

#------------------------------------------------------------------------------#
#----------------------------------------------------------------- FUNCTIONS --#

def export_skin_weights(file_path=None, geometry=None):
    """
    PARAMS:
        file_path: str, path/to/save/location/mesh.json
        geometry: str, mesh object
    """
    data = []
    # error handling
    if not file_path:
        return OpenMaya.MGlobal_displayError("No file path given.")
    if not geometry:
        geometry = _geometry_check(geometry)
        if not geometry:
            return

    # build up skin data
    skin_clusters = find_skin_clusters(geometry)
    if not skin_clusters:
        skin_message = "No skin clusters found on {0}.".format(geometry)
        return OpenMaya.MGlobal_displayWarning(skin_message)
    for skin_cluster in skin_clusters:
        skin_data_init = SkinData(skin_cluster)
        skin_data = skin_data_init.gather_data()
        data.append(skin_data)
        args = [skin_data_init.skin_cluster, file_path]
        export_message = "SkinCluster: {0} has " \
                         "been exported to {1}.".format(*args)
        OpenMaya.MGlobal_displayInfo(export_message)

    # dump data
    file_path = win_path_convert(file_path)
    json_save(data, file_path)
    return file_path

def import_skin_weights(file_path=None, geometry=None, remove_unused=None, selected_verts=None):
    """
    PARAMS:
        file_path: str, path/to/import/location/mesh.json
        geometry: str, mesh object
        remove_unused: prunes joints that have 0 influences on mesh.
    """
    # load data
    if not file_path:
        return OpenMaya.MGlobal_displayError("No file path given.")
    if not os.path.exists(file_path):
        path_message = "Could not find {0} file.".format(file_path)
        return OpenMaya.MGlobal_displayWarning(path_message)
    data = json_load(file_path)

    # geometry handling
    if not geometry:
        geometry = _geometry_check(geometry)
        if not geometry:
            return
    else:
        data[0]["shape"] = geometry

    # selected vert check
    if selected_verts:
        selected = cmds.ls(sl=True)
        selected_verts_strings = cmds.filterExpand(sm=31)
        if not selected_verts_strings:
            vert_message = "No verts were selected, please select some verts, thanks."
            return OpenMaya.MGlobal_displayWarning(vert_message)

        selected_vert_indexes = _parse_for_indexes(selected_verts_strings)
        data[0]["selected_vert_indexes"] = selected_vert_indexes

    # check verts
    if not cmds.objExists(geometry[0]):
        geometry = remove_namespace(geometry)
    vert_check = _vert_check(data, geometry)
    if not vert_check:
        return

    # import skin weights
    _import_skin_weights(data, geometry, file_path, remove_unused)

def vertex_blind_data(bake_type, mesh_objects=None):
    """
    PARAMS:
        bake_type: str, "bake" or "unbake"
        mesh_objects: list, optional
    """
    # prep
    if not mesh_objects:
        mesh_objects = get_selected_geometry()
    if not isinstance(mesh_objects, list):
        mesh_objects = [mesh_objects]

    # error handling
    if not mesh_objects:
        message = "Please make a selection."
        return OpenMaya.MGlobal_displayWarning(message)

    # loop through mesh obects and bake/unbake
    for mesh in mesh_objects:
        # skip if no skin cluster found
        if not find_skin_clusters(mesh) and bake_type == "bake":
            message = "Skipping {0}, no skinCluster found.".format(mesh)
            OpenMaya.MGlobal_displayWarning(message)
            continue

        # grab selection for dag path
        cmds.select(mesh)
        selection = OpenMaya.MSelectionList()
        OpenMaya.MGlobal.getActiveSelectionList(selection)
        if bake_type == "bake":
            _bake_vertex_blind_data(mesh)
        elif bake_type == "unbake":
            _unbake_vertex_blind_data(mesh, selection)

#------------------------------------------------------------------------------#
#------------------------------------------------------------------ PRIVATES --#

def _import_skin_weights(data, geometry, file_path, remove_unused=None):

    # loop through skin data
    for skin_data in data:
        if not geometry:
            geometry = skin_data["shape"]
        if not cmds.objExists(geometry[0]):
            if not cmds.objExists(geometry):
                message = "Could not find {0} in scene.".format(geometry)
                OpenMaya.MGlobal_displayWarning(message)
                continue

        # get clusters and set data
        skin_cluster = find_skin_clusters(geometry)
        if skin_cluster:
            skin_cluster = skin_cluster[0]
            skin_cluster_obj, missing_influences = _parallel_skin_clusters(skin_cluster, skin_data)
            if not missing_influences:
                skin_cluster_obj.set_data(skin_data)
                continue
            cmds.delete(skin_cluster)
            message = "Removing skinCluster because of missing influences."
            OpenMaya.MGlobal_displayWarning(message)

        # TODO: make joint remapper, Chris has a setup for this already
        skin_cluster = _create_new_skin_cluster(skin_data, geometry)
        if not skin_cluster:
            continue
        skin_cluster[0].set_data(skin_data)
        if remove_unused:
            remove_unused_influences(skin_cluster[1])
        OpenMaya.MGlobal_displayInfo("Imported {0} onto {1}.".format(file_path, geometry))

def _parallel_skin_clusters(skin_cluster, skin_data):
    # get current influences
    skin_cluster_obj = SkinData(skin_cluster)
    current_data = skin_cluster_obj.gather_data()
    current_influences = current_data["weights"].keys()

    # unclock weights
    for influence in current_influences:
        cmds.setAttr('%s.liw' % influence, 0)
    new_influences = skin_data["weights"].keys()

    # TODO: add any misssing influences
    missing_influences = []
    for influence in new_influences:
        if influence not in current_influences:
            missing_influences.append(influence)
            # cmds.skinCluster(skin_cluster, e=True, ai=influence)
    return skin_cluster_obj, missing_influences

def _unbake_vertex_blind_data(mesh, selection):
    # get dag path
    dag_path = OpenMaya.MDagPath()
    selection.getDagPath(0, dag_path)
    dag_path.extendToShape()

    # get MFnMesh
    fn_mesh = OpenMaya.MFnMesh(dag_path)

    # get baked data
    empty_array = OpenMaya.MIntArray()
    empty_data = []
    fn_mesh.getStringBlindData(OpenMaya.MFn.kMeshVertComponent, BLIND_DATA_ID,
                               "weightsInfo", empty_array, empty_data)

    # get influences for skin cluster (we need the exact joints)
    influences = []
    for data in empty_data:
        joints = [x.split(":")[0] for x in data.split("|")]
        influences.extend(joints)
    influences = filter(None, list(set(influences)))

    # create skinCluster
    shape = dag_path.fullPathName()

    # check for clusters, if so delete
    clusters = find_skin_clusters(cmds.listRelatives(shape, p=True))
    if clusters:
        cmds.delete(clusters)

    # create new skinCluster
    skin_cluster = cmds.skinCluster(influences, shape, tsb=True, omi=0, nw=1)

    # grab new skinCluster joint id's
    influences_ids = {}
    influence_dags = OpenMaya.MDagPathArray()
    skin_data = SkinData(skin_cluster[0]) # probably a bit much
    skin_data.skin_set.influenceObjects(influence_dags)
    influence_length = influence_dags.length()
    for inf_id in xrange(influence_length):
        influence_path = influence_dags[inf_id].fullPathName().split("|")[-1]
        influences_ids[influence_path] = inf_id

    # unlock influences used by skincluster
    for inf in influences:
        cmds.setAttr('%s.liw' % inf, 0)

    # normalize needs turned off for pruning
    cmds.setAttr('%s.normalizeWeights' % skin_cluster[0], 0)

    # prune weights
    cmds.skinPercent(skin_cluster[0], shape, nrm=False, prw=100)

    # get weights
    dag_path, mobject = skin_data.get_skin_dag_path_and_mobject()
    weights = skin_data.get_weights(dag_path, mobject)
    influence_id_pattern = []
    for x in xrange(empty_array.length()):
        # vert id's
        vert_id = empty_array[x]

        # get weight value
        full_list = fn_mesh.stringBlindDataComponentId(vert_id,
                        OpenMaya.MFn.kMeshVertComponent, BLIND_DATA_ID, "weightsInfo")
        sets = filter(None, full_list.split("|"))
        for b in sets:
            joint = b.split(":")[0]
            joint_id = influences_ids.get(joint)
            weight = float(b.split(":")[1])

            # set weight value
            weight_matrix_pos = (vert_id * influence_length) + joint_id
            weights.set(weight, weight_matrix_pos)

            # store joint id order
            if joint_id not in influence_id_pattern:
                influence_id_pattern.append(joint_id)

    # set influence array correctly
    influence_array = OpenMaya.MIntArray(len(influence_id_pattern))
    for influence in influence_id_pattern:
        influence_array.set(influence, influence)

    # set weights
    skin_data.skin_set.setWeights(dag_path, mobject, influence_array, weights, False)

    # reset normalization
    cmds.setAttr('%s.normalizeWeights' % skin_cluster[0], 1)

    success = "Successfully unbaked {0} verts on "\
              "mesh: {1}".format(empty_array.length(), mesh)
    return OpenMaya.MGlobal_displayInfo(success)

def _bake_vertex_blind_data(mesh):
    # skin data
    skin_cluster = find_skin_clusters(mesh)[0]
    skin_data = SkinData(skin_cluster)

    # dag path and mobject
    dag_path, mobject = skin_data.get_skin_dag_path_and_mobject()

    # mfnmesh
    fn_mesh = OpenMaya.MFnMesh(dag_path)

    # set influence obejcts
    bones_dag_path = OpenMaya.MDagPathArray()
    num_bones = skin_data.skin_set.influenceObjects(bones_dag_path)

    # get influence ids
    inf_ids = []
    for x in xrange(bones_dag_path.length()):
        inf_id = skin_data.skin_set.indexForInfluenceObject(bones_dag_path[x])
        inf_ids.append(inf_id)

    # get vert count
    vertexes = OpenMaya.MItMeshVertex(dag_path, mobject)
    vertex_indexes = [x for x in xrange(0, vertexes.count())]

    # mint array for setStringBlindData
    vertex_mint_array = OpenMaya.MIntArray()
    for count in xrange(len(vertex_indexes)):
        vertex_mint_array.append(count)

    # set joint and vertex id's
    db_values = []
    for i in xrange(vertexes.count()):

        # plug setup
        plug_weight_list = skin_data.skin_set.findPlug("weightList")
        weight_list_attr = plug_weight_list.attribute()
        plug_weights = skin_data.skin_set.findPlug("weights")
        weights_attr = plug_weights.attribute()

        # vertex id's
        vertex_id = vertex_indexes[i]
        plug_weights.selectAncestorLogicalIndex(vertex_id, weight_list_attr)

        # joint id's
        joint_ids = OpenMaya.MIntArray()
        plug_weights.getExistingArrayAttributeIndices(joint_ids)

        # set weight id values and save out weight string
        weight_string = ""
        influence_plug = plug_weights
        for j in xrange(joint_ids.length()):
            inf_joint_id = joint_ids[j]
            influence_plug.selectAncestorLogicalIndex(inf_joint_id, weights_attr)
            weight = influence_plug.asFloat()
            bone_name = bones_dag_path[inf_ids.index(inf_joint_id)].partialPathName()

            # string name
            weight_string += bone_name + ":" + str(weight) + "|"

        # append for set command
        db_values.append(weight_string)

    # create blind data tuples (mstring arrays)
    blind_data_ln = ("weightsInfo", "weightsInfo", "weightsInfo")
    blind_data_sn = ("wi", "wi", "wi")
    blind_data_fn = ("string", "string", "string")
    if not cmds.blindDataType(q=True, id=BLIND_DATA_ID):
        fn_mesh.createBlindDataType(BLIND_DATA_ID, blind_data_ln,
                                    blind_data_sn, blind_data_fn)

    # save string data
    fn_mesh.setStringBlindData(vertex_mint_array, OpenMaya.MFn.kMeshVertComponent,
                               BLIND_DATA_ID, "weightsInfo", db_values)

    success = "Successfully baked {0} verts on "\
              "mesh: {1}".format(vertexes.count(), mesh)
    return OpenMaya.MGlobal_displayInfo(success)

def _vert_check(data, geometry):
    # check vertex count
    for skin_data in data:
        if not geometry:
            geometry = skin_data["shape"]
        vert_count = cmds.polyEvaluate(geometry, vertex=True)
        import_vert_count = len(skin_data["blendWeights"])
        if vert_count != import_vert_count:
            geo = geometry
            vert_message = "The vert count does not match for {0}.".format(geo)
            return OpenMaya.MGlobal_displayError(vert_message)
    return True

def _create_new_skin_cluster(skin_data, geometry):
    # check joints
    joints = skin_data["weights"].keys()
    unused_joints = []
    existing_joints = []
    scene_joints = set([remove_namespace(joint) for joint \
                        in cmds.ls(type="joint")])
    for joint in joints:
        if not joint in scene_joints:
            unused_joints.append(joint)
            continue
        existing_joints.append(joint)

    # TODO: make joint remapper
    if unused_joints and not scene_joints:
        return

    skin_cluster = cmds.skinCluster(existing_joints, geometry, tsb=True, nw=2,
                                    n=skin_data["skinCluster"])[0]
    return SkinData(skin_cluster), skin_cluster

def _geometry_check(geometry):
    if not geometry:
        geometry = cmds.ls(sl=True)
    if cmds.nodeType(geometry) != "transform" or not geometry:
        geo_message = "Please select a piece/s of geometry."
        return OpenMaya.MGlobal_displayError(geo_message)
    return geometry

def _parse_for_indexes(vert_strings):
    """Parses and returns the index value from vert attribute string values."""
    vert_indexes = []
    for vert_string in vert_strings:
        vert_string = vert_string.split(".")[-1]
        index = int(re.search(r'\d+', vert_string).group())
        vert_indexes.append(index)
    return vert_indexes

#------------------------------------------------------------------------------#
#------------------------------------------------------------------- CLASSES --#


class SkinData(object):
    def __init__(self, skin_cluster):

        # globals/data
        self.skin_cluster = skin_cluster
        deformer = cmds.deformer(skin_cluster, q=True, g=True)[0]
        self.shape = cmds.listRelatives(deformer, parent = True, path=True)[0]
        self.mobject = get_mobject(self.skin_cluster)
        self.skin_set = OpenMayaAnim.MFnSkinCluster(self.mobject)
        self.influence_array = self.get_influence_array()
        self.data = {
            "weights" : {},
            "blendWeights" : [],
            "skinCluster" : self.skin_cluster,
            "shape" : self.shape,
            "selected_vert_indexes" : [],
            }

    def gather_data(self):

        # get incluence and blend weight data
        dag_path, mobject = self.get_skin_dag_path_and_mobject()
        self.get_influence_weights(dag_path, mobject)
        self.get_blend_weights(dag_path, mobject)

        # add in attribute data
        for attribute in ATTRIBUTES:
            self.data[attribute] = cmds.getAttr("{0}.{1}". \
                                        format(self.skin_cluster,
                                               attribute))
        return self.data

    def get_skin_dag_path_and_mobject(self):
        function_set = OpenMaya.MFnSet(self.skin_set.deformerSet())
        selection_list = OpenMaya.MSelectionList()
        function_set.getMembers(selection_list, False)
        dag_path = OpenMaya.MDagPath()
        mobject = OpenMaya.MObject()
        selection_list.getDagPath(0, dag_path, mobject)
        return dag_path, mobject

    def get_influence_weights(self, dag_path, mobject):
        weights = self.get_weights(dag_path, mobject)

        influence_paths = OpenMaya.MDagPathArray()
        influence_count = self.skin_set.influenceObjects(influence_paths)
        components_per_influence = weights.length() / influence_count
        for count in xrange(influence_paths.length()):
            name = influence_paths[count].partialPathName()
            name = remove_namespace(name)
            weight_data = [weights[influence*influence_count+count] \
                           for influence in xrange(components_per_influence)]
            self.data["weights"][name] = weight_data

    def get_weights(self, dag_path, mobject):
        """Where the API magic happens."""
        weights = OpenMaya.MDoubleArray()
        util = OpenMaya.MScriptUtil()
        util.createFromInt(0)
        pointer = util.asUintPtr()

        # magic call
        self.skin_set.getWeights(dag_path, mobject, weights, pointer);
        return weights

    def get_blend_weights(self, dag_path, mobject):
        return self._get_blend_weights(dag_path, mobject)

    def _get_blend_weights(self, dag_path, mobject):
        weights = OpenMaya.MDoubleArray()

        # magic call
        self.skin_set.getBlendWeights(dag_path, mobject, weights)
        blend_data = [weights[blend_weight] for \
                      blend_weight in xrange(weights.length())]
        self.data["blendWeights"] = blend_data

    def get_influence_array(self):
        influence_paths = OpenMaya.MDagPathArray()
        influence_count = self.skin_set.influenceObjects(influence_paths)
        influence_array = OpenMaya.MIntArray(influence_count)
        for count in xrange(influence_count):
            influence_array.set(count, count)
        return influence_array

    def set_data(self, data):
        """Final point for importing weights. Sets and applies influences
        and blend weight values.
        @PARAMS:
            data: dict()
        """
        self.data = data
        dag_path, mobject = self.get_skin_dag_path_and_mobject()
        self.set_influence_weights(dag_path, mobject)
        self.set_blend_weights(dag_path, mobject)

        # set skinCluster Attributes
        for attribute in ATTRIBUTES:
            cmds.setAttr('{0}.{1}'.format(self.skin_cluster, attribute),
                         self.data[attribute])

    def set_influence_weights(self, dag_path, mobject):
        weights = self.get_weights(dag_path, mobject)
        influence_paths = OpenMaya.MDagPathArray()
        influence_count = self.skin_set.influenceObjects(influence_paths)
        components_per_influence = weights.length() / influence_count

        # influences
        unused_influences = []
        influences = [influence_paths[inf_count].partialPathName() for \
                      inf_count in xrange(influence_paths.length())]

        # unlocks influences
        for inf in influences:
            cmds.setAttr('%s.liw' % inf, 0)

        # selected verts
        selected_vert_indexes = self.data["selected_vert_indexes"]

        # build influences/weights
        for imported_influence, imported_weights in self.data["weights"].items():
            for inf_count in xrange(influence_paths.length()):
                influence_name = influence_paths[inf_count].partialPathName()
                influence_name = remove_namespace(influence_name)
                if influence_name == imported_influence:
                    for count in xrange(len(imported_weights)):

                        # handle selected vert option
                        if selected_vert_indexes:
                            if count in selected_vert_indexes:
                                weights.set(imported_weights[count],
                                            count * influence_count + inf_count)
                            continue

                        # handle normal importing
                        weights.set(imported_weights[count],
                                    count * influence_count + inf_count)
                    if influence_name in influences:
                        influences.remove(influence_name)
                    break
            else:
                unused_influences.append(imported_influence)

        # TODO: make joint remapper
        if unused_influences and influences:
            OpenMaya.MGlobal_displayWarning("Make a joint remapper, Aaron!")

        # set influences
        influence_array = OpenMaya.MIntArray(influence_count)
        for count in xrange(influence_count):
            influence_array.set(count, count)

        # set weights
        self.skin_set.setWeights(dag_path, mobject, influence_array, weights, False)

    def set_blend_weights(self, dag_path, mobject):
        blend_weights = OpenMaya.MDoubleArray(len(self.data['blendWeights']))
        for influence, weight in enumerate(self.data['blendWeights']):
            blend_weights.set(weight, influence)
        self.skin_set.setBlendWeights(dag_path, mobject, blend_weights)
