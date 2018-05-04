# built-in
import os
import json
from datetime import datetime

# third-party
from maya.api import OpenMaya, OpenMayaAnim
from maya import cmds
import KDTree

import skinning_utils
import maya_utils


def export_weights(geometry, path):
    skin_cluster_name = skinning_utils.get_skin_cluster_from_geometry(geometry)
    if not skin_cluster_name:
        return OpenMaya.MGlobal.displayWarning("No skinCluster found on {}!".format(geometry))

    # Get the skin weights.
    skin_handler = SkinHandler(skin_cluster_name)
    skin_handler.get_weights()

    # export
    with open(path, 'w') as weight_file:
        weight_file.write(json.dumps(skin_handler.data, sort_keys=True, indent=4))


def import_weights(geometry, path, method=None):
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

    # Create skinCluster if one does not already exist.
    skin_cluster_name = skinning_utils.get_skin_cluster_from_geometry(geometry)
    if not skin_cluster_name:
        skinning_utils.create_skin_cluster_from_geometry(geometry, data['influences'])
        skin_cluster_name = skinning_utils.get_skin_cluster_from_geometry(geometry)

    # Set the skin weights.
    skin_handler = SkinHandler(skin_cluster_name)
    skin_handler.set_weights(data, method)


def bake_weights(geometry, create_snapshot=None):
    # Create skinCluster if one does not already exist.
    skin_cluster_name = skinning_utils.get_skin_cluster_from_geometry(geometry)
    if not skin_cluster_name:
        return OpenMaya.MGlobal.displayWarning("No skinCluster found on {}!".format(geometry))

    # Build up the influence table.
    skin_handler = SkinHandler(skin_cluster_name)
    skin_handler.bake(create_snapshot)


def unbake_weights(geometry, snapshot_id=None):
    # Ensure geometry has a shape node.
    shapes = cmds.listRelatives(geometry, shapes=True)
    if not shapes:
        return OpenMaya.MGlobal.displayWarning("{} is not geometry!".format(geometry))

    # Get the available snapshots in the scene and validate against the snapshot id.
    available_blind_data = [cmds.getAttr("{}.typeId".format(blind_data)) for blind_data in cmds.ls(type="polyBlindData")]
    if snapshot_id:
        if not snapshot_id in available_blind_data:
            OpenMaya.MGlobal.displayWarning("{} is not a valid snapshot ID!".format(snapshot_id))
            return OpenMaya.MGlobal.displayWarning("Available snapshots: {}".format(available_blind_data))

    # Build up the influence table.
    skin_handler = SkinHandler()
    skin_handler.unbake(geometry, snapshot_id)


