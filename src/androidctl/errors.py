"""Stable process exit codes (see docs/instances.md)."""


class Error(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code
