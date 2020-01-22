# Copyright 1998-2019 Epic Games, Inc. All Rights Reserved.

# built-in
import sys
import logging

# third-party
from maya import cmds
from maya.api import OpenMaya

# internal
from .utils import skin_utils

# Use xrange if using python 2.
if sys.version_info[0] < 3:
    # noinspection PyShadowingBuiltins
    range = xrange

logger = logging.getLogger(__name__)


class BaseSkinCluster(object):
    def __init__(self, mesh=None):
        """
        Base class for handling skinClusters on a mesh. This class it built on
        properties for validation and for dynamically working with possible
        changed data in Maya. The mesh name might stay the same, but it's
        very possible that the influences, the skinCluster and the shape nodes
        will be changed. By relying on properties it can be made certain that
        no matter these changes, this class will do it's best to work.
        .. glossary::
            mesh:
                A collection of geometry.
            geometry:
                Components that make up a mesh.
        .. NOTE::
            A mesh IS made up of geometry but geometry is NOT made up of a mesh.
            A single mesh CAN be made up of many geometric components.
            A mesh is NOT multiple meshes.
        :param mesh: The mesh the skinCluster is attached to (optional).
        """

        self._mesh = None
        self._influence_indexes = None

        if mesh:
            self.set_mesh(mesh)

        # Vertex component for Maya API.
        self.vertex_component = skin_utils.get_vertex_component()

    @property
    def mesh(self):
        return self._mesh

    @property
    def mesh_object(self):
        """
        Returns the mesh object from the passed in mesh. This is the object used
        for getting, setting and baking weights on the mesh.

        :return: Returns the mesh object.
        :rtype: MFnMesh
        """
        # Must extend to shape in order to get the MFnMesh.
        self.mesh_dag_path_object.extendToShape()
        return OpenMaya.MFnMesh(self.mesh_dag_path_object)

    @property
    def mesh_dag_path_object(self):
        """
        Returns the dag path object from the OutputGeometry defined on the
        skinCluster object.

        :return: Returns the dag path object from the OutputGeometry defined
        on the skinCluster object.
        :rtype: MDagPath
        """
        return skin_utils.get_dag_path_object(self.output_geometry)

    @property
    def skin_cluster(self):
        """
        Returns the skinCluster's name based on the passed in mesh.

        :return: Returns the skinCluster's name.
        :rtype: str
        """
        return skin_utils.get_skin_cluster_from_mesh(self.mesh)

    @property
    def skin_cluster_object(self):
        """
        Validates that a skinCluster can be grabbed from the set mesh. If one
        is not found errors are raise to prevent further operations.

        :return: Returns the skinCluster object.
        :rtype: MFnSkinCluster
        """
        try:
            return skin_utils.get_skin_cluster_object(self.skin_cluster)
        except TypeError:
            raise TypeError(
                "No skinCluster found on {mesh}!".format(mesh=self.mesh)
            )
        except RuntimeError:
            raise RuntimeError(
                "No mesh has been set on {class_name}! Please initialize with "
                "a mesh or use the built in set_mesh method!".format(
                    class_name=self.__class__.__name__
                )
            )

    @property
    def input_geometry(self):
        """
        Returns the InputGeometry dag path based on the skinCluster object.

        :return: Returns the InputGeometry dag path from the skinCluster object.
        :rtype: str
        """
        input_geometry = self.skin_cluster_object.getInputGeometry()
        dag_node = OpenMaya.MFnDagNode(input_geometry[0])
        return dag_node.fullPathName()

    @property
    def output_geometry(self):
        """
        Grabs the OutputGeometry dag path associated with skinCluster object.

        :return: Returns the fullPath to the output geometry.
        :rtype: str
        """
        output_geometry = self.skin_cluster_object.getOutputGeometry()
        dag_node = OpenMaya.MFnDagNode(output_geometry[0])
        return dag_node.fullPathName()

    @property
    def number_of_verts(self):
        """
        Returns the number of verts based on the given mesh.

        :return: Returns the number of verts on the mesh.
        """
        return len(self.mesh_object.getPoints())

    @property
    def length_of_weight_matrix(self):
        """
        The length weight matrix is the number of verts multiplied by the
        number of influences.

        :return: Returns the number length of the weight matrix.
        """
        return len(self.get_weights())

    @property
    def influences(self):
        """
        :return: Returns the full dag path of all joint influences on the
        skinned mesh.
        :rtype: list
        """
        return [
            influence.fullPathName() for influence in self.influence_objects
        ]

    @property
    def influence_objects(self):
        """
        Grabs all the influence objects on from the skinCluster on the mesh.

        :return: MDagPathArray([MDagPath])
        """
        return self.skin_cluster_object.influenceObjects()

    @property
    def number_of_influences(self):
        """
        Based on the number of influence objects modified on the skinCluster,
        this will return the number of 'current' influences.

        :return: Returns the current number of influences on the skinCluster.
        :rtype: int
        """
        return len(self.influence_objects)

    @property
    def influence_indexes(self):
        """
        Returns the influence indexes in the order needed to build the weight
        matrix.

        :return: Returns the influence indexes.
        :rtype: MIntArray
        """
        return self._influence_indexes

    def set_mesh(self, mesh):
        """
        This method allows for re-building from a different mesh or if the name
        of the mesh changes. Without having using message connections or
        relying on internal workflows/tools the names of meshes in the scene
        are not absolute.

        :param str mesh: Name of mesh to build from.
        """
        self._mesh = mesh

        # Build influence indexes. This must happen to ensure that the
        # weight table builds correctly.
        self.build_influence_indexes()

    def get_skinning_data(self):
        """Data handle place holder."""
        pass

    def set_skinning_data(self, *args, **kwargs):
        """Data handle setter place holder."""
        pass

    def build_influence_indexes(self):
        """
        Builds the influence indexes on the MIntArray related to the skinCluster.
        This is very Important! This method allows for rebuilding the influence
        list if the influences on the mesh ever change.

        .. NOTE:: Setting the influences can be arbitrary as long as it loads
        weights with the same influence indexes assigned.
        """
        # Build MIntArray based on the number of influences on the skinCluster.
        self._influence_indexes = OpenMaya.MIntArray(
            self.number_of_influences,
            0,  # Initial value of each element.
        )
        # Set the proper influence index in the MIntArray.
        for influence_index in range(self.number_of_influences):
            self._influence_indexes[influence_index] = influence_index

    def get_weights(self):
        """
        Grabs the weights of the skin cluster object.

        :return: Returns the weight matrix.
        :rtype: MDoubleArray
        """
        weights = self.skin_cluster_object.getWeights(
            self.mesh_dag_path_object,  # path
            self.vertex_component,  # component type
            self.influence_indexes,  # influence indexes
        )
        return weights

    def get_weight_chunks(self):
        """
        Returns a list of all the weight chunks in the weight matrix. This is
        useful as a lookup table when modifying weight values on specific
        verts.

        :return: Returns a list of all the weight chunks.
        :rtype: list(list)
        """
        weights = self.get_weights()
        number_of_influences = self.number_of_influences

        # Build up chunks as fast as possible.
        weight_chunks = []
        for i in range(0, len(weights), number_of_influences):
            weight_chunks.append(weights[i:i + number_of_influences])
        return weight_chunks

    def set_weights(self, weight_matrix, normalize=True, undo=False):
        """
        Sets the weights on the skinCluster object.

        :param MIntArray weight_matrix: The weight matrix containing the new
        values of the weights.
        :param bool normalize: Whether or not to normalize weights.
        :param bool undo: If True, this will make the setting of weights
        undoable.
            .. NOTE::
                This can make the operation take much longer depending on the
                density of the mesh.
        """
        self.skin_cluster_object.setWeights(
            self.mesh_dag_path_object,  # path
            self.vertex_component,  # component type
            self.influence_indexes,  # influence indexes
            weight_matrix,  # new weights
            normalize,  # normalize
            undo,  # Undoable.
        )

    def bake_vertex_blind_data(
            self,
            data_to_bake,
            weight_matrix,
            blind_data_id,
            attribute_name="weightsInfo",
            attribute_short_name="wi",
    ):
        """
        Sets the given bake data onto the verts assigned in the weight matrix.

        :param list data_to_bake: The list of the data to bake in the order
        to set in the weight matrix, this must match the chunk size of the
        weight matrix.
        :param MDoubleArray weight_matrix: The weight matrix.
        :param int blind_data_id: The assigned blind data ID. This is unique
        and can only be one in the scene.
        :param str attribute_name: The name of attribute to create on the
        polyBlindData node.
        :param str attribute_short_name: The attribute short name.
        """
        if len(data_to_bake) != len(weight_matrix):
            raise ValueError(
                "The chunk size of the data to bake does not match the chunk "
                "size of the weight matrix. Please ensure that the data you're "
                "trying to bake matches chunk size. Otherwise, the applied "
                "bake data will not be correct!"
            )
        # Create blind data tuples (MString arrays). The createBlindDataType
        # requires this in the API.
        blind_data_tuple = (
            (attribute_name, attribute_short_name, "string"),
        ) * 3
        if not cmds.blindDataType(query=True, typeId=blind_data_id):
            self.mesh_object.createBlindDataType(blind_data_id, blind_data_tuple)

        # Save string data to the verts in the weight matrix.
        self.mesh_object.setStringBlindData(
            weight_matrix,
            OpenMaya.MFn.kMeshVertComponent,
            blind_data_id,
            attribute_name,
            data_to_bake,
        )

    def get_vertex_string_blind_data(
            self,
            blind_data_id,
            vert_id=None,
            attribute_name="weightsInfo"
    ):
        """
        Returns the blind data associated with the blind data ID and the
        name of the attribute to query.
        :param int blind_data_id: The blind data ID.
        :param int vert_id: The vert to ID to query data from.
        :param str attribute_name: The attribute to query on the polyBlindData
        node.
        :return: Returns a tuple containing the weight matrix and the string
        data associated with it.
        :rtype: list_or_tuple
        """
        # Grab string data from a single vert.
        if isinstance(vert_id, int):
            return self.mesh_object.getStringBlindData(
                vert_id,
                OpenMaya.MFn.kMeshVertComponent,
                blind_data_id,
                attribute_name
            )
        # Or grab string data from all verts.
        else:
            return self.mesh_object.getStringBlindData(
                OpenMaya.MFn.kMeshVertComponent,
                blind_data_id,
                attribute_name
            )

    def get_mesh_world_space_points(self):
        """Gets the world space points from the mesh object."""
        points = self.mesh_object.getPoints(OpenMaya.MSpace.kWorld)
        return [OpenMaya.MVector(point) for point in points]

    def get_mesh_vertex_normal_points(self):
        """Gets the vertex normal points from the mesh object."""
        points = self.mesh_object.getVertexNormals(
            False,
            space=OpenMaya.MSpace.kWorld
        )
        return [OpenMaya.MVector(points[point]) for point in range(len(points))]

    def get_weight_data(self):
        """
        Convenience method for getting the weights data. This method chunks
        based on number of weighted values/number of influences. This allows
        for a lookup table to store different types of imports i.e., closest
        point, vertex normals, etc.

        :return: Returns the data dictionary containing data about the weights.
        :rtype: dict
        """
        # Cache data for iteration speed.
        number_of_influences = self.number_of_influences
        influence_indexes = self.influence_indexes
        weights = self.get_weights()
        length_of_weight_matrix = len(weights)

        # Build up serializable data about the skin weighting.
        range_args = [
            0,  # start
            length_of_weight_matrix,  # stop
            number_of_influences  # step
        ]

        weight_data = {}
        for vertex_id, vertex in enumerate(range(*range_args), start=0):
            weight_data[vertex_id] = zip(
                influence_indexes,  # influence index
                weights[vertex:vertex + number_of_influences]  # weight value
            )
        return weight_data

    def get_unused_influences(self):
        """
        Internal method for getting all unused influences on the SkinCluster
        """
        weighted_influences = cmds.skinCluster(
            self.skin_cluster,
            query=True,
            weightedInfluence=True,
        )
        all_influences = cmds.skinCluster(
            self.skin_cluster,
            query=True,
            influence=True,
        )
        return list(set(all_influences) - set(weighted_influences))

    def remove_unused_influences(self):
        """Internal method for removing unused influences on the skinCluster."""
        for influence in self.get_unused_influences():
            cmds.skinCluster(
                self.skin_cluster,
                edit=True,
                removeInfluence=influence
            )

    def get_missing_influences(self, influences):
        """
        Gets the influences missing from the skinCluster.

        :param list influences: The list of influences to compare with.
        :return: Returns the missing influences on the skinCluster.
        :rtype: list
        """
        # Ensure the items in the influence list are the fullPath.
        influences = cmds.ls(influences, long=True)
        return list(set(self.influences) - set(influences))

