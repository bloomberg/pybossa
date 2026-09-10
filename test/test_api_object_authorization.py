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
"""Behavioural regression tests for API object authorization.

API routes that never call ensure_authorized_to('read',
project). In GIGwork that check is the ONLY enforcement of data classification -
data_access_levels is truthy, so ProjectAuth._read requires project_users
membership - and these four paths skipped it.

These tests need live Postgres and Redis. See test_api_authorization_structure.py
for the tripwires that run without them.
"""
import json

from test import with_context
from test.helper.web import Helper
from test.factories import (UserFactory, ProjectFactory, TaskFactory,
                            TaskRunFactory)
from pybossa.core import project_repo, task_repo, user_repo


def password_user(email_addr, name):
    user = UserFactory.create(email_addr=email_addr, name=name)
    user.set_password('pw1234')
    user_repo.save(user)
    return user


class TestNewtaskCrossProject(Helper):
    """A requested task must belong to the project in the route.

    The scheduler's cherry-pick branch fetched by primary key and returned the
    task before any project check, so any reachable task_queue project acted as
    a conduit to read tasks from projects the caller has no membership in.
    """

    @with_context
    def test_task_id_from_another_project_is_not_returned(self):
        owner = UserFactory.create()
        attacker = password_user('attacker@example.com', 'attacker')
        conduit = ProjectFactory.create(owner=owner, published=True,
                                        info={'sched': 'task_queue'})
        victim = ProjectFactory.create(owner=owner, published=True)
        victim_task = TaskFactory.create(project=victim,
                                         info={'secret': 'other project data'})

        self.signin(email='attacker@example.com', password='pw1234')
        self.set_proj_passwd_cookie(conduit, attacker)
        res = self.app.get(
            f'/api/project/{conduit.id}/newtask/{victim_task.id}')
        body = res.data.decode()
        assert 'other project data' not in body, (
            "cross-project task leaked through the cherry-pick branch")

    @with_context
    def test_task_id_from_the_same_project_still_works(self):
        """The guard must not break legitimate cherry-pick."""
        owner = UserFactory.create()
        worker = password_user('worker@example.com', 'worker')
        project = ProjectFactory.create(owner=owner, published=True,
                                        info={'sched': 'task_queue'})
        task = TaskFactory.create(project=project, info={'q': 'own project'})

        self.signin(email='worker@example.com', password='pw1234')
        self.set_proj_passwd_cookie(project, worker)
        res = self.app.get(f'/api/project/{project.id}/newtask/{task.id}')
        assert res.status_code == 200, res.status_code


class TestFavoritesAuthorization(Helper):
    """Favorite mutations must reauthorize each task.

    POST /api/favorites took any task id, appended the caller to fav_user_ids
    and returned the whole task. Task ids are sequential.
    """

    def _signin_with_csrf(self, email_addr):
        csrf = self.get_csrf('/account/signin')
        self.signin(email=email_addr, password='pw1234', csrf=csrf)
        return {'X-CSRFToken': csrf}

    @with_context
    def test_cannot_favorite_a_task_in_a_project_you_cannot_read(self):
        owner = UserFactory.create()
        outsider = password_user('outsider@example.com', 'outsider')
        project = ProjectFactory.create(
            owner=owner, published=True, info={'passwd_hash': None})
        task = TaskFactory.create(project=project,
                                  info={'secret': 'restricted content'})

        headers = self._signin_with_csrf('outsider@example.com')
        res = self.app.post('/api/favorites',
                            data=json.dumps({'task_id': task.id}),
                            content_type='application/json', headers=headers)
        assert res.status_code in (401, 403), res.status_code
        assert 'restricted content' not in res.data.decode()

    @with_context
    def test_favorite_response_omits_gold_answers_and_calibration(self):
        """Even for an authorized caller the response must be sanitised."""
        owner = UserFactory.create()
        worker = password_user('w2@example.com', 'w2')
        project = ProjectFactory.create(
            owner=owner, published=True,
            info={'passwd_hash': None, 'project_users': [worker.id]})
        task = TaskFactory.create(project=project, calibration=1,
                                  gold_answers={'answer': 'ground truth'})

        headers = self._signin_with_csrf('w2@example.com')
        res = self.app.post('/api/favorites',
                            data=json.dumps({'task_id': task.id}),
                            content_type='application/json', headers=headers)
        assert res.status_code == 200, res.status_code
        payload = json.loads(res.data)
        assert 'gold_answers' not in payload, payload
        assert 'calibration' not in payload, payload

    def _create_stale_favorite(self):
        owner = UserFactory.create()
        worker = password_user('stale@example.com', 'stale')
        project = ProjectFactory.create(
            owner=owner, published=True,
            info={'passwd_hash': None, 'project_users': [worker.id]})
        task = TaskFactory.create(
            project=project, info={'secret': 'revoked project data'})

        headers = self._signin_with_csrf('stale@example.com')
        response = self.app.post(
            '/api/favorites', data=json.dumps({'task_id': task.id}),
            content_type='application/json', headers=headers)
        assert response.status_code == 200, (
            response.status_code, response.data)

        project.info = dict(project.info, project_users=[])
        project_repo.update(project)
        return worker, task, headers

    @with_context
    def test_existing_favorite_is_omitted_from_get_after_access_revoked(self):
        _, task, headers = self._create_stale_favorite()

        response = self.app.get('/api/favorites', headers=headers)

        assert response.status_code == 200, response.status_code
        payload = json.loads(response.data)
        assert all(item['id'] != task.id for item in payload), payload
        assert 'revoked project data' not in response.data.decode()

    @with_context
    def test_existing_favorite_is_reauthorized_on_post(self):
        _, task, headers = self._create_stale_favorite()

        response = self.app.post(
            '/api/favorites', data=json.dumps({'task_id': task.id}),
            content_type='application/json', headers=headers)

        assert response.status_code in (401, 403), response.status_code
        assert 'revoked project data' not in response.data.decode()

    @with_context
    def test_existing_favorite_is_reauthorized_before_delete(self):
        worker, task, headers = self._create_stale_favorite()

        response = self.app.delete('/api/favorites/%s' % task.id,
                                   headers=headers)

        assert response.status_code in (401, 403), response.status_code
        favorite = task_repo.get_task_favorited(worker.id, task.id)
        assert len(favorite) == 1
        assert worker.id in favorite[0].fav_user_ids


