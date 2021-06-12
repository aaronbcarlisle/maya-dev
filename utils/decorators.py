from maya import cmds


def keep_selection(_function):
    """
    Maintains the selection from the beginning of the wrapped
    function and ensures it persists regardless of exception.

    :param callable _function: Function to wrap.
    :return: Returns the result of the wrapped function.
    :rtype: callable
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
    Wraps the decorated function in function in an undo chunk.

    :param callable _function: Function to wrap.
    :return: Returns the result of the wrapped function.
    :rtype: callable
    """
    def wrapper(*args, **kwargs):
        cmds.undoInfo(openChunk=True)
        try:
            function = _function(*args, **kwargs)
        finally:
            cmds.undoInfo(closeChunk=True)
        return function
    return wrapper
