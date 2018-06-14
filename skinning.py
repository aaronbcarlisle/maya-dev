# built-in
import os
import json
import time
from datetime import datetime

# third-party
from maya.api import OpenMaya
from maya import cmds
import KDTree

from colossus.Utils.DCC.maya import skinning_utils
from colossus.Utils.DCC.maya import maya_utils

DEFAULT_BLIND_DATA_ID = datetime.now().year


def export_weights(geometry, path):
    """
    Serializes out weighting information of given geometry to path specified using json.
    :param str geometry: Name of geometry.
    :param str path: Path to save weight file.
    """
    skin_cluster_name = skinning_utils.get_skin_cluster_from_geometry(geometry)
    if not skin_cluster_name:
        return OpenMaya.MGlobal.displayWarning("No skinCluster found on {}!".format(geometry))

    # Get the skin weights.
    skin_handler = SkinHandler(skin_cluster_name)
    skin_handler.store_weights()

    # Serialize out the weighting information to disk.
    with open(path, 'w') as weight_file:
        weight_file.write(json.dumps(skin_handler.data, sort_keys=True, indent=4))
    OpenMaya.MGlobal.displayInfo("Successfully saved weight data for {} to {}.".format(geometry, path))


def import_weights(geometry, path, method=None, remove_unused_influences=None, vert_indexes=None):
    """
    Imports weight information from given weight file (path) onto given geometry mesh.
    :param str geometry: Name of geometry.
    :param str path: Path to weight file.
    :param str method: Options are (None, positions, normals). None is point order.
    :param bool remove_unused_influences: Boolean for removing unused influences or not.
    :param list vert_indexes: Optional, specify which verts you want weights to be loaded on.
    """
    # Ensure that the file exists on disk.
    if not os.path.isfile(path):
        return OpenMaya.MGlobal.displayWarning("{} does not exist on disk!".format(path))

    # Ensure geometry has a shape node.
    shapes = cmds.listRelatives(geometry, shapes=True)
    if not shapes:
        return OpenMaya.MGlobal.displayWarning("{} is not geometry!".format(geometry))

    # Load the skin weight data.
    data = None
    with open(path) as weight_file:
        data = json.loads(weight_file.read())

    # If the vert count does not exist, default to closest point.
    imported_vert_count = len(data['verts'])
    if not method and imported_vert_count != cmds.polyEvaluate(geometry, v=True):
        warning = "Vert order does not match for {}, defaulting to closest point (positions)!".format(geometry)
        OpenMaya.MGlobal.displayWarning(warning)
        method = "positions"

    # Create skinCluster if one does not already exist.
    skin_cluster_name = skinning_utils.get_skin_cluster_from_geometry(geometry)
    if not skin_cluster_name:
        if vert_indexes:
            warning = "Aborting weight import on specified verts, no skinCluster found!"
            return OpenMaya.MGlobal.displayWarning(warning)
        skinning_utils.create_skin_cluster_from_geometry(geometry, data['influences'])
        skin_cluster_name = skinning_utils.get_skin_cluster_from_geometry(geometry)

    # Set the skin weights.
    skin_handler = SkinHandler(skin_cluster_name)
    kwargs = {"method": method, "remove_unused_influences": remove_unused_influences, "vert_indexes": vert_indexes}
    skin_handler.set_weights(data, **kwargs)
    OpenMaya.MGlobal.displayInfo("Successfully loaded weight data from {} on to {}.".format(path, geometry))


def bake_weights(geometry, create_snapshot=None, delete_skin_cluster=None):
    """
    Baking weights allows you to save vertex weight information using blindData on the given geometry mesh.
    This allows manipulation of the geometry (deleting history, removing/changing topology) without losing
    weight information.
    .. NOTE:: BlindData is saved on the geometry, so nothing gets serialized out of the scene.
    :param str geometry: Name of geometry.
    :param bool create_snapshot: Options are (None/False, True). Creating a snapshot creates a new blindData ID which
    allows us to save different states of weighting information on the geometry mesh.
    :param bool delete_skin_cluster: If set to True, will delete skinCluster.
    """
    # Don't try to bake if there isn't a skinCluster.
    skin_cluster_name = skinning_utils.get_skin_cluster_from_geometry(geometry)
    if not skin_cluster_name:
        return OpenMaya.MGlobal.displayWarning("No skinCluster found on {}!".format(geometry))

    # Build up the influence table.
    skin_handler = SkinHandler(skin_cluster_name)
    skin_handler.bake(create_snapshot)

    if delete_skin_cluster:
        cmds.delete(skin_cluster_name)
        OpenMaya.MGlobal.displayInfo("Deleted skinCluster {} from {}.".format(skin_cluster_name, geometry))


