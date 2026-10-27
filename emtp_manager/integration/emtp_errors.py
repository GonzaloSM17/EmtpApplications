"""Errors shared by COM launch and EMTP session management."""


class EmtpLaunchError(RuntimeError):
    """EMTP activation failed; validate EMTP before starting another workflow."""