class SkinHandler(object):

    def __init__(self, skin_cluster_name=None):
        # Setting the skin cluster name to None is only used for unbaking.
        if not skin_cluster_name:
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
                     'verts': {}}


    def _set_influence_indexes(self):
        influence_indexes = OpenMaya.MIntArray(len(self.influence_objects), 0)
        for influence_object in range(self.number_of_influences):
            index = int(self.skin_cluster_object.indexForInfluenceObject(self.influence_objects[influence_object]))
            influence_indexes[influence_object] = index
        return influence_indexes

    def _set_influences(self):
        for influence_index in range(self.number_of_influences):
            influence = self.influence_objects[influence_index]
            influence_id = int(self.skin_cluster_object.indexForInfluenceObject(influence))
            self.data['influences'][influence_id] = influence.fullPathName()

    def _get_influence_weights(self):
        """Gathers up the weights using Maya's API."""
        return self.skin_cluster_object.getWeights(self.geometry_dag_path, self.vertex_component, self.influence_indexes)

    def get_weights(self):
        ws_point_list = KDTree.get_ws_point_list(self.input_geometry)
        vertex_normal_list = KDTree.get_vertex_normal_point_list(self.geometry_dag_path)

        # Gather up the influences.
        self._set_influences()

        # Get the influence weights using the Maya API.
        influence_weights = self._get_influence_weights()

        # build influence weight pairs
        skinning_info = {}
        for count, vertex in enumerate(range(0, len(influence_weights), self.number_of_influences), 0):
            skinning_info[count] = zip(self.influence_indexes, influence_weights[vertex:vertex + self.number_of_influences])

        # Save weight and position data for serialization.
        for vert_id in range(len(skinning_info)):
            position = [ws_point_list[vert_id].x, ws_point_list[vert_id].y, ws_point_list[vert_id].z]
            normal = [vertex_normal_list[vert_id].x, vertex_normal_list[vert_id].y, vertex_normal_list[vert_id].z]
            self.data['verts'][vert_id] = {'position': position,
                                           'normal': normal,
                                           'weights': [pair for pair in skinning_info[vert_id] if pair[-1] != 0.0]}

        # Log out the results of the getting of weights.
        args = [len(influence_weights), self.geometry_dag_path]
        message = "Successfully stored weight data for {} verts for {}.".format(*args)
        OpenMaya.MGlobal.displayInfo(message)

    def set_weights(self, data=None, method=None):
        # Data is not required so that you can reset the original weighting of the mesh, if needed.
        if data:
            self.data = data

        # The default method is point order.
        points = self.data['verts']
        if not method and len(points) != self.number_of_verts:
            return OpenMaya.MGlobal.displayWarning("Vert order does not match!")

        # Gather up positional data and find closest points if method is positions.
        if method == "positions":
            ws_point_list = [self.data['verts'][str(vert_id)]['position'] for vert_id in range(len(points))]
            KDT = KDTree.KDTree_from_point_list(ws_point_list)
            target_points = KDTree.get_ws_point_list(self.input_geometry)
            points = [KDTree.get_closest_position_in_KDTree(KDT, p)[0] for p in target_points]

        # Gather up normal data and find closest points if method is normals.
        elif method == "normals":
            vertex_normal_point_list = [self.data['verts'][str(vert_id)]['normal'] for vert_id in range(len(points))]
            KDT = KDTree.KDTree_from_point_list(vertex_normal_point_list)
            target_points = KDTree.get_vertex_normal_point_list(self.geometry_dag_path)
            points = [KDTree.get_closest_position_in_KDTree(KDT, p)[0] for p in target_points]

        # If a invalid method is passed, log out invalid method and default to point order.
        elif method:
            OpenMaya.MGlobal.displayWarning("Method {} invalid, defaulting to point order!".format(method))
            method = None

        # Unlock influences used by the skinCluster.
        for inf in self.influences:
            cmds.setAttr('%s.liw' % inf, 0)

        # Build up weight matrix.
        weights = []
        for vert_id in range(len(points)):

            # Set the initial state of the row in the weight matrix with default 0.0 values.
            vertex_skin_array = [0.0] * len(self.influence_indexes)

            # If the method is positions, then look up the closest point from the KDT table.
            if method == "positions":
                vert_id = points[vert_id]

            # Build up the vertex skin array to extend the data to the weight MDoubleArray.
            for influence_set in self.data['verts'][str(vert_id)]['weights']:

                # get correct joint id
                joint_index = influence_set[0]
                weight = influence_set[1]

                # set weight value
                vertex_skin_array[int(joint_index)] = weight

            # Extend the weight array.
            weights.extend(vertex_skin_array)

        # Set influence array correctly.
        weights = OpenMaya.MDoubleArray(weights)

        # Use the Maya API setWeights command to set all in one go.
        set_weight_args = [self.geometry_dag_path, self.vertex_component, self.influence_indexes, weights, False]
        self.skin_cluster_object.setWeights(*set_weight_args)

        # Log out the results of the setting of weights.
        if not method:
            method = "point order"
        args = [method, len(points), len(self.data['verts']), self.geometry_dag_path]
        message = "Successfully set weights using the '{}' method on {} out of {} verts for {}.".format(*args)
        OpenMaya.MGlobal.displayInfo(message)

    def bake(self, create_snapshot=None):
        # For snapshots, to capture the current time, down to the second as an integer format.
        blind_data_id = datetime.now().year
        if create_snapshot:
            blind_data_id = int(datetime.now().strftime("%m%d%H%M%S"))

        # Build data.
        self.get_weights()

        # Set vertex mint Array.
        number_of_verts = len(self.data['verts'])
        vertex_array = OpenMaya.MIntArray()
        for count in range(number_of_verts):
            vertex_array.append(count)

        # Set the data to save onto the mesh.
        data_to_set = []
        for vert_id in range(len(self.data['verts'])):

            # Setup the plugs for attribute reading.
            plug_weight_list = self.skin_cluster_object.findPlug("weightList", False)
            weight_list_attr = plug_weight_list.attribute()
            plug_weights = self.skin_cluster_object.findPlug("weights", False)
            weights_attr = plug_weights.attribute()

            # Vertex id's.
            plug_weights.selectAncestorLogicalIndex(vert_id, weight_list_attr)

            # Joint id's.
            joint_ids = plug_weights.getExistingArrayAttributeIndices()

            # Set weight id values and save build weight string.
            weight_string = ""
            influence_plug = plug_weights
            for index in range(len(joint_ids)):
                influence_joint_id = joint_ids[index]
                influence_plug.selectAncestorLogicalIndex(influence_joint_id, weights_attr)
                weight = influence_plug.asFloat()
                bone_name = self.influence_objects[self.influence_indexes[influence_joint_id]].partialPathName()

                # Actual string to be set on mesh.
                weight_string += bone_name + ":" + str(weight) + "|"

            # Append for set command.
            data_to_set.append(weight_string)

        # Create blind data tuples (mstring arrays).
        blind_data_tuple = (("weightsInfo", "wi", "string"),)*3
        if not cmds.blindDataType(q=True, id=blind_data_id):
            self.mesh_object.createBlindDataType(blind_data_id, blind_data_tuple)

        # Save string data to verts.
        self.mesh_object.setStringBlindData(vertex_array, OpenMaya.MFn.kMeshVertComponent, blind_data_id, "weightsInfo", data_to_set)

        # Log out the results of baking.
        args = [len(self.data['verts']), self.geometry_dag_path]
        message = "Successfully baked blind weight data from {} verts onto {}.".format(*args)
        OpenMaya.MGlobal.displayInfo(message)

    def unbake(self, geometry, snapshot_id=None):
        # Account for blind data snapshots.
        blind_data_id = datetime.now().year
        if snapshot_id:
            blind_data_id = snapshot_id

        # Return out and report if the snapshot ID is not valid.
        if not cmds.blindDataType(q=True, id=blind_data_id):
            return OpenMaya.MGlobabl.displayWarning("{} is not a valid snapshot ID".format(blind_data_id))

        # Delete skinCluster if one already exists.
        skin_cluster = skinning_utils.get_skin_cluster_from_geometry(geometry)
        if skin_cluster:
            cmds.delete(skin_cluster)

        # Get the MFnMesh to query the blind data.
        geometry_dag_path = maya_utils.get_dag_path_object(geometry)
        geometry_dag_path.extendToShape()
        mesh_object = OpenMaya.MFnMesh(geometry_dag_path)

        # Get stringBlindData from the geometry
        mint_array, string_data = mesh_object.getStringBlindData(OpenMaya.MFn.kMeshVertComponent, blind_data_id, "weightsInfo")

        # Get influences for new skinCluster (exact joints are needed).
        influences = []
        for data in string_data:
            joints = [x.split(":")[0] for x in data.split("|")]
            influences.extend(joints)
        influences = filter(None, list(set(influences)))

        # Create new skinCluster with the correct influences.
        skin_cluster_name = cmds.skinCluster(influences, geometry, tsb=True, omi=False, nw=True)[0]

        # re-initialize
        self.__init__(skin_cluster_name)

        # Grab new skinCluster joint id's to have the correct indexes.
        influences_ids = {}
        for inf_id in range(self.number_of_influences):
            influence_path = self.influence_objects[inf_id].fullPathName().split("|")[-1]
            influences_ids[influence_path] = inf_id

        # unlock influences used by skincluster
        for inf in influences:
            cmds.setAttr('%s.liw' % inf, 0)

        weights = []
        for vert_id in range(len(mint_array)):
            vertex_skin_array = [0.0] * len(self.influence_indexes)

            # get weight value
            vertex_string_data = mesh_object.getStringBlindData(vert_id, OpenMaya.MFn.kMeshVertComponent, blind_data_id, "weightsInfo")
            influence_sets = filter(None, vertex_string_data.split("|"))
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
        args = [len(mint_array), geometry_dag_path]
        message = "Successfully unbaked blind weight data from {} verts on {}.".format(*args)
        OpenMaya.MGlobal.displayInfo(message)