def unbake_weights(geometry, snapshot_id=None, normalize_method=2):
    """
    Unbaking weights takes the saved blindData on the geometry mesh and reaplies a skinCluster with the same weighting
    information.
    :param str geometry: Name of geometry.
    :param int snapshot_id: Options are (None, int). The blindData ID number to unbake the weights with. If None, it
    :param int normalize_method: Options are 0, 1 or 2. See cmds.skinCluster for reference.
    will use the default blindData ID (whatever ID was originally used to bake the mesh with).
    """
    # Ensure geometry has a shape node.
    shapes = cmds.listRelatives(geometry, shapes=True)
    if not shapes:
        return OpenMaya.MGlobal.displayWarning("{} is not geometry!".format(geometry))

    # Get the available snapshots in the scene and validate against the snapshot id.
    available_blind_data = [cmds.getAttr("{}.typeId".format(blind_data)) for blind_data in cmds.ls(type="polyBlindData")]
    if not snapshot_id:
        snapshot_id = DEFAULT_BLIND_DATA_ID
    if snapshot_id not in available_blind_data:
        OpenMaya.MGlobal.displayWarning("{} is not a valid snapshot ID!".format(snapshot_id))
        return OpenMaya.MGlobal.displayWarning("Available snapshots: {}".format(available_blind_data))

    # Build up the influence table.
    skin_handler = SkinHandler()
    skin_handler.unbake(geometry, snapshot_id=snapshot_id, normalize_method=normalize_method)


def get_unique_blind_data_id():
    """
    It's possible for objects to have the same ID if they're made at the same time. This method ensures the ID
    that is returned is unique.
    :return: Returns unique blind data ID.
    """
    blind_data_id = int(time.time())
    all_blind_data_ids = maya_utils.get_all_blind_data_ids()
    if blind_data_id in all_blind_data_ids:
        blind_data_id = max(all_blind_data_ids) + 1
    return blind_data_id


