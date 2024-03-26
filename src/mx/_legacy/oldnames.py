#
# ----------------------------------------------------------------------------------------------------
#
# Copyright (c) 2023, 2024, Oracle and/or its affiliates. All rights reserved.
# DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
#
# This code is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 only, as
# published by the Free Software Foundation.
#
# This code is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# version 2 for more details (a copy is included in the LICENSE file that
# accompanied this code).
#
# You should have received a copy of the GNU General Public License version
# 2 along with this work; if not, write to the Free Software Foundation,
# Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Please contact Oracle, 500 Oracle Parkway, Redwood Shores, CA 94065 USA
# or visit www.oracle.com if you need additional information or have any
# questions.
#
# ----------------------------------------------------------------------------------------------------
"""
Implements intercepting logic for proxy files.

.. seealso:: :func:`redirect`
"""

from __future__ import annotations
import atexit
import sys
import traceback
from types import ModuleType
from typing import List, Optional

from .._impl import mx

# Stores accesses to internal symbols
_internal_accesses = set()
# Whether an exit handler was already installed
_exit_handler_set = False


class ModuleInterceptor:
    def __init__(self, thisname, targetname, allowed_internal_reads, allowed_writes=None):
        """
        This class mimics a python module and intercepts all accesses, that's why we have to access our instance fields
        through ``__dict__``.
        """
        allowed_internal_reads = allowed_internal_reads or []
        allowed_writes = allowed_writes or []
        this_module = sys.modules[thisname]
        target_module = sys.modules[targetname]

        self.__dict__["_thisname"] = thisname
        self.__dict__["_allowed_internal_reads"] = allowed_internal_reads
        self.__dict__["_allowed_writes"] = allowed_writes
        self.__dict__["_this_module"] = this_module
        self.__dict__["_target_module"] = target_module
        # Set of names for which reads should be redirected to the target module
        # Only symbols exported by the module and the allowed internal reads are redirected, everything else does not
        # need to be (such accesses shouldn't happen in the first place, since they either access non-exported symbols
        # or indirect imports).
        self.__dict__["_redirected_reads"] = set(target_module.__all__ + allowed_internal_reads)
        # Set of names for which writes should be redirected to the target module
        self.__dict__["_redirected_writes"] = set(allowed_writes)

    def _get_target(self, name, is_set: bool) -> ModuleType:
        """
        Logic how a given access is redirected.

        Accesses are either not redirected (returns ``_thismdoule``, the proxy module that created the interceptor) or
        redirected to ``_target_module``, the module that is being proxied.

        Proxying is important to ensure changes to global variables are observed correctly.
        If client code changes a global variable in mx, that write should happen in the module where the symbol was
        defined and not in the proxy, otherwise internal code may not see the write.
        If mx code changes a global variable, client code accessing that variable through a proxy should read the
        updated value, so such accesses need to be redirected to the original module.

        :param name: The name of the symbol being accessed
        :param is_set: Whether this access is a set (True) or a get (False)
        :return: The python module on which this access should be performed on
        """
        mem_name = f"{self.__dict__['_thisname']}.{name}"

        # We do not treat double underscore symbols (dunders) as internal
        if name.startswith("_") and not name.startswith("__"):
            if not is_set and name not in self.__dict__["_allowed_internal_reads"]:
                mx.abort(f"Disallowed read of internal symbol detected: {mem_name}")

            _internal_accesses.add(mem_name)
            stack = traceback.extract_stack()
            mx.logv(f"Access to internal symbol detected ({'write' if is_set else 'read'}): {mem_name}")
            mx.logvv("".join(stack.format()))

        if is_set and name not in self.__dict__["_allowed_writes"]:
            mx.abort(f"Disallowed write to {mem_name}")

        if name in self.__dict__["_redirected_writes" if is_set else "_redirected_reads"]:
            return self.__dict__["_target_module"]
        else:
            return self.__dict__["_this_module"]

    def __setattr__(self, name, value):
        target = self._get_target(name, True)
        setattr(target, name, value)

    def __getattr__(self, name):
        target = self._get_target(name, False)
        return getattr(target, name)


def _exit_handler():
    if _internal_accesses:
        mx.logv(f"The following internal mx symbols were accessed: {', '.join(_internal_accesses)}")


def redirect(
    thisname: str, allowed_internal_reads: Optional[List[str]] = None, allowed_writes: Optional[List[str]] = None
):
    """
    Redirects attribute accesses on the ``thisname`` module to the ``mx._impl.{thisname}`` module.
    For the exact rules which accesses are redirected, see :class:`ModuleInterceptor`

    Produces warnings for accesses to internal symbols (which should not be accessed from the outside) that are not
    explicitly allowed in ``allowed_internal_reads``.

    Produces errors for writes to symbols (we should not rely on setting arbitrary symbols from the outside) that are
    not explicitly allowed in ``allowed_writes``.

    At the end (using an exit handler :func:_exit_handler:), the final list of these symbols is printed.

    :param: allowed_writes: List of symbols that are allowed to be set. All other assignments will produce an error.
    """
    global _exit_handler_set

    sys.modules[thisname] = ModuleInterceptor(thisname, "mx._impl." + thisname, allowed_internal_reads, allowed_writes)

    if not _exit_handler_set:
        atexit.register(_exit_handler)
        _exit_handler_set = True
