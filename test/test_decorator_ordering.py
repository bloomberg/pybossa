# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2026 Scifabric LTD.
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
"""Structural guard for decorator ordering.

Python applies decorators bottom-up, and
Flask's ``route`` is not a wrapper - it registers the function it is handed and
returns that same function. So when ``@blueprint.route`` is the innermost
decorator, the RAW function is what lands in the URL map and every decorator
written above it is dead code. That silently disabled ``@admin_required`` on
/api/verify and ``@login_required`` on the attachment download endpoint, plus
seven more instances that were not ticketed.

This test is deliberately static - it parses the source rather than booting the
app - so it runs without Postgres or Redis and cannot be skipped by an
environment problem. It guards the whole tree, not just the ten sites fixed at
the time of writing, so a newly added misordered route fails here.
"""
import ast
import pathlib

PYBOSSA_ROOT = pathlib.Path(__file__).resolve().parent.parent / 'pybossa'

# Decorators that grant or deny access. Inert here means an open endpoint.
SECURITY_DECORATORS = {
    'login_required',
    'admin_required',
    'admin_or_subadmin_required',
    'admin_or_project_owner',
}

# Decorators that are inert today and MUST STAY inert or be deleted. Activating
# these by "correcting" the ordering opens a hole rather than closing one:
#   jsonpify   - emits callback(<body>) for ?callback=, a cross-origin read
#                primitive that ignores CORS
#   crossdomain - sets Access-Control-Allow-Origin: * , on state-changing POSTs
#                including bulk task delete. Prod sets CORS_RESOURCES = {}
#                precisely to keep cross-origin access shut.
MUST_NOT_ACTIVATE = {'jsonpify', 'crossdomain'}


def _decorator_name(node):
    """Return the bare name of a decorator node, or None."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_route(node):
    """True for @<something>.route(...)."""
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'route')


def _iter_routed_functions():
    """Yield (path, function name, line, names above the first route)."""
    for path in sorted(PYBOSSA_ROOT.rglob('*.py')):
        try:
            tree = ast.parse(path.read_text(errors='replace'))
        except SyntaxError:                                  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decs = node.decorator_list
            route_positions = [i for i, d in enumerate(decs) if _is_route(d)]
            if not route_positions:
                continue
            # decorator_list is source order, top first
            above = [_decorator_name(d) for d in decs[:min(route_positions)]]
            yield path, node.name, node.lineno, [a for a in above if a]


def test_no_security_decorator_above_a_route():
    """A security decorator above @route never runs. The endpoint is open."""
    offenders = []
    for path, func, lineno, above in _iter_routed_functions():
        inert = SECURITY_DECORATORS.intersection(above)
        if inert:
            rel = path.relative_to(PYBOSSA_ROOT.parent)
            offenders.append(f"{rel}:{lineno} {func}() -> inert {sorted(inert)}")
    assert not offenders, (
        "Security decorators are above @route and therefore never execute. "
        "Move @route to the top of the stack:\n  " + "\n  ".join(offenders))


def test_jsonpify_and_crossdomain_are_not_activated_by_a_route_move():
    """These must be deleted, never reordered.

    They sit inert above @route in the pre-fix tree. Hoisting the route without
    deleting them would switch JSONP on across the API and add
    Access-Control-Allow-Origin: * to bulk task deletion.
    """
    offenders = []
    for path, func, lineno, above in _iter_routed_functions():
        found = MUST_NOT_ACTIVATE.intersection(above)
        if found:
            rel = path.relative_to(PYBOSSA_ROOT.parent)
            offenders.append(f"{rel}:{lineno} {func}() -> {sorted(found)}")
    assert not offenders, (
        "jsonpify/crossdomain sit above @route. DELETE them - do not reorder, "
        "that would activate them:\n  " + "\n  ".join(offenders))


def test_nothing_at_all_sits_above_a_route():
    """Catch-all. Any decorator above @route is dead code and misleading.

    csrf.exempt is the one benign case - exemption is recorded by name and
    survives either ordering - but leaving it above the route still reads as if
    ordering matters, so the tree is kept uniformly route-first.
    """
    offenders = []
    for path, func, lineno, above in _iter_routed_functions():
        if above:
            rel = path.relative_to(PYBOSSA_ROOT.parent)
            offenders.append(f"{rel}:{lineno} {func}() -> {above}")
    assert not offenders, (
        "Decorators above @route are never applied to the registered view:\n  "
        + "\n  ".join(offenders))


def _assert_named_endpoint_has_route_first(relpath, func):
    """The nine endpoints whose authentication was inert before this change."""
    for path, name, _lineno, above in _iter_routed_functions():
        if name == func and str(path).endswith(relpath.split('/', 1)[1]):
            assert not above, (
                f"{relpath} {func}(): {above} sit above @route and will not run")
            return
    raise AssertionError(f"{func} not found as a routed view in {relpath}")


def test_named_endpoints_have_route_first():
    for relpath, func in (
        ('pybossa/api/__init__.py', 'verify_operations'),
        ('pybossa/view/attachment.py', 'download_attachment'),
        ('pybossa/api/__init__.py', 'get_user_preferences'),
        ('pybossa/api/__init__.py', 'update_user_preferences'),
        ('pybossa/api/__init__.py', 'release_category_locks'),
        ('pybossa/api/__init__.py', 'get_service_request'),
        ('pybossa/api/__init__.py', 'assign_task'),
        ('pybossa/api/__init__.py', 'partial_answer'),
        ('pybossa/api/__init__.py', 'user_has_partial_answer'),
    ):
        _assert_named_endpoint_has_route_first(relpath, func)
