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
"""Static tripwires for API object authorization.

These parse the source with ast rather than booting the app, so they run
without Postgres or Redis. They are a REGRESSION TRIPWIRE, not a proof of
correctness - they assert that the specific guard removed by each finding is
still present. The behavioural proof lives in test_api_object_authorization.py, which
needs a database.

Kept deliberately narrow: each one names the function it guards, so a rename
fails loudly rather than passing vacuously.
"""
import ast
import pathlib

PYBOSSA_ROOT = pathlib.Path(__file__).resolve().parent.parent / 'pybossa'


def _function(relpath, name, cls=None):
    """Return the ast node for a named function, failing loudly if absent."""
    tree = ast.parse((PYBOSSA_ROOT / relpath).read_text(errors='replace'))
    if cls:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == cls:
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                            and sub.name == name:
                        return sub
        raise AssertionError(f"{cls}.{name} not found in {relpath}")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {relpath}")


def _src(node):
    return ast.unparse(node)


def test_newtask_checks_project_id():
    """The cherry-pick branch must compare the task's project to the URL's."""
    node = _function('sched.py', 'template_get_locked_task')
    src = _src(node)
    assert 'task.project_id' in src, (
        "sched.py cherry-pick branch no longer compares task.project_id - "
        "any project becomes a conduit to read tasks from any other")


def test_favorites_does_not_dictize_unfiltered():
    """No request handler may serialise a raw task.dictize().

    Checks the handlers only - _sanitized() legitimately calls task.dictize()
    on its way into apply_access_control.
    """
    offenders = []
    for handler in ('get', 'post', 'delete'):
        src = _src(_function('api/favorites.py', handler, cls='FavoritesAPI'))
        if 'json.dumps(task.dictize())' in src:
            offenders.append(handler)
    assert not offenders, (
        f"FavoritesAPI.{'/'.join(offenders)} serialise a raw task.dictize() - "
        "use self._sanitized(task)")


def test_favorites_reauthorize_every_mutation():
    for handler in ('post', 'delete'):
        node = _function('api/favorites.py', handler, cls='FavoritesAPI')
        try_body = next(item.body for item in node.body
                        if isinstance(item, ast.Try))
        guards = [item for item in try_body if isinstance(item, ast.Expr)
                  and '_ensure_can_read_task' in ast.unparse(item)]
        assert len(guards) == 1, (
            'FavoritesAPI.%s must reauthorize every response path' % handler)


def test_favorites_has_select_attributes():
    """Covers the GET path, which goes through _create_dict_from_model."""
    _function('api/favorites.py', '_select_attributes', cls='FavoritesAPI')


def test_related_embeds_are_authorized():
    """Every embed inside related=1 must be gated on is_authorized."""
    node = _function('api/api_base.py', '_add_hateoas_links')
    src = _src(node)
    assert src.count('is_authorized') >= 6, (
        "_add_hateoas_links has fewer is_authorized guards than embeds; "
        f"found {src.count('is_authorized')}, expected one per embed")
    assert 'tr.dictize()' in src and 'is_authorized' in src


def test_embedded_task_applies_access_control():
    """is_authorized alone is insufficient for Tasks - TaskAuth._read is
    merely is_authenticated, so gold_answers would still be emitted."""
    node = _function('api/api_base.py', '_embedded_task_dict')
    assert 'apply_access_control' in _src(node)
    outer = _src(_function('api/api_base.py', '_add_hateoas_links'))
    assert 't.dictize()' not in outer, (
        "_add_hateoas_links embeds a raw t.dictize(); use _embedded_task_dict")


def test_gold_answers_are_gated():
    """The gold-answer injection must be behind an authorization check."""
    node = _function('api/task_run.py', '_customize_response_dict',
                     cls='TaskRunAPI')
    src = _src(node)
    assert '_only_admin_or_subadminowners' in src, (
        "gold_answers injection is no longer gated - every worker's submission "
        "response would carry the answer key for gold quality probes")
    # The assignment must be inside a conditional, not at statement level.
    assigns_at_top = [s for s in node.body
                      if isinstance(s, ast.Assign)
                      and 'gold_answers' in ast.unparse(s)]
    assert not assigns_at_top, (
        "gold_answers is assigned unconditionally in _customize_response_dict")
