# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2015 Scifabric LTD.
#
# PYBOSSA is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PYBOSSA is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with PYBOSSA.  If not, see <http://www.gnu.org/licenses/>.
"""
PYBOSSA main module.

This exports:
    * auth: for authorization methods
    * cache: for caching pages, and methods
    * view: for web front views

"""


# Patch boto v2 for Python 3.12+ compatibility.
# boto v2 uses 'imp' (removed in 3.12) and a broken vendored 'six'.
# This must run before any boto import.
import sys
import importlib
import importlib.util
import types

# Provide a shim for the removed 'imp' module that boto.plugin uses.
if 'imp' not in sys.modules:
    imp_shim = types.ModuleType('imp')
    imp_shim.find_module = lambda name, path=None: (None, None, None)
    imp_shim.load_module = lambda *args, **kwargs: None
    sys.modules['imp'] = imp_shim

# Patch boto's broken vendored six.
import six
import six.moves
import six.moves.urllib
import six.moves.urllib.parse
import six.moves.urllib.error
import six.moves.urllib.request
import queue
import http.client
sys.modules['boto.vendored.six'] = six
sys.modules['boto.vendored.six.moves'] = six.moves
sys.modules['boto.vendored.six.moves.urllib'] = six.moves.urllib
sys.modules['boto.vendored.six.moves.urllib.parse'] = six.moves.urllib.parse
sys.modules['boto.vendored.six.moves.urllib.error'] = six.moves.urllib.error
sys.modules['boto.vendored.six.moves.urllib.request'] = six.moves.urllib.request
sys.modules['boto.vendored.six.moves.queue'] = queue
sys.modules['boto.vendored.six.moves.http_client'] = http.client

__version__ = "2.9.2"  # pragma: no cover
