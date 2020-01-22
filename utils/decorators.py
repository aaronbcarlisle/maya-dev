from maya import cmds


def keep_selection(_function):
    """
    Keeps selection after method call.

    :param function _function: Function to wrap.
    :return: Returns the result of the wrapped function.
    :rtype: function
    """
    def wrapper(*args, **kwargs):
        selection = cmds.ls(selection=True)
        try:
            function = _function(*args, **kwargs)
        finally:
            cmds.select(selection, replace=True)
        return function
    return wrapper


def undo(_function):
    """
    Wraps the passed in function in an undo chunk.

    :param function _function: Function to wrap.
    :return: Returns the result of the wrapped function.
    :rtype: function
    """
    def wrapper(*args, **kwargs):
        cmds.undoInfo(openChunk=True)
        try:
            function = _function(*args, **kwargs)
        finally:
            cmds.undoInfo(closeChunk=True)
        return function
    return wrapper
