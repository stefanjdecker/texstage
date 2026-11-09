# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""For the pool's tests (tests/test_pool.py): a worker that imports this module before it is ready ends, as
one whose start goes wrong would. Nothing else imports it."""
import os

os._exit(3)
