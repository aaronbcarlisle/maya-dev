# Copyright 1998-2019 Epic Games, Inc. All Rights Reserved.

# built-in
import sys
import time
from datetime import datetime

# third-party
from maya import cmds
from maya.api import OpenMaya

# internal
from .utils import skin_utils
from .skin_cluster import BaseSkinCluster

# Use xrange if using python 2.
if sys.version_info[0] < 3:
    # noinspection PyShadowingBuiltins
    range = xrange


def get_unique_blind_data_id():
    """
    It's possible for objects to have the same ID if they're made at the same
    time. This method ensures the ID that is returned is unique.

    :return: Returns unique blind data ID.
    :rtype: int
    """
    blind_data_id = int(time.time())
    all_blind_data_ids = skin_utils.get_all_blind_data_ids()
    if blind_data_id in all_blind_data_ids:
        blind_data_id = max(all_blind_data_ids) + 1
    return blind_data_id


class SkinClusterImportMethod(object):
    """Import Method Enum Class."""
    CLOSEST_POINT = "position"
    VERTEX_NORMAL = "normal"
    VERT_ORDER = None


class SkinClusterManager(BaseSkinCluster):

    DEFAULT_BLIND_DATA_ID = datetime.now().year

    def get_skinning_data(self):
        """
        This method builds up a data structure from the skinning information
        based on the mesh. This overrides the base class method and
        determines the serialization format.

        :return: Returns the serializable skinning data.
        :rtype: dict
        """
        # Create data structure.
        data = {
            "input_geometry": self.input_geometry,
            "influences": self.influences,
            "influence_ids": list(range(self.number_of_influences)),
            "verts": {},
        }

        # Cache weights and positions.
        weight_data = self.get_weight_data()
        world_space_points = self.get_mesh_world_space_points()
        vertex_normal_points = self.get_mesh_vertex_normal_points()

        # Build up data structure.
        for vert_id in range(len(weight_data)):
            world_space_position = [
                world_space_points[vert_id].x,
                world_space_points[vert_id].y,
                world_space_points[vert_id].z
            ]
            vertex_normal_position = [
                vertex_normal_points[vert_id].x,
                vertex_normal_points[vert_id].y,
                vertex_normal_points[vert_id].z
            ]

            # Build up weight values to be stored, skipping 0.0 and NaN values.
            weights = []  # Pairs of influence and value (0, 1.0), (1, 1.0), etc
            for pair in weight_data[vert_id]:
                weight_value = pair[-1]
                if weight_value != 0.0 and str(weight_value) != "NaN":
                    weights.append(pair)

            # Set vert data.
            data['verts'][vert_id] = {
                "position": world_space_position,
                "normal": vertex_normal_position,
                "weights": weights,
            }
        return data

    def set_skinning_data(
            self,
            skinning_data,
            import_method=None,
            normalize=False,
            undo=False,
            verts=None
    ):
        """
        This method sets the given skinning data onto the mesh.

        :param dict skinning_data: Dictionary containing the data to import.
        :param str import_method:
            SkinClusterManager.CLOSEST_POINT
            SkinClusterManager.VERT_NORMAL
        :param bool normalize: Whether or not to normalize weights.
        :param bool undo: Whether or not to make operation undoable.
        :param list verts: List of verts to set weights on (optional). If not
        set the method will set weights on all verts.
        """
        # Determine if the points to import are of a different import method
        # than vertex order.
        points = None if not import_method else self._get_points(
            skinning_data,
            import_method,
        )

        # Unlock influences used by the skinCluster.
        [cmds.setAttr("{i}.liw".format(i=i), 0) for i in self.influences]

        # Get the MDoubleArray for the setWeights command.
        weight_matrix = self._get_weight_matrix(
            skinning_data,
            points=points,
            verts=verts,
        )

        # Use the Maya API setWeights command to set all in one go.
        self.set_weights(
            weight_matrix=weight_matrix,
            normalize=normalize,
            undo=undo
        )

    def bake_weights(self, create_snapshot=None, blind_data_id=None):
        """
        Bakes weighting data using polyBlindData nodes.

        :param bool create_snapshot: If True, a unique blind data ID will be
        created allowing multiple 'snapshots' of weighting on a single mesh.
        :return: Returns the polyBlindData node created.
        :param int blind_data_id: Blind data ID to create or stomp over.
        :rtype: str
        """
        skinning_data = self.get_skinning_data()
        number_of_verts = self.number_of_verts
        influence_indexes = self.influence_indexes
        number_of_influences = self.number_of_influences
        influence_objects = self.influence_objects

        # Get blind data ID.
        if blind_data_id:
            blind_data_id = blind_data_id
        elif not blind_data_id and create_snapshot:
            blind_data_id = get_unique_blind_data_id()
        else:
            blind_data_id = SkinClusterManager.DEFAULT_BLIND_DATA_ID

        data_to_bake = []
        weight_matrix = OpenMaya.MIntArray()
        for vert_id in range(number_of_verts):

            # Build up blind data chunk from vert id.
            blind_data_chunk = [""] * number_of_influences
            for influence_set in skinning_data['verts'][vert_id]['weights']:
                joint_index = influence_set[0]
                weight_value = influence_set[1]

                bone_name = influence_objects[
                    influence_indexes[joint_index]
                ].partialPathName()

                # Ensure that the correct data gets set on the correct index.
                blind_data_chunk[joint_index] = (
                    "{bone_name}:{weight_value}|".format(
                        bone_name=bone_name,
                        weight_value=weight_value
                    )
                )

            # Ensure the string is one long string.
            blind_data_chunk = "".join(blind_data_chunk)

            # Append for set command.
            data_to_bake.append(blind_data_chunk)
            weight_matrix.append(vert_id)

        self.bake_vertex_blind_data(data_to_bake, weight_matrix, blind_data_id)
        return skin_utils.get_blind_data_node_from_id(blind_data_id)

    def unbake_weights(self, blind_data_id, verts=None):
        """
        Applies the weighting info stored on the verts via polyBlindData.

        :param int blind_data_id: Blind data ID to apply weights from.
        :param list verts: List of verts to set weights on (optional). If not
        set the method will set weights on all verts.
        """
        weight_chunks = self.get_weight_chunks() if verts else None
        influences = [influence.split("|")[-1] for influence in self.influences]
        number_of_influences = self.number_of_influences

        vert_ids, vertex_string_data = self.get_vertex_string_blind_data(
            blind_data_id
        )

        # This is very important. By default, the data comes back in reverse,
        # making the lookup table point order backwards but effective for
        # applying blind data to all verts. When applying weight data
        # to specific verts, the vert ID's need to start at 0 and the data
        # containing the weight information needs to be reversed to match index.
        vert_ids = range(len(vert_ids))
        vertex_string_data.reverse()

        weight_matrix = []
        for vert_id in vert_ids:
            data = vertex_string_data[vert_id]

            weight_chunk = [0.0] * number_of_influences

            # Don't change anything if the vert isn't in the vert list.
            if weight_chunks and vert_id not in verts:
                weight_chunk = weight_chunks[vert_id]
            # Otherwise build weight chunk from blind data.
            else:
                influence_sets = data.split("|")[:-1]
                for influence_set in influence_sets:
                    influence = influence_set.split(":")[0]
                    joint_index = influences.index(influence)
                    weight = float(influence_set.split(":")[1])

                    # Set weight value.
                    weight_chunk[joint_index] = weight

            # Extend the weight array.
            weight_matrix.extend(weight_chunk)

        # Convert weight matrix to MDoubleArray for setWeights command.
        weight_matrix = OpenMaya.MDoubleArray(weight_matrix)

        # Use the Maya API setWeights command to set all in one go.
        self.set_weights(weight_matrix)

    def get_all_snapshots(self):
        """
        Grabs all the polyBlindData snapshots in the scene.

        :return: Returns a dictionary of all the associated polyBlindData
        in the scene.
        :rtype: dict
        """
        connected_snapshots = self.get_connected_snapshots()
        disconnected_snapshots = self.get_disconnected_snapshots()
        connected_snapshots.update(disconnected_snapshots)
        return connected_snapshots

    @staticmethod
    def get_disconnected_snapshots():
        """
        Grabs all the polyBlindData nodes that are not directly connected to
        any mesh.

        :return: Returns a dictionary containing data about all the
        polyBlindData nodes not connected to a mesh.
        :rtype: dict
        """
        snapshots = {}
        shapes = cmds.ls(type="shape")
        for shape in shapes:
            blind_data_nodes = "{shape}.blindDataNodes".format(shape=shape)
            if cmds.objExists(blind_data_nodes):
                nodes = cmds.listConnections(blind_data_nodes) or []
                for node in nodes:
                    # Don't add base snapshots to the QListWidget.
                    blind_data_id = cmds.getAttr(
                        "{node}.typeId".format(node=node)
                    )

                    # Skip nodes baked with default blind data ID.
                    if len(str(blind_data_id)) < 5:
                        continue

                    # Build up blind data info.
                    mesh = cmds.listRelatives(shape, parent=True)[0]
                    timestamp = str(time.ctime(int(blind_data_id)))
                    snapshot_data = {
                        "id": blind_data_id, "timestamp": timestamp
                    }
                    if not snapshots.get(mesh):
                        snapshots[mesh] = [snapshot_data]
                    else:
                        snapshots[mesh].append(snapshot_data)
        return snapshots

    @staticmethod
    def get_connected_snapshots():
        """
        Grabs all the polyBlindData nodes that are directly connected to meshes.

        :return: Returns a dictionary containing data about all the
        polyBlindData nodes connected to a mesh.
        :rtype: dict
        """
        snapshots = {}
        all_blind_data_ids = skin_utils.get_all_blind_data_ids()
        for blind_data_id in all_blind_data_ids:
            # Skip nodes baked with default blind data ID.
            if len(str(blind_data_id)) < 5:
                continue

            blind_data_node = skin_utils.get_blind_data_node_from_id(
                blind_data_id
            )

            # Build up blind data info.
            mesh = skin_utils.get_mesh_from_blind_data_node(blind_data_node)
            timestamp = str(time.ctime(int(blind_data_id)))
            snapshot_data = {
                "id": blind_data_id, "timestamp": timestamp
            }
            if not snapshots.get(mesh):
                snapshots[mesh] = [snapshot_data]
            else:
                snapshots[mesh].append(snapshot_data)
        return snapshots

    @staticmethod
    def _get_weight_chunk(
            vert_id,
            skinning_data,
            number_of_influences,
            influences
    ):
        """
        Builds up the weight chunk for the passed in vert ID.

        :param dict skinning_data: Dictionary containing the skinning data.
        :param int vert_id: The vert id to query.
        :param int number_of_influences: Number of influences.
        :return: Returns the weight chunk from the weight matrix.
        :rtype: list
        """
        # Build up weight chunk from vert id.
        weight_chunk = [0.0] * number_of_influences
        skinning_data_influences = skinning_data.get("influences")
        for influence_set in skinning_data['verts'][vert_id]['weights']:
            # Lookup joint from influences in skinning data to ensure the
            # correct index is replaced/added.
            joint_index = influences.index(
                skinning_data_influences[influence_set[0]]
            )
            weight_value = influence_set[1]

            weight_chunk[joint_index] = weight_value

        return weight_chunk

    def _get_weight_matrix(self, skinning_data, points=None, verts=None):
        """
        Determines the weight matrix using the skinning data and the current
        mesh the weights are going to be applied to.

        :param dict skinning_data: The skinning data to compare with.
        :param list points: The list of points that are not of vertex order.
        :return: Returns the weight matrix needed to be used in the setWeights
        command.
        :param list verts: List of verts to set weights on (optional). If not
        set the method will set weights on all verts.
        :rtype: MDoubleArray.
        """
        # Cache data for iteration.
        weight_chunks = self.get_weight_chunks() if verts else None
        number_of_influences = self.number_of_influences
        number_of_verts = self.number_of_verts
        influences = self.influences

        # convert vertexes to closest points if using a method other than
        # vertex order.
        if points and verts:
            for vert in verts:
                index = verts.index(vert)
                verts[index] = points[vert]

        # Build up weight matrix from skinning data.
        weight_matrix = []
        for vert_id in range(number_of_verts):

            # Find the matching point if not vertex order.
            if points:
                vert_id = points[vert_id]

            # Don't change anything if the vert isn't in the vert list.
            if weight_chunks and vert_id not in verts:
                weight_chunk = weight_chunks[vert_id]
            else:
                # Build new weight chunk.
                weight_chunk = self._get_weight_chunk(
                    vert_id,
                    skinning_data,
                    number_of_influences,
                    influences,
                )

            # Build up the weight matrix.
            weight_matrix.extend(weight_chunk)

        # return the weight matrix as an MDoubleArray for the setWeights
        # command.
        return OpenMaya.MDoubleArray(weight_matrix)

    def _get_points(self, skinning_data, import_method):
        """
        Grabs the closest points based on whether the user wants to query
        based on closest point or vertex normal.

        :param dict skinning_data: The skinning data to compare and match.
        :param str import_method: Determines what points match.
            SkinClusterManager.CLOSEST_POINT
            SkinClusterManager.VERT_NORMAL
            SkinClusterManager.VERT_ORDER (None)
        :return: Returns the list of points that match in the correct order.
        This list is dependent on influence index matching.
        :rtype: list
        """
        vert_data = skinning_data["verts"]

        # Find points based on closest point.
        if import_method == SkinClusterImportMethod.CLOSEST_POINT:
            source_points = skin_utils.convert_points_to_mvectors(
                [
                    vert_data[vert_id]['position'] for vert_id in range(
                    len(vert_data)
                )
                ]
            )
            target_points = self.get_mesh_world_space_points()
        # Find points based on vertex normals.
        elif import_method == SkinClusterImportMethod.VERTEX_NORMAL:
            source_points = skin_utils.convert_points_to_mvectors(
                [
                    vert_data[vert_id]['normal'] for vert_id in range(
                    len(vert_data)
                )
                ]
            )
            target_points = self.get_mesh_world_space_points()
        # Raise if an invalid import method has been passed in.
        else:
            raise TypeError(
                "{import_method} is not a valid import method, "
                "expected {closest_point_method}, {vertex_normal_method} "
                " or {vertex_order_method}!".format(
                    import_method=import_method,
                    closest_point_method=SkinClusterImportMethod.CLOSEST_POINT,
                    vertex_normal_method=SkinClusterImportMethod.VERTEX_NORMAL,
                    vertex_order_method=str(SkinClusterImportMethod.VERT_ORDER),
                )
            )

        # Find the closest point in the target points from the source points
        # using a KDTree for lookup.
        kdtree = skin_utils.get_kdtree_from_points(source_points)
        return [
            skin_utils.get_closest_point_in_kdtree(
                kdtree,  # based off the source points
                target_point  # points on mesh to find closest to
            )[0] for target_point in target_points
        ]
