
from maya import cmds
from maya.api import OpenMaya, OpenMayaAnim


class BaseSkinCluster:

    def __init__(self, mesh):
        self._mesh = mesh
        self._influence_indexes = None

        single_index_component = OpenMaya.MFnSingleIndexedComponent()
        self.vertex_component = single_index_component.create(
            OpenMaya.MFn.kMeshVertComponent
        )

    @property
    def mesh(self):
        return self._mesh

    @mesh.setter
    def mesh(self, mesh):
        self._mesh = mesh

    @property
    def skin_cluster(self):
        """
        Gets the skinCluster from the mesh.

        :return: Returns the skinCluster from the mesh.
        :rtype: str
        """
        history = cmds.listHistory(self.mesh, pruneDagObjects=True)
        skin_cluster = cmds.ls(history, type="skinCluster")
        return skin_cluster[0] if skin_cluster else ""

    @property
    def skin_cluster_object(self):
        """
        Gets the MFnSkinCluster object from the skinCluster.

        :return: Returns the MFnSkinCluster object from the skinCluster.
        :rtype: OpenMayaAnim.MFnSkinCluster
        """
        selection_list = OpenMaya.MGlobal.getSelectionListByName(self.skin_cluster)
        mobject = selection_list.getDependNode(0)
        return OpenMayaAnim.MFnSkinCluster(mobject)

    @property
    def output_geometry(self):
        """
        Gets the output geometry from the skinCluster.

        :return: Returns the output geometry object from the skinCluster.
        :rtype: str
        """
        output_geometry = self.skin_cluster_object.getOutputGeometry()
        dag_node = OpenMaya.MFnDagNode(output_geometry[0])
        return dag_node.fullPathName()

    @property
    def mesh_dag_path_object(self):
        """
        Gets the DAG path object from the skinCluster.

        :return: Returns the MFnSkinCluster object from the skinCluster.
        :rtype: OpenMaya.MDagPath
        """
        selection_list = OpenMaya.MGlobal.getSelectionListByName(
            self.output_geometry
        )
        return selection_list.getDagPath(0)

    @property
    def influence_indexes(self):
        """
        Gets the influence indexes for the skinCluster.

        :return: Returns the influence indexes for the skinCluster.
        :rtype: OpenMaya.MIntArray
        """
        self._influence_indexes = OpenMaya.MIntArray(
            self.number_of_influences,
            0  # initial value of each index
        )

        # build up the influence indexes
        for influence_index in range(self.number_of_influences):
            self._influence_indexes[influence_index] = influence_index

        return self._influence_indexes

    @property
    def influence_objects(self):
        """
        Gets the influence objects on the skinCluster.

        :return: Returns influence objects on the skinCluster.
        :rtype: OpenMaya.MDagPathArray
        """
        return self.skin_cluster_object.influenceObjects()

    @property
    def number_of_influences(self):
        """
        Gets the number of influences on the skinCluster.

        :return: Return the number of influences on the skinCluster.
        :rtype: int
        """
        return len(self.influence_objects)

    def get_weights(self):
        """
        Gets the weight matrix for the skinCluster.

        :return: Gets the weight matrix for the skinCluster.
        :rtype: OpenMaya.MDoubleArray
        """
        return self.skin_cluster_object.getWeights(
           self.mesh_dag_path_object,  # MDagPath
           self.vertex_component,  # component type; MeshVert
           self.influence_indexes
        )

    def set_weights(self, weight_matrix, normalize=True, undo=False):
        """
        Sets the weights on the skinCluster using the values from the given
        weight matrix.

        :param OpenMaya.MDoubleArray weight_matrix: Weight matrix to apply.
        :param bool normalize: Whether to normalize the weights.
        :param bool undo: Returns the old weights.
        :return: Returns the old weights if undo is True.
        :rtype: bool or None
        """
        return self.skin_cluster_object.setWeights(
            self.mesh_dag_path_object,
            self.vertex_component,
            self.influence_indexes,
            weight_matrix,
            normalize,
            undo
        )
