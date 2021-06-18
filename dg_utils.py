from maya import cmds


def get_top_level_nodes_of_type(node_type, nodes=None, search_depth=None, **kwargs):
    """
    Gets the top level nodes for the given node type.

    .. NOTE::
        Kwargs can be used to expand the ls command for more filtering.
        e.g., The following returns all visible top level DAG objects.
        >> get_top_level_nodes_of_type("joint", depth=1, visible=True)

    :param str node_type: The node type to search for.
    :param list(str) nodes: Optional list of nodes to search through.
    :param int search_depth: The dag depth to find nodes of given type.
    :return: Returns the top level nodes for the given node type.
    :return: list(str)
    """
    # query the scene for nodes of given type with expanded search kwargs
    # defaults to using the ::* wildcard for nested reference filtering
    search_kwargs = dict(typ=node_type, long=True, dag=True, **kwargs)
    nodes_to_search = cmds.ls(nodes or "::*", **search_kwargs)

    # convert 0 to None for list slicing and convert 1 to 2 for dag root
    search_depth = search_depth or None
    search_depth = 2 if search_depth == 1 else search_depth

    def _top_level_node(node_path):
        """
        Find the node in the given node path that matches the given type.

        :param str node_path: Full path to a node to search.
        :return: Returns the full path to the node of given type.
        """
        # find the first node in the hierarchy that matches the given node type
        node_hierarchy = node_path.split("|")[:search_depth]
        for node_index, node in enumerate(node_hierarchy, 1):
            if node and cmds.nodeType(node) == node_type:

                # return the full path to the matching node in node hierarchy
                return "|".join(node_hierarchy[:node_index])

    # return a flattened list of the top level nodes
    nodes_map = map(lambda node: _top_level_node(node), nodes_to_search)
    return list(filter(None, set(nodes_map)))
