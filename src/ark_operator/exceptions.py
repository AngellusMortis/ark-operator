"""ARK Operator exceptions."""


class SynchronousOnlyOperationError(RuntimeError):
    """Code can only be ran inside of executor thread."""


class AsynchronousOnlyOperationError(RuntimeError):
    """Code can only be ran inside of event loop."""


class SteamCMDError(RuntimeError):
    """Except running steamcmd."""
