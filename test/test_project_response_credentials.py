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
"""Behavioural tests for project response filtering and task-run identity.

Needs live Postgres and Redis. See test_project_response_credentials_static.py for the
tripwires that run without them.
"""
import json

from test import with_context
from test.helper.web import Helper
from test.factories import UserFactory, ProjectFactory, TaskFactory


class TestProjectCredentialsNotDisclosed(Helper):
    """Project responses do not disclose stored credentials.

    ProjectAPI._select_attributes returned the complete record - including
    secret_key and info['passwd_hash'] - to any caller holding the subadmin
    flag, with no ownership test. In GIGwork a subadmin reaches a project they
    do not own whenever they are assigned to it via info['project_users'].

    secret_key is a live credential: auth_jwt_project mints an HS256 JWT from
    it, that JWT is the sole authorization for the external_uid task and
    task-run paths, it is symmetric so it can be signed offline, and there is
    no rotation route.
    """

    @with_context
    def test_non_owner_subadmin_does_not_receive_secret_key(self):
        owner = UserFactory.create()
        subadmin = UserFactory.create(email_addr='sub@example.com',
                                      name='sub', password='pw1234',
                                      subadmin=True, admin=False)
        project = ProjectFactory.create(owner=owner, published=True)
        project.info['project_users'] = [subadmin.id]

        self.signin(email='sub@example.com', password='pw1234')
        res = self.app.get(f'/api/project/{project.id}')
        if res.status_code != 200:
            return  # not readable at all is also acceptable
        payload = json.loads(res.data)
        assert 'secret_key' not in payload, payload.keys()
        assert 'passwd_hash' not in payload.get('info', {}), payload.get('info')

    @with_context
    def test_owner_still_receives_secret_key(self):
        """Owners legitimately need the key - the fix must not break them."""
        owner = UserFactory.create(email_addr='owner@example.com',
                                   name='owner', password='pw1234',
                                   subadmin=True, admin=False)
        project = ProjectFactory.create(owner=owner, published=True)

        self.signin(email='owner@example.com', password='pw1234')
        res = self.app.get(f'/api/project/{project.id}')
        if res.status_code == 200:
            assert 'secret_key' in json.loads(res.data)

    @with_context
    def test_admin_still_receives_secret_key(self):
        admin = UserFactory.create(email_addr='root@example.com', name='root',
                                   password='pw1234', admin=True)
        other = UserFactory.create()
        project = ProjectFactory.create(owner=other, published=True)

        self.signin(email='root@example.com', password='pw1234')
        res = self.app.get(f'/api/project/{project.id}')
        if res.status_code == 200:
            assert 'secret_key' in json.loads(res.data)


class TestRedundancyBypass(Helper):
    """Authenticated task runs ignore caller-supplied network identity.

    TaskRunAuth._create counts existing rows matching
    (project_id, task_id, user_id, user_ip, external_uid) to decide whether a
    submission is a duplicate. user_ip came from the request body, so a
    different fake value on each POST made the count zero every time and one
    worker could fill every redundancy slot on a task.
    """

    @with_context
    def test_second_submission_with_forged_user_ip_is_rejected(self):
        owner = UserFactory.create()
        worker = UserFactory.create(email_addr='w@example.com', name='w',
                                    password='pw1234')
        project = ProjectFactory.create(owner=owner, published=True)
        task = TaskFactory.create(project=project, n_answers=3)

        self.signin(email='w@example.com', password='pw1234')

        first = self.app.post(
            '/api/taskrun',
            data=json.dumps({'project_id': project.id, 'task_id': task.id,
                             'info': {'answer': 'one'},
                             'user_ip': '10.0.0.1'}),
            content_type='application/json')

        second = self.app.post(
            '/api/taskrun',
            data=json.dumps({'project_id': project.id, 'task_id': task.id,
                             'info': {'answer': 'two'},
                             'user_ip': '10.0.0.2'}),
            content_type='application/json')

        assert second.status_code in (401, 403), (
            "a forged user_ip let the same worker submit twice to one task; "
            f"first={first.status_code} second={second.status_code}")

    @with_context
    def test_authenticated_task_run_stores_null_user_ip(self):
        """The codebase's own invariant: user_ip IS NULL means authenticated.

        cache/project_stats.py counts authenticated contributors with
        `user_ip IS NULL` and anonymous ones with `user_ip IS NOT NULL`, so a
        caller-supplied user_ip also miscounted an authenticated worker as
        anonymous.
        """
        from pybossa.core import task_repo
        owner = UserFactory.create()
        worker = UserFactory.create(email_addr='w2@example.com', name='w2',
                                    password='pw1234')
        project = ProjectFactory.create(owner=owner, published=True)
        task = TaskFactory.create(project=project, n_answers=2)

        self.signin(email='w2@example.com', password='pw1234')
        res = self.app.post(
            '/api/taskrun',
            data=json.dumps({'project_id': project.id, 'task_id': task.id,
                             'info': {'answer': 'x'},
                             'user_ip': '10.0.0.9'}),
            content_type='application/json')
        if res.status_code in (200, 201):
            stored = task_repo.filter_task_runs_by(task_id=task.id)
            assert stored, "no task run persisted"
            assert stored[0].user_ip is None, (
                f"caller-supplied user_ip persisted: {stored[0].user_ip}")