class TestRelatedEmbedAuthorization(Helper):
    """Objects embedded by related=1 require their own checks.

    related=1 embedded task runs and results without re-checking, and all=1
    drops the owner scoping, making it instance-wide.
    """

    @with_context
    def test_related_does_not_embed_other_users_task_runs(self):
        owner = UserFactory.create()
        contributor = UserFactory.create()
        snooper = password_user('snoop@example.com', 'snoop')
        project = ProjectFactory.create(owner=owner, published=True)
        task = TaskFactory.create(project=project)
        TaskRunFactory.create(task=task, user=contributor,
                              info={'answer': 'private answer'})

        self.signin(email='snoop@example.com', password='pw1234')
        res = self.app.get('/api/task?related=True&all=1&limit=100')
        assert 'private answer' not in res.data.decode(), (
            "related=1 embedded another contributor's answer")

    @with_context
    def test_embedded_task_omits_gold_answers(self):
        """TaskAuth._read is just is_authenticated, so is_authorized alone is
        not enough for embedded Tasks - access control must be applied."""
        owner = UserFactory.create()
        contributor = password_user('c2@example.com', 'c2')
        project = ProjectFactory.create(owner=owner, published=True)
        task = TaskFactory.create(project=project, calibration=1,
                                  gold_answers={'answer': 'ground truth'})
        TaskRunFactory.create(task=task, user=contributor)

        self.signin(email='c2@example.com', password='pw1234')
        res = self.app.get('/api/taskrun?related=True&all=1')
        assert 'ground truth' not in res.data.decode(), (
            "embedded task carried gold_answers")


class TestTaskRunGoldAnswerDisclosure(Helper):
    """Gold answers are limited to project administrators.

    _customize_response_dict injected the task's gold answers into every
    task-run POST response, decrypting them from S3 in the process. Gold tasks
    are hidden quality probes reused across workers, so this handed the answer
    key to the people being measured.
    """

    @with_context
    def test_worker_post_response_has_no_gold_answers(self):
        owner = UserFactory.create()
        worker = password_user('w3@example.com', 'w3')
        project = ProjectFactory.create(owner=owner, published=True)
        task = TaskFactory.create(project=project, calibration=1,
                                  gold_answers={'answer': 'ground truth'})

        self.signin(email='w3@example.com', password='pw1234')
        res = self.app.post('/api/taskrun',
                            data=json.dumps({'project_id': project.id,
                                             'task_id': task.id,
                                             'info': {'answer': 'guess'}}),
                            content_type='application/json')
        body = res.data.decode()
        assert 'ground truth' not in body, (
            "gold answer disclosed in the task-run POST response")
        if res.status_code in (200, 201):
            assert 'gold_answers' not in json.loads(body)
