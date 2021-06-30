from maya import cmds


def get_root_nodes_of_type(node_type, nodes=None, search_depth=None, **kwargs):
    """
    Gets the all root nodes for a given node type.

    .. NOTE::
        Kwargs can be used to expand the ls command for more filtering.
        e.g., The following returns all visible root joint nodes.
        >> get_root_nodes_of_type("joint", visible=True)

    :param str node_type: The node type to search for.
    :param list(str) nodes: Optional list of nodes to search through.
    :param int search_depth: The dag depth to find nodes of given type.
    :return: Returns the top level nodes for the given node type.
    :return: list(str)
    """
    # query the scene for nodes of the given type with expanded search kwargs
    # defaults to using the ::* wildcard for nested reference filtering
    search_kwargs = dict(typ=node_type, long=True, dag=True, **kwargs)
    nodes_to_search = cmds.ls(nodes or "::*", **search_kwargs)

    # convert 0 to None for list slicing and convert 1 to 2 for dag root "|"
    search_depth = search_depth or None
    search_depth = 2 if search_depth == 1 else search_depth

    def _get_root_node_of_type(node_path):
        """
        Find the node in the given node path that matches the given type.

        :param str node_path: Full path to a node to search.
        :return: Returns the full path to the node of given type.
        """
        # split on the "|" and slice the list to the set search depth
        # the first element will be an empty sting but is needed for rebuilding
        # the dag path when the join method is ran i.e., "|node|dag|path" vs
        # "node|dag|path", the latter being invalid without the trailing "|"
        node_hierarchy = node_path.split("|")[:search_depth]

        # set enumerate to start on 1 so the node index is the joint
        # node not it's parent node in the hierarchy and return the joined
        # dag path on the first occurrence of a node in the hierarchy that
        # matches the given node type
        for node_index, node in enumerate(node_hierarchy, 1):
            if node and cmds.nodeType(node) == node_type:
                
                # return the full dag path to the matching node
                return "|".join(node_hierarchy[:node_index])

    # use map built-in method for iteration speed
    nodes_map = map(_get_root_node_of_type, nodes_to_search)

    # use set and filter built-ins to return a flattened sparse list of all 
    # found root nodes of the given node type in the set search depth
    return list(filter(None, set(nodes_map)))