class SkinHandler(object):

    def __init__(self, skin_cluster_name=None):
        """
        Base class for SkinCluster manipulation.
        :param str skin_cluster_name: Name of the skinCluster.
        """
        # Setting the skin cluster name to None is only used for unbaking.
        if skin_cluster_name is None:
            return

        # Build skinCluster object.
        self.skin_cluster_name = skin_cluster_name
        self.skin_cluster_object = skinning_utils.get_skin_cluster_object(skin_cluster_name)
        self.geometry_filter_object = skinning_utils.get_geometry_filter_object(skin_cluster_name)

        # Manage influences.
        self.influence_objects = self.skin_cluster_object.influenceObjects()
        self.influences = [influence.fullPathName() for influence in self.influence_objects]
        self.number_of_influences = len(self.influence_objects)

        # Set influence indexes.
        self.influence_indexes = self._set_influence_indexes()

        # Gather input and output geometry information.
        self.input_geometry = maya_utils.get_input_geometry(self.skin_cluster_object)
        self.output_geometry = maya_utils.get_output_geometry(self.skin_cluster_object)
        self.geometry_dag_path = maya_utils.get_dag_path_object(self.output_geometry)

        # Vertex component for Maya API.
        single_index_component = OpenMaya.MFnSingleIndexedComponent()
        self.vertex_component = single_index_component.create(OpenMaya.MFn.kMeshVertComponent)

        # Get the MFnMesh object from the mesh.
        self.geometry_dag_path.extendToShape()
        self.mesh_object = OpenMaya.MFnMesh(self.geometry_dag_path)

        # Record the current number of verts for validation.
        self.number_of_verts = len(self.mesh_object.getPoints())

        # Initialize data.
        self.data = {'input_geometry': self.input_geometry,
                     'influences': self.number_of_influences * [None],
                     'influence_ids': [],
                     'verts': {}}

    def _set_influence_indexes(self):
        """
        Sets the influence indexes on the MIntArray related to the skinCluster.
        This is very Important!
        .. NOTE:: Setting the influences can be arbitrary as long as we load weights with the same indexes assigned.
        :return list influence_indexes: Returns the influence indexes.
        """
        influence_indexes = OpenMaya.MIntArray(len(self.influence_objects), 0)
        for influence_index in xrange(self.number_of_influences):
            influence_indexes[influence_index] = influence_index
        return influence_indexes

    def _set_influences(self):
        """This builds the influence array in the data dictionary."""
        for influence_index in xrange(self.number_of_influences):
            influence = self.influence_objects[influence_index]
            self.data['influences'][influence_index] = influence.fullPathName()

            # Ensure we store the influence ids for unbaking blindData.
            self.data['influence_ids'].append(influence_index)

    def get_weights(self):
        """
        This uses the OpenMaya2 API call (getWeights) for getting weights all in one go.
        :return object MIntArray:
        """
        args = [self.geometry_dag_path, self.vertex_component, self.influence_indexes]
        weights = self.skin_cluster_object.getWeights(*args)
        return weights if weights else []

    def store_weights(self):
        """Stores the weight information in the data handle."""
        ws_point_list = KDTree.get_ws_point_list(self.input_geometry)
        vertex_normal_point_list = KDTree.get_vertex_normal_point_list(self.geometry_dag_path)

        # Gather up the influences.
        self._set_influences()

        # Get the influence weights using the Maya API.
        influence_weights = self.get_weights()

        # build influence weight pairs
        skinning_info = {}
        for count, vertex in enumerate(xrange(0, len(influence_weights), self.number_of_influences), 0):
            skinning_info[count] = zip(self.influence_indexes, influence_weights[vertex:vertex + self.number_of_influences])

        # Save weight and position data for serialization.
        for vert_id in xrange(len(skinning_info)):
            position = [ws_point_list[vert_id].x, ws_point_list[vert_id].y, ws_point_list[vert_id].z]
            normal = [vertex_normal_point_list[vert_id].x, vertex_normal_point_list[vert_id].y, vertex_normal_point_list[vert_id].z]

            # Build up weight values to be stored, skipping 0.0 and NaN values.
            weights = []
            for pair in skinning_info[vert_id]:
                weight_value = pair[-1]
                if weight_value != 0.0 and str(weight_value) != "NaN":
                    weights.append(pair)

            # Build data dictionary.
            self.data['verts'][vert_id] = {'position': position,
                                           'normal': normal,
                                           'weights': weights}

        # Log out the results of the getting of weights.
        args = [len(self.data['verts']), self.geometry_dag_path]
        message = "Successfully stored weight data for {} verts for {}.".format(*args)
        OpenMaya.MGlobal.displayInfo(message)

    def set_weights(self, data=None, method=None, remove_unused_influences=None, vert_indexes=None):
        """
        Uses the OpenMaya2 API call (setWeights) to set weights on a mesh, all in one go.
        :param dict data: The dictionary containing the weight information to be applied.
        :param str method: Options are (None, positions, normals). None is point order.
        :param bool remove_unused_influences: Boolean for removing unused influences or not.
        :param list vert_indexes: Optional, specify which verts you want weights to be loaded on.
        """
        # Data is not required so that you can reset the original weighting of the mesh, if needed.
        if data:
            self.data = data

        # The default method is point order.
        points = self.data['verts']
        if not method and len(points) != self.number_of_verts:
            return OpenMaya.MGlobal.displayWarning("Vert order does not match!")

        # Gather up positional data and find closest points if method is positions.
        if method == "positions":
            ws_point_list = [self.data['verts'][str(vert_id)]['position'] for vert_id in xrange(len(points))]
            KDT = KDTree.KDTree_from_point_list(ws_point_list)
            target_points = KDTree.get_ws_point_list(self.input_geometry)
            points = [KDTree.get_closest_position_in_KDTree(KDT, p)[0] for p in target_points]

        # Gather up normal data and find closest points if method is normals.
        elif method == "normals":
            vertex_normal_point_list = [self.data['verts'][str(vert_id)]['normal'] for vert_id in xrange(len(points))]
            KDT = KDTree.KDTree_from_point_list(vertex_normal_point_list)
            target_points = KDTree.get_vertex_normal_point_list(self.geometry_dag_path)
            points = [KDTree.get_closest_position_in_KDTree(KDT, p)[0] for p in target_points]

        # If a invalid method is passed, log out invalid method and default to point order.
        elif method:
            OpenMaya.MGlobal.displayWarning("Method {} invalid, defaulting to point order!".format(method))
            method = None

        # Unlock influences used by the skinCluster.
        for influence in self.influences:
            cmds.setAttr('%s.liw' % influence, 0)

        # Get the MDoubleArray for the setWeights command.
        weight_array = self.get_weight_array(method, points, vert_indexes)

        # Use the Maya API setWeights command to set all in one go.
        set_weight_args = [self.geometry_dag_path, self.vertex_component, self.influence_indexes, weight_array, False]
        self.skin_cluster_object.setWeights(*set_weight_args)

        # Remove unused influences.
        if remove_unused_influences:
            removed_influences = skinning_utils.remove_unused_influences(self.skin_cluster_name)
            for influence in removed_influences:
                message = "Removed {} influence from {}".format(influence, self.skin_cluster_name)
                OpenMaya.MGlobal.displayInfo(message)

        # Log out the results of the setting of weights.
        if not method:
            method = "point order"

        # Only output the number of verts that were actually set.
        if vert_indexes:
            points = vert_indexes

        # Output.
        args = [method, len(points), len(self.data['verts']), self.geometry_dag_path]
        message = "Successfully set weights using the '{}' method on {} out of {} verts for {}.".format(*args)
        OpenMaya.MGlobal.displayInfo(message)

    def get_weight_array(self, method, points, vert_indexes):
        current_skin_arrays = []
        if vert_indexes:
            # Get the current weight set.
            current_weights = list(self.get_weights())

            # Build up existing skin arrays.
            stride = self.number_of_influences
            for _ in current_weights:
                current_skin_array, current_weights = current_weights[:stride], current_weights[stride:]
                current_skin_arrays.append(current_skin_array)

            # Convert vert indexes to closest point.
            if method == "positions":
                for vert_index in vert_indexes:
                    index = vert_indexes.index(vert_index)
                    vert_indexes[index] = points[vert_index]

        # Build up weight matrix.
        weights = []
        for vert_id in xrange(len(points)):

            # Set the initial state of the row in the weight matrix with default 0.0 values.
            vertex_skin_array = [0.0] * self.number_of_influences

            # If setting weights on specific weights, grab the current skin array set.
            if vert_indexes:
                old_skin_array = current_skin_arrays[vert_id]

            # If the method is positions, then look up the closest point from the KDT table.
            if method == "positions":
                vert_id = points[vert_id]

            vertex_skin_array = self._get_skin_array(str(vert_id), vertex_skin_array)

            # Assigns the vertex skin array to it'~ current values if importing specific vert weights.
            if vert_indexes and vert_id not in vert_indexes:
                vertex_skin_array = old_skin_array

            # Extend the weight array.
            weights.extend(vertex_skin_array)

        # Return MDoubleArray that will be passed into the setWeights command.
        return OpenMaya.MDoubleArray(weights)

    def _get_skin_array(self, vert_id, vertex_skin_array, method=None):
        """
        Builds up a skin array that will eventually be used as a MDoubleArray in the setWeights command.
        :param int vert_id: The vert you want to grab weight data from.
        :param list vertex_skin_array: List that will store the weight values.
        :param method: Options are: None or "string"
        :return: Returns a list of direct weight values or a string of weight values.
        """
        for influence_set in self.data['verts'][vert_id]['weights']:
            joint_index = influence_set[0]
            weight = influence_set[1]

            # If standard method, set the weight value directly.
            if not method:
                vertex_skin_array[int(joint_index)] = weight

            # If using blindData, store the data as a string with it's associating bone.
            elif method == "string":
                bone_name = self.influence_objects[self.influence_indexes[joint_index]].partialPathName()
                vertex_skin_array[joint_index] = bone_name + ":" + str(weight) + "|"

        return vertex_skin_array

    def bake(self, create_snapshot=None):
        """
        Baking weights allows you to save vertex weight information using blindData on a geometry mesh.
        This allows manipulation of the geometry (deleting history, removing/changing topology) without losing
        weight information.
        .. NOTE:: BlindData is saved on the geometry, so nothing gets serialized out of the scene.
        :param bool create_snapshot: Options are (None/False, True). Creating a snapshot creates a new blindData ID which
        allows us to save different states of weighting information on the geometry mesh.
        """
        # For snapshots, to capture the current time, down to the second as an integer format.
        blind_data_id = DEFAULT_BLIND_DATA_ID
        if create_snapshot:
            blind_data_id = get_unique_blind_data_id()

        # Build data.
        self.store_weights()

        # Set vertex mint Array.
        number_of_verts = len(self.data['verts'])
        vertex_array = OpenMaya.MIntArray()
        for count in xrange(number_of_verts):
            vertex_array.append(count)

        joint_ids = self.data['influence_ids']

        # Set the data to save onto the mesh.
        data_to_set = []
        for vert_id in xrange(len(self.data['verts'])):

            # Build up default weight string array.
            vertex_string_array = []
            for index in xrange(self.number_of_influences):
                influence_joint_id = joint_ids[index]
                bone_name = self.influence_objects[self.influence_indexes[influence_joint_id]].partialPathName()
                vertex_string_array.append("{}:0.0|".format(bone_name))

            vertex_string_array = self._get_skin_array(vert_id, vertex_string_array, method="string")

            # Make weight string array one long string for blindData bake.
            weight_string = ''.join(vertex_string_array)

            # Append for set command.
            data_to_set.append(weight_string)

        # Create blind data tuples (MString arrays).
        blind_data_tuple = (("weightsInfo", "wi", "string"),)*3
        if not cmds.blindDataType(q=True, id=blind_data_id):
            self.mesh_object.createBlindDataType(blind_data_id, blind_data_tuple)

        # Save string data to verts.
        self.mesh_object.setStringBlindData(vertex_array, OpenMaya.MFn.kMeshVertComponent,
                                            blind_data_id, "weightsInfo", data_to_set)

        # Log out the results of baking.
        args = [len(self.data['verts']), self.geometry_dag_path]
        message = "Successfully baked blind weight data from {} verts onto {}.".format(*args)
        OpenMaya.MGlobal.displayInfo(message)

    def unbake(self, geometry, snapshot_id=None, normalize_method=2):
        """
        Unbaking weights takes the saved blindData on the geometry mesh and reapplies a skinCluster with the same
        weighting information.
        :param str geometry: Name of geometry.
        :param int snapshot_id: The blindData ID number to unbake the weights with. If no arguments, it
        :param int normalize_method: Options are 0, 1 or 2. See cmds.skinCluster for reference.
        will use the default the blindData ID to the current year it was created. This will be what get's overridden on
        meshes not using a snapshot.
        """
        # Default the blind data id to whatever is passed in.
        blind_data_id = snapshot_id

        # Delete skinCluster if one already exists.
        skin_cluster = skinning_utils.get_skin_cluster_from_geometry(geometry)
        if skin_cluster:
            cmds.delete(skin_cluster)

        # Get the MFnMesh to query the blind data.
        geometry_dag_path = maya_utils.get_dag_path_object(geometry)
        geometry_dag_path.extendToShape()
        mesh_object = OpenMaya.MFnMesh(geometry_dag_path)

        # Get stringBlindData from the geometry
        points, string_data = mesh_object.getStringBlindData(OpenMaya.MFn.kMeshVertComponent, blind_data_id, "weightsInfo")

        # Get influences for new skinCluster (exact joints are needed).
        influences = []
        for data in string_data:
            joints = [x.split(":")[0] for x in data.split("|")]
            influences.extend(joints)
        influences = filter(None, list(set(influences)))

        # Create new skinCluster with the correct influences.
        skin_cluster_name = cmds.skinCluster(influences, geometry, toSelectedBones=True,
                                             obeyMaxInfluences=False, normalizeWeights=normalize_method)[0]

        # re-initialize
        self.__init__(skin_cluster_name)

        # Build look-up table for influence indexes.
        influences_ids = {}
        for inf_id in xrange(self.number_of_influences):
            influence_path = self.influence_objects[inf_id].fullPathName().split("|")[-1]
            influences_ids[influence_path] = inf_id

        weights = []
        for vert_id in xrange(len(points)):
            vertex_skin_array = [0.0] * self.number_of_influences

            # Get weight value saved on the vertex.
            blind_data_args = [vert_id, OpenMaya.MFn.kMeshVertComponent, blind_data_id, "weightsInfo"]
            vertex_string_data = mesh_object.getStringBlindData(*blind_data_args)
            influence_sets = vertex_string_data.split("|")[:-1]

            for influence_set in influence_sets:
                joint = influence_set.split(":")[0]
                joint_index = influences_ids.get(joint)
                weight = float(influence_set.split(":")[1])

                # Set weight value.
                vertex_skin_array[int(joint_index)] = weight

            # Extend the weight array.
            weights.extend(vertex_skin_array)

        # Set influence array correctly.
        weights = OpenMaya.MDoubleArray(weights)

        # Use the Maya API setWeights command to set all in one go.
        set_weight_args = [self.geometry_dag_path, self.vertex_component, self.influence_indexes, weights, False]
        self.skin_cluster_object.setWeights(*set_weight_args)

        # Log out the results of unbaking.
        args = [len(points), geometry_dag_path]
        message = "Successfully unbaked blind weight data from {} verts on {}.".format(*args)
        OpenMaya.MGlobal.displayInfo(message)
