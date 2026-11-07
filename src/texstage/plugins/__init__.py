# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Operator-controlled, experimental extensions. No discovery at import time."""


class PluginError(ValueError):
    """A package, profile or plugin operation failed its contract."""

    def __init__(self, message, *, code="plugin"):
        super().__init__(message)
        self.code = code
