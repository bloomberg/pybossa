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
"""Static tripwires for project response filtering and task-run identity.

These run without Postgres or Redis. Tripwires, not proofs; the behavioural
tests are in test_project_response_credentials.py.
"""
import ast
import pathlib

PYBOSSA_ROOT = pathlib.Path(__file__).resolve().parent.parent / 'pybossa'


def _class(relpath, name):
    tree = ast.parse((PYBOSSA_ROOT / relpath).read_text(errors='replace'))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in {relpath}")


def _method(relpath, cls, name):
    for sub in _class(relpath, cls).body:
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and sub.name == name:
            return sub
    raise AssertionError(f"{cls}.{name} not found in {relpath}")


def test_private_keys_is_actually_consumed():
    """private_keys was declared and never read - a dead allowlist."""
    src = (PYBOSSA_ROOT / 'api/project.py').read_text()
    assert src.count('private_keys') >= 2, (
        "ProjectAPI.private_keys is declared but never read. It is supposed to "
        "strip secret_key from responses.")


def test_select_attributes_strips_credentials_for_non_owners():
    src = ast.unparse(_method('api/project.py', 'ProjectAPI',
                              '_select_attributes'))
    assert '_strip_project_credentials' in src, (
        "ProjectAPI._select_attributes returns the full record to any "
        "subadmin, including secret_key and info['passwd_hash']")
    assert 'owners_ids' in src


def test_stripper_removes_secret_key_and_passwd_hash():
    src = ast.unparse(_method('api/project.py', 'ProjectAPI',
                              '_strip_project_credentials'))
    assert 'private_keys' in src, "stripper must consume the private_keys set"
    assert 'passwd_hash' in src, "stripper must remove info['passwd_hash']"


def test_add_user_info_clears_user_ip_for_authenticated_users():
    """The authenticated branch must discard any caller-supplied user_ip.

    TaskRunAuth._create counts rows matching
    (project_id, task_id, user_id, user_ip, external_uid) to decide whether a
    submission is a duplicate. user_ip arrives from the request body, so a
    different fake value on each POST made that count zero every time and let
    one worker fill every redundancy slot on a task.
    """
    node = _method('api/task_run.py', 'TaskRunAPI', '_add_user_info')
    src = ast.unparse(node)
    # The anonymous branch legitimately SETS user_ip from the request address;
    # the authenticated branch must clear it.
    assert 'taskrun.user_ip = None' in src, (
        "_add_user_info never clears user_ip - the duplicate gate stays open")
    # Assert specifically on the authenticated branch, not just the file.
    authenticated_branch = None
    for outer in ast.walk(node):
        if isinstance(outer, ast.If):
            for inner in ast.walk(outer):
                if isinstance(inner, ast.If) and 'is_anonymous' in ast.unparse(inner.test):
                    authenticated_branch = inner.orelse
    assert authenticated_branch is not None, \
        "could not locate the is_anonymous branch"
    branch_src = '\n'.join(ast.unparse(s) for s in authenticated_branch)
    assert 'user_id' in branch_src
    assert 'taskrun.user_ip = None' in branch_src, (
        "the authenticated branch sets user_id but leaves the caller-supplied "
        f"user_ip in place. Branch body:\n{branch_src}")
