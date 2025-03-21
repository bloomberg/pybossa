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
import json
from unittest.mock import patch, call

from nose.tools import assert_equal

from pybossa.api.task import TaskAPI
from pybossa.repositories import ProjectRepository
from pybossa.repositories import ResultRepository
from pybossa.repositories import TaskRepository
from test import db, with_context
from test.factories import ExternalUidTaskRunFactory
from test.factories import ProjectFactory, TaskFactory, TaskRunFactory, \
    UserFactory
from test.helper.gig_helper import make_subadmin, make_admin
from test.test_api import TestAPI
import hashlib

project_repo = ProjectRepository(db)
task_repo = TaskRepository(db)
result_repo = ResultRepository(db)


class TestTaskAPI(TestAPI):

    def create_result(self, n_results=1, n_answers=1, owner=None,
                      filter_by=False):
        if owner:
            owner = owner
        else:
            admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        tasks = []
        for i in range(n_results):
            tasks.append(TaskFactory.create(n_answers=n_answers,
                                            project=project))
        for i in range(n_answers):
            for task in tasks:
                TaskRunFactory.create(task=task, project=project)
        if filter_by:
            return result_repo.filter_by(project_id=1)
        else:
            return result_repo.get_by(project_id=1)

    @with_context
    @patch('pybossa.api.task.TaskAPI._verify_auth')
    def test_task_query_list_project_ids(self, auth):
        """Get a list of tasks using a list of project_ids."""
        auth.return_value = True
        projects = ProjectFactory.create_batch(3)
        tasks = []
        for project in projects:
            tmp = TaskFactory.create_batch(2, project=project)
            for t in tmp:
                tasks.append(t)

        user = UserFactory.create()
        project_ids = [project.id for project in projects]
        url = '/api/task?all=1&project_id=%s&limit=100&api_key=%s' % (project_ids, user.api_key)
        res = self.app.get(url)
        data = json.loads(res.data)
        assert len(data) == 3 * 2, len(data)
        for task in data:
            assert task['project_id'] in project_ids
        task_project_ids = list(set([task['project_id'] for task in data]))
        assert sorted(project_ids) == sorted(task_project_ids)

        # more filters
        res = self.app.get(url + '&orderby=created&desc=true')
        data = json.loads(res.data)
        assert data[0]['id'] == tasks[-1].id

        task_orig = tasks[0]
        task_run = TaskRunFactory.create(task=task_orig, user=user)

        project_ids = [project.id for project in projects]
        url = '/api/task?project_id=%s&limit=100&participated=true&api_key=%s' % (project_ids, user.api_key)
        res = self.app.get(url)
        data = json.loads(res.data)
        assert len(data) == (3 * 2) - 1, len(data)
        for task in data:
            assert task['project_id'] in project_ids
        task_project_ids = list(set([task['project_id'] for task in data]))
        assert sorted(project_ids) == sorted(task_project_ids)
        task_ids = [task['id'] for task in data]
        err_msg = 'This task should not be in the list as the user participated.'
        assert task_orig.id not in task_ids, err_msg

    @with_context
    @patch('pybossa.api.task.TaskAPI._verify_auth')
    def test_task_query_participated_user_ip(self, auth):
        """Test API Task query with participated arg user_ip."""
        auth.return_value = True
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        tasks1 = TaskFactory.create_batch(10, project=project,
                                         info=dict(foo='fox'))
        tasks2 = TaskFactory.create_batch(10, project=project,
                                         info=dict(foo='dog'))
        tasks = tasks1 + tasks2
        TaskRunFactory.create(task=tasks[0], user=user)
        TaskRunFactory.create(task=tasks[1], user=user)
        TaskRunFactory.create(task=tasks[2], user=user)

        url = '/api/task?participated=1&api_key=' + user.api_key

        res = self.app.get(url)
        data = json.loads(res.data)
        assert len(data) == 17, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # limit & offset
        url = '/api/task?participated=1&all=1&limit=10&offset=10&api_key=' + user.api_key

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 7, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # last_id
        url = '/api/task?participated=1&all=1&last_id=%s&api_key=%s' % (tasks[0].id, user.api_key)

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 17, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # orderby & desc
        url = '/api/task?participated=1&all=1&orderby=created&desc=1&api_key=' + user.api_key

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 17, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        assert data[0]['id'] == tasks[-1].id

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # info & fulltextsearch
        url = '/api/task?participated=1&all=1&orderby=created&desc=1&info=foo::fox&fulltextsearch=1&api_key=' + user.api_key

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 7, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        assert data[0]['id'] == tasks1[-1].id

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

    @with_context
    @patch('pybossa.api.task.TaskAPI._verify_auth')
    def test_task_query_participated_external_uid(self, auth):
        """Test API Task query with participated arg external_uid."""
        auth.return_value = True
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        tasks1 = TaskFactory.create_batch(10, project=project,
                                         info=dict(foo='fox'))
        tasks2 = TaskFactory.create_batch(10, project=project,
                                         info=dict(foo='dog'))
        tasks = tasks1 + tasks2
        ExternalUidTaskRunFactory.create(task=tasks[0])
        ExternalUidTaskRunFactory.create(task=tasks[1])
        ExternalUidTaskRunFactory.create(task=tasks[2])

        url = '/api/task?participated=1&all=1&external_uid=1xa'

        res = self.app.get(url)
        res.status_code == 401, "unauthenticated users are not authorized to access task"
        return
        data = json.loads(res.data)

        assert len(data) == 17, data
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # limit & offset
        url = '/api/task?participated=1&all=1&limit=10&offset=10&external_uid=1xa'

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 7, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # last_id
        url = '/api/task?external_uid=1xa&participated=1&all=1&last_id=%s' % (tasks[0].id)

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 17, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # orderby & desc
        url = '/api/task?external_uid=1x&participated=1&all=1&orderby=created&desc=1'

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 17, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        assert data[0]['id'] == tasks[-1].id

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # info & fulltextsearch
        url = '/api/task?external_uid=1xa&participated=1&all=1&orderby=created&desc=1&info=foo::fox&fulltextsearch=1'

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 7, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        assert data[0]['id'] == tasks1[-1].id

        for task in data:
            assert task['id'] not in participated_tasks, task['id']


    @with_context
    def test_task_query_participated(self):
        """Test API Task query with participated arg."""
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        tasks1 = TaskFactory.create_batch(10, project=project,
                                         info=dict(foo='fox'))
        tasks2 = TaskFactory.create_batch(10, project=project,
                                         info=dict(foo='dog'))
        tasks = tasks1 + tasks2
        TaskRunFactory.create(task=tasks[0], user=user)
        TaskRunFactory.create(task=tasks[1], user=user)
        TaskRunFactory.create(task=tasks[2], user=user)

        url = '/api/task?api_key=%s&participated=1&all=1' % user.api_key

        self.set_proj_passwd_cookie(project, user)
        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 17, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # limit & offset
        url = '/api/task?api_key=%s&participated=1&all=1&limit=10&offset=10' % user.api_key

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 7, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # last_id
        url = '/api/task?api_key=%s&participated=1&all=1&last_id=%s' % (user.api_key, tasks[0].id)

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 17, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # orderby & desc
        url = '/api/task?api_key=%s&participated=1&all=1&orderby=created&desc=1' % user.api_key

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 17, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        assert data[0]['id'] == tasks[-1].id

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

        # info & fulltextsearch
        url = '/api/task?api_key=%s&participated=1&all=1&orderby=created&desc=1&info=foo::fox&fulltextsearch=1' % user.api_key

        res = self.app.get(url)
        data = json.loads(res.data)

        assert len(data) == 7, len(data)
        participated_tasks = [tasks[0].id, tasks[1].id, tasks[2].id]

        assert data[0]['id'] == tasks1[-1].id

        for task in data:
            assert task['id'] not in participated_tasks, task['id']

    @with_context
    @patch('pybossa.api.task.TaskAPI._verify_auth')
    def test_task_query_without_params(self, auth):
        """ Test API Task query"""
        auth.return_value = True
        project = ProjectFactory.create()
        t1 = TaskFactory.create(created='2015-01-01T14:37:30.642119', info={'question': 'answer'})
        tasks = TaskFactory.create_batch(8, project=project, info={'question': 'answer'})
        t2 = TaskFactory.create(created='2019-01-01T14:37:30.642119',
                                info={'question': 'answer'},
                                fav_user_ids=[1,2,3,4])

        t3 = TaskFactory.create(created='2018-01-01T14:37:30.642119',
                                info={'question': 'answer'},
                                fav_user_ids=[1,2])
        user = UserFactory.create()

        tasks.insert(0, t1)
        tasks.append(t2)
        tasks.append(t3)

        res = self.app.get('/api/task?all=1&api_key=' + user.api_key)
        tasks = json.loads(res.data)
        assert len(tasks) == 11, tasks
        task = tasks[0]
        assert task['info']['question'] == 'answer', task


        # The output should have a mime-type: application/json
        assert res.mimetype == 'application/json', res

        # Desc filter
        url = '/api/task?desc=true&all=1&api_key=' + user.api_key
        res = self.app.get(url)
        data = json.loads(res.data)
        err_msg = "It should get the last item first."
        assert data[0]['created'] == tasks[len(tasks)-1]['created'], err_msg

        # Desc filter
        url = '/api/task?orderby=wrongattribute&all=1&api_key=' + user.api_key
        res = self.app.get(url)
        data = json.loads(res.data)
        err_msg = "It should be 415."
        assert data['status'] == 'failed', data
        assert data['status_code'] == 415, data
        assert 'has no attribute' in data['exception_msg'], data

        # Desc filter
        url = '/api/task?orderby=id&all=1&api_key=' + user.api_key
        res = self.app.get(url)
        data = json.loads(res.data)
        err_msg = "It should get the last item first."
        tasks_by_id = sorted(tasks, key=lambda x: x['id'], reverse=False)
        i = 0
        for t in tasks_by_id:
            assert tasks_by_id[i]['id'] == data[i]['id']
            i += 1

        # Desc filter
        url = '/api/task?orderby=id&desc=true&all=1&api_key=' + user.api_key
        res = self.app.get(url)
        data = json.loads(res.data)
        err_msg = "It should get the last item first."
        tasks_by_id = sorted(tasks, key=lambda x: x['id'], reverse=True)
        i = 0
        for t in tasks_by_id:
            assert tasks_by_id[i]['id'] == data[i]['id']
            i += 1

        # fav_user_ids
        url = '/api/task?orderby=fav_user_ids&desc=true&all=1&api_key=' + user.api_key
        res = self.app.get(url)
        data = json.loads(res.data)
        err_msg = "It should get the last item first."
        # print data
        assert data[0]['id'] == t2.id, err_msg

        # fav_user_ids
        url = '/api/task?orderby=fav_user_ids&desc=true&limit=1&offset=1&all=1&api_key=' + user.api_key
        res = self.app.get(url)
        data = json.loads(res.data)
        err_msg = "It should get the last item first."
        assert data[0]['id'] == t3.id, err_msg
        url = '/api/task?orderby=fav_user_ids&desc=true&limit=1&offset=2&all=1&api_key=' + user.api_key
        res = self.app.get(url)
        data = json.loads(res.data)
        err_msg = "It should get the last item first."
        assert data[0]['id'] == tasks[2]['id'], err_msg

        # Related
        taskruns = TaskRunFactory.create_batch(8, project=project, task=t2)
        res = self.app.get('/api/task?id=' + str(t2.id) + '&related=True&all=1&api_key=' + user.api_key)
        data = json.loads(res.data)
        task = data[0]
        assert task['info']['question'] == 'answer', task
        assert len(task['task_runs']) == 8, task
        assert len(task['task_runs']) == len(taskruns), task
        assert task['result'] == None, task

        # Stats
        res = self.app.get('/api/task?limit=1&all=1&stats=True&api_key=' + user.api_key)
        data = json.loads(res.data)
        assert len(data) == 1, data
        assert 'stats' not in data[0].keys()

    @with_context
    def test_task_query_without_params_with_context(self):
        """ Test API Task query with context"""
        user = UserFactory.create()
        project_oc = ProjectFactory.create(owner=user)
        project_two = ProjectFactory.create()
        TaskFactory.create_batch(10, project=project_oc, info={'question': 'answer'})
        TaskFactory.create_batch(10, project=project_two, info={'question': 'answer'})
        res = self.app.get('/api/task?api_key=' + user.api_key)
        tasks = json.loads(res.data)
        assert len(tasks) == 10, tasks
        for task in tasks:
            assert task['project_id'] == project_oc.id, task
            assert task['info']['question'] == 'answer', task

        # The output should have a mime-type: application/json
        assert res.mimetype == 'application/json', res

        res = self.app.get('/api/task?api_key=' + user.api_key + "&all=1")
        tasks = json.loads(res.data)
        assert len(tasks) == 20, tasks


    @with_context
    @patch('pybossa.api.task.TaskAPI._verify_auth')
    def test_task_query_with_params(self, auth):
        """Test API query for task with params works"""
        auth.return_value = True
        project = ProjectFactory.create()
        user = UserFactory.create()
        tasks = TaskFactory.create_batch(10, project=project)
        # Test for real field
        res = self.app.get('/api/task?project_id=1&all=1&api_key=' + user.api_key)
        data = json.loads(res.data)
        # Should return one result
        assert len(data) == 10, data
        # Correct result
        assert data[0]['project_id'] == 1, data

        # Valid field but wrong value
        res = self.app.get('/api/task?project_id=99999999&all=1&api_key=' + user.api_key)
        data = json.loads(res.data)
        assert len(data) == 0, data

        # Multiple fields
        res = self.app.get('/api/task?project_id=1&state=ongoing&all=1&api_key=' + user.api_key)
        data = json.loads(res.data)
        # One result
        assert len(data) == 10, data
        # Correct result
        assert data[0]['project_id'] == 1, data
        assert data[0]['state'] == 'ongoing', data

        # Limits
        res = self.app.get('/api/task?project_id=1&limit=5&all=1&api_key=' + user.api_key)
        data = json.loads(res.data)
        for item in data:
            assert item['project_id'] == 1, item
        assert len(data) == 5, data

        # Keyset pagination
        url = "/api/task?project_id=1&limit=5&last_id=%s&all=1&api_key=%s" % (tasks[4].id, user.api_key)
        res = self.app.get(url)
        data = json.loads(res.data)
        for item in data:
            assert item['project_id'] == 1, item
        assert len(data) == 5, data
        assert data[0]['id'] == tasks[5].id, data


    @with_context
    def test_task_query_with_params_with_context(self):
        """Test API query for task with params works with context"""
        user = UserFactory.create()
        user_two = UserFactory.create()
        project_oc = ProjectFactory.create(owner=user)
        project_two = ProjectFactory.create()
        tasks = TaskFactory.create_batch(10, project=project_oc)
        TaskFactory.create_batch(10, project=project_two)
        # Test for real field
        res = self.app.get("/api/task?project_id="+ str(project_oc.id) + "&api_key=" + user.api_key)
        data = json.loads(res.data)
        # Should return then results
        assert len(data) == 10, data
        # Correct result
        for t in data:
            assert t['project_id'] == project_oc.id, t

        res = self.app.get("/api/task?api_key=" + user.api_key + "&all=1")
        data = json.loads(res.data)
        # Should return one result
        assert len(data) == 20, data


        # Valid field but wrong value
        res = self.app.get("/api/task?project_id=99999999&api_key=" + user.api_key)
        data = json.loads(res.data)
        assert len(data) == 0, data

        # Multiple fields
        res = self.app.get('/api/task?project_id=1&state=ongoing&api_key=' + user.api_key)
        data = json.loads(res.data)
        # One result
        assert len(data) == 10, data
        # Correct result
        for t in data:
            assert t['project_id'] == project_oc.id, data
            assert t['state'] == 'ongoing', data

        # Limits
        res = self.app.get("/api/task?project_id=1&limit=5&api_key=" + user.api_key)
        data = json.loads(res.data)
        assert len(data) == 5, data
        for item in data:
            assert item['project_id'] == project_oc.id, item

        # Keyset pagination
        url = "/api/task?project_id=1&limit=5&last_id=%s&api_key=%s" % (tasks[4].id, user.api_key)
        res = self.app.get(url)
        data = json.loads(res.data)
        assert len(data) == 5, data
        assert data[0]['id'] == tasks[5].id, data
        for item in data:
            assert item['project_id'] == project_oc.id, item

        # Test for real field with user_two
        res = self.app.get("/api/task?project_id="+ str(project_oc.id) + "&api_key=" + user_two.api_key)
        data = json.loads(res.data)
        # Should return then results
        assert len(data) == 0, data
        # Test for real field with user_two
        self.set_proj_passwd_cookie(project_oc, user_two)
        res = self.app.get("/api/task?all=1&project_id="+ str(project_oc.id) + "&api_key=" + user_two.api_key)
        data = json.loads(res.data)
        # Should return then results
        assert len(data) == 10, data
        # Correct result
        for t in data:
            assert t['project_id'] == project_oc.id, t

        self.set_proj_passwd_cookie(project_oc, user_two)
        self.set_proj_passwd_cookie(project_two, user_two)
        res = self.app.get("/api/task?api_key=" + user_two.api_key + "&all=1")
        data = json.loads(res.data)
        # Should return one result
        assert len(data) == 20, data


        # Valid field but wrong value
        res = self.app.get("/api/task?project_id=99999999&api_key=" + user_two.api_key)
        data = json.loads(res.data)
        assert len(data) == 0, data

        # Multiple fields
        res = self.app.get('/api/task?project_id=1&state=ongoing&api_key=' + user_two.api_key)
        data = json.loads(res.data)
        # One result
        assert len(data) == 0, data
        res = self.app.get('/api/task?all=1&project_id=1&state=ongoing&api_key=' + user_two.api_key)
        data = json.loads(res.data)
        # One result
        assert len(data) == 10, data
        # Correct result
        for t in data:
            assert t['project_id'] == project_oc.id, data
            assert t['state'] == 'ongoing', data

        # Limits
        res = self.app.get("/api/task?project_id=1&limit=5&api_key=" + user_two.api_key)
        data = json.loads(res.data)
        assert len(data) == 0, data
        res = self.app.get("/api/task?all=1&project_id=1&limit=5&api_key=" + user_two.api_key)
        data = json.loads(res.data)
        assert len(data) == 5, data
        for item in data:
            assert item['project_id'] == project_oc.id, item

        # Keyset pagination
        url = "/api/task?project_id=1&limit=5&last_id=%s&api_key=%s" % (tasks[4].id, user_two.api_key)
        res = self.app.get(url)
        data = json.loads(res.data)
        assert len(data) == 0, data
        url = "/api/task?all=1&project_id=1&limit=5&last_id=%s&api_key=%s" % (tasks[4].id, user_two.api_key)
        res = self.app.get(url)
        data = json.loads(res.data)
        assert len(data) == 5, data
        assert data[0]['id'] == tasks[5].id, data
        for item in data:
            assert item['project_id'] == project_oc.id, item


    @with_context
    def test_task_post(self):
        """Test API Task creation"""
        admin = UserFactory.create()
        user = UserFactory.create()
        make_subadmin(user)
        non_owner = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        data = dict(project_id=project.id, info='my task data')
        root_data = dict(project_id=project.id, info='my root task data')

        # anonymous user
        # no api-key
        res = self.app.post('/api/task', data=json.dumps(data))
        error_msg = 'Should not be allowed to create'
        assert_equal(res.status, '401 UNAUTHORIZED', error_msg)

        ### real user but not allowed as not owner!
        res = self.app.post('/api/task?api_key=' + non_owner.api_key,
                            data=json.dumps(data))

        error_msg = 'Should not be able to post tasks for projects of others'
        assert_equal(res.status, '403 FORBIDDEN', error_msg)

        # now a real user
        res = self.app.post('/api/task?api_key=' + user.api_key,
                            data=json.dumps(data))
        assert res.data, res
        datajson = json.loads(res.data)
        out = task_repo.get_task(datajson['id'])
        assert out, out
        assert_equal(out.info, 'my task data'), out
        assert_equal(out.project_id, project.id)

        # now the root user
        res = self.app.post('/api/task?api_key=' + admin.api_key,
                            data=json.dumps(root_data))
        assert res.data, res
        datajson = json.loads(res.data)
        out = task_repo.get_task(datajson['id'])
        assert out, out
        assert_equal(out.info, 'my root task data'), out
        assert_equal(out.project_id, project.id)

        # test user_pref
        root_data = dict(project_id=project.id, info='my root task data')
        root_data['user_pref'] = dict(languages=["Traditional Chinese"], locations=["United States"], assign_user=["email@domain.com"])
        res = self.app.post('/api/task?api_key=' + admin.api_key,
                            data=json.dumps(root_data))
        assert res.data, res


        # POST with not JSON data
        url = '/api/task?api_key=%s' % user.api_key
        res = self.app.post(url, data=data)
        err = json.loads(res.data)
        assert res.status_code == 500, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'task', err
        assert err['action'] == 'POST', err
        assert err['exception_cls'] == 'JSONDecodeError', err

        # POST with not allowed args
        res = self.app.post(url + '&foo=bar', data=json.dumps(data))
        err = json.loads(res.data)
        assert res.status_code == 415, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'task', err
        assert err['action'] == 'POST', err
        assert err['exception_cls'] == 'AttributeError', err

        # POST with fake data
        data['wrongfield'] = 13
        data['info'] = 'Kicking around on a piece of ground in your home town'
        res = self.app.post(url, data=json.dumps(data))
        err = json.loads(res.data)
        assert res.status_code == 415, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'task', err
        assert err['action'] == 'POST', err
        assert err['exception_cls'] == 'TypeError', err

    @with_context
    def test_task_post_with_reserved_fields_returns_error(self):
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        data = {'created': 'today',
                'state': 'completed',
                'id': 222, 'project_id': project.id}

        res = self.app.post('/api/task?api_key=' + user.api_key,
                            data=json.dumps(data))

        assert res.status_code == 400, res.status_code
        error = json.loads(res.data)
        assert error['exception_msg'] == "Reserved keys in payload", error

    @with_context
    def test_task_post_with_notfound_project_id(self):
        user = UserFactory.create()
        project_id = 99999
        data = dict(project_id=project_id, info='my task data')

        res = self.app.post('/api/task?api_key=' + user.api_key,
                            data=json.dumps(data))

        assert res.status_code == 404, res.status_code
        error = json.loads(res.data)
        assert error['exception_msg'] == f"404 Not Found: Non existing project id {project_id}", error

    @with_context
    def test_task_post_with_reserved_fav_user_ids(self):
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        data = {'fav_user_ids': [1, 2, 3],
                'project_id': project.id}

        res = self.app.post('/api/task?api_key=' + user.api_key,
                            data=json.dumps(data))

        assert res.status_code == 400, res.status_code
        error = json.loads(res.data)
        assert error['exception_msg'] == "Reserved keys in payload", error


    @with_context
    def test_task_put_with_reserved_fields_returns_error(self):
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        task = TaskFactory.create(project=project)
        url = '/api/task/%s?api_key=%s' % (task.id, user.api_key)
        data = {'created': 'today',
                'state': 'completed',
                'id': 222}

        res = self.app.put(url, data=json.dumps(data))

        assert res.status_code == 400, res.status_code
        error = json.loads(res.data)
        assert error['exception_msg'] == "Reserved keys in payload", error


    @with_context
    def test_task_put_with_expiration_within_bound(self):
        admin = UserFactory.create()
        project = ProjectFactory.create(owner=admin)
        task = TaskFactory.create(
            project=project,
            info=dict(x=1),
            created='2015-01-01T14:37:30.642119'
        )
        # 40 days after creation date
        expiration = '2015-02-10T14:37:30.642119'
        datajson = json.dumps({'expiration': expiration})

        url = '/api/task/%s?api_key=%s' % (task.id, admin.api_key)
        with patch.dict(self.flask_app.config, {'TASK_EXPIRATION': 60}):
            res = self.app.put(url, data=datajson)
        out = json.loads(res.data)
        assert_equal(res.status, '200 OK', res.data)
        assert_equal(expiration, out['expiration'])
        assert_equal(task.state, 'ongoing')
        assert task.id == out['id'], out


    @with_context
    def test_task_put_with_expiration_out_of_bounds(self):
        admin = UserFactory.create()
        project = ProjectFactory.create(owner=admin)
        task = TaskFactory.create(
            project=project,
            info=dict(x=1),
            created='2015-01-01T14:37:30.642119'
        )
        # the task expires 60 days after creation date
        max_expiration = '2015-03-02T14:37:30.642119'
        # 365 days after creation date
        expiration = '2016-01-01T14:37:30.642119'
        datajson = json.dumps({'expiration': expiration})

        url = '/api/task/%s?api_key=%s' % (task.id, admin.api_key)
        with patch.dict(self.flask_app.config, {'TASK_EXPIRATION': 60}):
            res = self.app.put(url, data=datajson)
        out = json.loads(res.data)
        assert_equal(res.status, '200 OK', res.data)
        # ignore time, only compare date
        assert_equal(max_expiration[0:10], out['expiration'][0:10])
        assert_equal(task.state, 'ongoing')
        assert task.id == out['id'], out


    @with_context
    def test_task_put_with_fav_user_ids_fields_returns_error(self):
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        task = TaskFactory.create(project=project)
        url = '/api/task/%s?api_key=%s' % (task.id, user.api_key)
        data = {'fav_user_ids': [1,2,3]}

        res = self.app.put(url, data=json.dumps(data))

        assert res.status_code == 400, res.status_code
        error = json.loads(res.data)
        assert error['exception_msg'] == "Reserved keys in payload", error


    @with_context
    def test_task_update(self):
        """Test API task update"""
        admin = UserFactory.create()
        user = UserFactory.create()
        make_subadmin(user)
        non_owner = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        task = TaskFactory.create(project=project, info=dict(x=1))
        root_task = TaskFactory.create(project=project, info=dict(x=1))
        data = {'n_answers': 1}
        datajson = json.dumps(data)
        root_data = {'n_answers': 4}
        root_datajson = json.dumps(root_data)

        ## anonymous
        res = self.app.put('/api/task/%s' % task.id, data=data)
        assert_equal(res.status, '401 UNAUTHORIZED', res.status)
        ### real user but not allowed as not owner!
        url = '/api/task/%s?api_key=%s' % (task.id, non_owner.api_key)
        res = self.app.put(url, data=datajson)
        assert_equal(res.status, '403 FORBIDDEN', res.status)

        ### real user
        url = '/api/task/%s?api_key=%s' % (task.id, user.api_key)
        res = self.app.put(url, data=datajson)
        out = json.loads(res.data)
        assert_equal(res.status, '200 OK', res.data)
        assert_equal(task.n_answers, data['n_answers'])
        assert_equal(task.state, 'ongoing')
        assert task.id == out['id'], out

        ### root
        res = self.app.put('/api/task/%s?api_key=%s' % (root_task.id, admin.api_key),
                           data=root_datajson)
        assert_equal(res.status, '200 OK', res.data)
        assert_equal(root_task.n_answers, root_data['n_answers'])
        assert_equal(task.state, 'ongoing')

        # PUT with not JSON data
        res = self.app.put(url, data=data)
        err = json.loads(res.data)
        assert res.status_code == 500, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'task', err
        assert err['action'] == 'PUT', err
        assert err['exception_cls'] == 'JSONDecodeError', err

        # PUT with not allowed args
        res = self.app.put(url + "&foo=bar", data=json.dumps(data))
        err = json.loads(res.data)
        assert res.status_code == 415, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'task', err
        assert err['action'] == 'PUT', err
        assert err['exception_cls'] == 'AttributeError', err

        # PUT with fake data
        data['wrongfield'] = 13
        res = self.app.put(url, data=json.dumps(data))
        err = json.loads(res.data)
        assert res.status_code == 415, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'task', err
        assert err['action'] == 'PUT', err
        assert err['exception_cls'] == 'TypeError', err

    @with_context
    def test_task_update_state(self):
        """Test API task n_answers updates state properly."""
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        task = TaskFactory.create(project=project, n_answers=1,
                                  state='ongoing', info=dict(x=1))
        data = {'n_answers': 2}
        datajson = json.dumps(data)

        url = '/api/task/%s?api_key=%s' % (task.id, user.api_key)
        res = self.app.put(url, data=datajson)
        out = json.loads(res.data)
        assert_equal(res.status, '200 OK', res.data)
        assert_equal(task.n_answers, data['n_answers'])
        assert_equal(task.state, 'ongoing')
        assert task.id == out['id'], out

        TaskRunFactory.create_batch(1, task=task)

        data = {'n_answers': 1}
        datajson = json.dumps(data)

        res = self.app.put(url, data=datajson)
        out = json.loads(res.data)
        assert_equal(res.status, '200 OK', res.data)
        assert_equal(task.n_answers, data['n_answers'])
        assert_equal(task.state, 'completed')
        assert task.id == out['id'], out

        data = {'n_answers': 5}
        datajson = json.dumps(data)

        res = self.app.put(url, data=datajson)
        out = json.loads(res.data)
        assert_equal(res.status, '200 OK', res.data)
        assert_equal(task.n_answers, data['n_answers'])
        assert_equal(task.state, 'ongoing')
        assert task.id == out['id'], out


    @with_context
    def test_task_delete(self):
        """Test API task delete"""
        admin = UserFactory.create()
        user = UserFactory.create()
        make_subadmin(user)
        non_owner = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        task = TaskFactory.create(project=project)
        root_task = TaskFactory.create(project=project)

        ## anonymous
        with patch.dict(self.flask_app.config, {'SQLALCHEMY_BINDS': {'bulkdel': "dbconn"}}):
            res = self.app.delete('/api/task/%s' % task.id)
        error_msg = 'Anonymous should not be allowed to delete'
        print(res.status)
        assert_equal(res.status, '401 UNAUTHORIZED', error_msg)

        ### real user but not allowed as not owner!
        url = '/api/task/%s?api_key=%s' % (task.id, non_owner.api_key)
        with patch.dict(self.flask_app.config, {'SQLALCHEMY_BINDS': {'bulkdel': "dbconn"}}):
            res = self.app.delete(url)
        error_msg = 'Should not be able to update tasks of others'
        assert_equal(res.status, '403 FORBIDDEN', error_msg)

        #### real user
        # DELETE with not allowed args
        with patch.dict(self.flask_app.config, {'SQLALCHEMY_BINDS': {'bulkdel': "dbconn"}}):
            res = self.app.delete(url + "&foo=bar")
        err = json.loads(res.data)
        assert res.status_code == 415, err
        assert err['status'] == 'failed', err
        assert err['target'] == 'task', err
        assert err['action'] == 'DELETE', err
        assert err['exception_cls'] == 'AttributeError', err

        # DELETE returns 204
        url = '/api/task/%s?api_key=%s' % (task.id, user.api_key)
        with patch.dict(self.flask_app.config, {'SQLALCHEMY_BINDS': {'bulkdel': "dbconn"}}):
            res = self.app.delete(url)
        assert_equal(res.status, '204 NO CONTENT', res.data)
        assert res.data == b'', res.data  # res.data is bytes type

        #### root user
        url = '/api/task/%s?api_key=%s' % (root_task.id, admin.api_key)
        with patch.dict(self.flask_app.config, {'SQLALCHEMY_BINDS': {'bulkdel': "dbconn"}}):
            res = self.app.delete(url)
        assert_equal(res.status, '204 NO CONTENT', res.data)

        tasks = task_repo.filter_tasks_by(project_id=project.id)
        assert task not in tasks, tasks
        assert root_task not in tasks, tasks

    @with_context
    def test_delete_task_cascade(self):
        """Test API delete task deletes associated taskruns"""
        task = TaskFactory.create()
        task_runs = TaskRunFactory.create_batch(3, task=task)
        url = '/api/task/%s?api_key=%s' % (task.id, task.project.owner.api_key)
        task_id = task.id
        with patch.dict(self.flask_app.config, {'SESSION_REPLICATION_ROLE_DISABLED': True}):
            res = self.app.delete(url)

        assert_equal(res.status, '204 NO CONTENT', res.data)
        task_runs = task_repo.filter_task_runs_by(task_id=task_id)
        assert len(task_runs) == 0, "There should not be any task run for task"

    @with_context
    def test_delete_task_when_result_associated(self):
        """Test API delete task fails when a result is associated."""
        result = self.create_result()
        project = project_repo.get(result.project_id)

        url = '/api/task/%s?api_key=%s' % (result.task_id,
                                           project.owner.api_key)
        res = self.app.delete(url)
        assert_equal(res.status, '403 FORBIDDEN', res.status)

    @with_context
    def test_delete_task_when_result_associated_variation(self):
        """Test API delete task fails when a result is associated after
        increasing the n_answers changing its state from completed to
        ongoing."""
        result = self.create_result()
        project = project_repo.get(result.project_id)
        task = task_repo.get_task(result.task_id)
        task.n_answers = 100
        task_repo.update(task)

        url = '/api/task/%s?api_key=%s' % (result.task_id,
                                           project.owner.api_key)
        res = self.app.delete(url)
        assert_equal(res.status, '403 FORBIDDEN', res.status)

    @with_context
    def test_delete_task_when_result_associated_admin(self):
        """Test API delete task works when a result is associated as admin."""
        admin = UserFactory.create(admin=True)
        result = self.create_result()
        project = project_repo.get(result.project_id)

        url = '/api/task/%s?api_key=%s' % (result.task_id,
                                           admin.api_key)
        with patch.dict(self.flask_app.config, {'SQLALCHEMY_BINDS': {'bulkdel': "dbconn"}}):
            res = self.app.delete(url)
        assert_equal(res.status, '204 NO CONTENT', res.status)

    @with_context
    def test_delete_task_when_result_associated_variation(self):
        """Test API delete task fails when a result is associated after
        increasing the n_answers changing its state from completed to
        ongoing."""
        admin = UserFactory.create(admin=True)
        result = self.create_result()
        project = project_repo.get(result.project_id)
        task = task_repo.get_task(result.task_id)
        task.n_answers = 100
        task_repo.update(task)

        url = '/api/task/%s?api_key=%s' % (result.task_id,
                                           admin.api_key)
        with patch.dict(self.flask_app.config, {'SQLALCHEMY_BINDS': {'bulkdel': "dbconn"}}):
            res = self.app.delete(url)
        assert_equal(res.status, '204 NO CONTENT', res.status)

    @with_context
    def test_create_update_gold_answers(self):
        [admin, subadminowner, subadmin, reguser] = UserFactory.create_batch(4)
        make_admin(admin)
        make_subadmin(subadminowner)
        make_subadmin(subadmin)

        project = ProjectFactory.create(owner=subadminowner)
        admin_headers = dict(Authorization=admin.api_key)
        task_info = dict(field_1='one', field_2='two')
        gold_answers = dict(field_3='some ans', field_4='some ans 2')

        # POST gold_answers successful
        data = dict(project_id=project.id, info=task_info, gold_answers=gold_answers,
            n_answers=2)
        res = self.app.post('/api/task', data=json.dumps(data), headers=admin_headers)
        assert res.data, res
        jdata = json.loads(res.data)
        assert_equal(jdata['info'], task_info), jdata
        assert_equal(jdata['gold_answers'], gold_answers), jdata
        assert jdata['calibration'] == 1, 'calibration should have been set with updating gold_answers'
        assert jdata['exported'] == True, 'exported should be True with new gold task'

        # GET task by subadmin not owner user does not get gold answers,
        # whereas admin/subadmin gets gold answers
        subadminowner_headers = dict(Authorization=subadminowner.api_key)
        subadmin_headers = dict(Authorization=subadmin.api_key)
        reguser_headers = dict(Authorization=reguser.api_key)
        res = self.app.get('/api/task/1', headers=admin_headers)
        jdata = json.loads(res.data)
        assert_equal(jdata['gold_answers'], gold_answers), jdata
        res = self.app.get('/api/task/1', headers=subadminowner_headers)
        jdata = json.loads(res.data)
        assert_equal(jdata['gold_answers'], gold_answers), jdata
        res = self.app.get('/api/task/1', headers=subadmin_headers)
        jdata = json.loads(res.data)
        assert 'gold_answers' not in jdata, jdata
        assert 'calibration' not in jdata, jdata
        # regular users should not receive gold_answers and calibration info
        res = self.app.get('/api/task/1', headers=reguser_headers)
        jdata = json.loads(res.data)
        assert 'gold_answers' not in jdata, jdata
        assert 'calibration' not in jdata, jdata

        # PUT request updates gold answers
        updated_gold_answers = dict(field_3='some ans - updated', field_5='one more ans')
        data = dict(project_id=project.id, gold_answers=updated_gold_answers)
        res = self.app.put('/api/task/1', data=json.dumps(data), headers=subadminowner_headers)
        jdata = json.loads(res.data)
        gold_answers.update(updated_gold_answers)
        assert_equal(jdata['gold_answers'], updated_gold_answers), jdata

        # Beyond redundancy, submitting task runs to task with gold_answers
        # is permitted. such task run submissions should not mark task as complete
        task = task_repo.get_task(jdata['id'])
        n_taskruns = 8
        taskruns = TaskRunFactory.create_batch(n_taskruns, project=project, task=task)
        assert task.state == 'ongoing', 'Gold task state should be ongoing beyond task submissions > task redundancy'
        assert len(taskruns) == n_taskruns, 'For gold task, number of task runs submissions can be beyond task redundancy'
        assert task.exported == False, 'Gold tasks to be marked exported as False upon task run submission'

        task.exported = True
        taskruns = TaskRunFactory.create_batch(1, project=project, task=task)
        assert task.exported == False, 'Gold tasks to be marked exported as False upon task run submission'

        # reset gold answer
        data = dict(project_id=project.id, gold_answers={})
        res = self.app.put('/api/task/1', data=json.dumps(data), headers=subadminowner_headers)
        jdata = json.loads(res.data)
        assert_equal(jdata['gold_answers'], {}), jdata
        assert jdata['calibration'] == 0, 'Calibration should be reset upon gold_answers reset'

    @with_context
    @patch('pybossa.api.task.task_repo.find_duplicate')
    @patch('pybossa.api.task.validate_required_fields')
    def test_task_post_api_exceptions(self, inv_field, dup):
        """Get a list of tasks using a list of project_ids."""
        [admin, subadminowner] = UserFactory.create_batch(2)
        make_admin(admin)
        make_subadmin(subadminowner)

        project = ProjectFactory.create(owner=subadminowner)
        admin_headers = dict(Authorization=admin.api_key)
        task_info = dict(field_1='one', field_2='two')
        gold_answers = dict(field_3='some ans')
        data = dict(project_id=project.id, info=task_info, gold_answers=gold_answers,
            n_answers=2)

        dup.return_value = True
        res = self.app.post('/api/task', data=json.dumps(data), headers=admin_headers)
        res_data = json.loads(res.data)
        assert json.loads(res_data['exception_msg'])['reason'] == 'DUPLICATE_TASK', res

        dup.return_value = False
        inv_field = True
        res = self.app.post('/api/task', data=json.dumps(data), headers=admin_headers)
        res_data = json.loads(res.data)
        assert res_data['exception_msg'] == 'Missing or incorrect required fields: ', res

    @with_context
    @patch('pybossa.api.task.url_for', return_value='testURL')
    @patch('pybossa.api.task.upload_json_data')
    def upload_gold_data(self, mock, mock2):
        """Test upload_gold_data"""
        task = task_repo.get_task(1)
        tasks = TaskAPI()
        url = tasks.upload_gold_data(task, 1, {'ans1': 'test'}, file_id=1)
        assert url == 'testURL', url

        url = tasks.upload_gold_data(task, 1, {'ans1': 'test'})
        assert url == 'testURL', url

    @with_context
    def test_create_task_with_hdfs_payload(self):
        [admin, subadminowner, subadmin, reguser] = UserFactory.create_batch(4)
        make_admin(admin)
        make_subadmin(subadminowner)
        make_subadmin(subadmin)

        project = ProjectFactory.create(owner=subadminowner)
        admin_headers = dict(Authorization=admin.api_key)
        task_info = dict(field_1='one', field_2='/fileproxy/hdfs/my_hdfs_file.txt')

        # POST fails with error 400
        data = dict(project_id=project.id, info=task_info, n_answers=2)
        res = self.app.post('/api/task', data=json.dumps(data), headers=admin_headers)
        assert res.status_code == 400
        response = json.loads(res.data)
        assert response["exception_msg"] == "Invalid task payload. HDFS is not supported"

        # POST successful with hdfs not present in task payload
        task_info["field_2"] = "xyz"
        data = dict(project_id=project.id, info=task_info, n_answers=2)
        res = self.app.post('/api/task', data=json.dumps(data), headers=admin_headers)
        task = json.loads(res.data)
        assert res.status_code == 200
        assert task["info"] == {"field_1": "one", "field_2": "xyz"}

    @with_context
    def test_create_task_find_duplicate_with_checksum(self):
        """Test create tasks performing duplicate check using dup_checksum value"""

        from flask import current_app
        current_app.config["TASK_RESERVED_COLS"] = ["genid_xyz", "genid_abc"]

        subadmin = UserFactory.create(subadmin=True)
        subadmin_headers = dict(Authorization=subadmin.api_key)
        project = ProjectFactory.create(
            owner=subadmin,
            short_name="testproject",
            info={
                "duplicate_task_check": {
                    "duplicate_fields": ["a", "c"]
                }
            })

        task_data = dict(
            project_id = project.id,
            info = {"a": 1, "b": 2, "c": 3}
        )
        checksum = hashlib.sha256()
        expected_dupcheck_payload = {"a": 1, "c": 3}
        checksum.update(json.dumps(expected_dupcheck_payload, sort_keys=True).encode("utf-8"))
        expected_checksum =  checksum.hexdigest()

        # task created with checksum as per project configuration
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        task = json.loads(res.data)
        assert res.status_code == 200
        assert task["dup_checksum"] == expected_checksum, task["dup_checksum"]

        # duplicate task creation failed
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        res.status == "409 CONFLICT"

        # with duplicate task check not configured, dup_checksum generated dropping reserved fields
        project2 = ProjectFactory.create(
            owner=subadmin,
            short_name="testproject2",
            info={})
        task_data = dict(
            project_id = project2.id,
            info = {"a": 1, "b": 2, "c": 3, "genid_xyz": "xyz123", "genid_abc": "abc123"}
        )
        expected_dupcheck_payload = {k:v for k,v in task_data["info"].items() if k not in current_app.config["TASK_RESERVED_COLS"]}
        checksum = hashlib.sha256()
        checksum.update(json.dumps(expected_dupcheck_payload, sort_keys=True).encode("utf-8"))
        expected_checksum =  checksum.hexdigest()

        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        task = json.loads(res.data)
        assert res.status_code == 200
        assert task["dup_checksum"] == expected_checksum, task["dup_checksum"]

    @with_context
    def test_create_task_with_duplicate_checksum_fails(self):
        """Test create tasks performing duplicate check using dup_checksum value fails due to missing configured fields in task payload"""

        subadmin = UserFactory.create(subadmin=True)
        # self.signin_user(subadmin)
        project = ProjectFactory.create(
            owner=subadmin,
            short_name="testproject",
            info={
                "duplicate_task_check": {
                    "duplicate_fields": ["a", "c"]
                }
            })

        task_data = dict(
            project_id = project.id,
            info = {"a": 1, "b": 2, "x": 3, "y": 4}  # missing field "c" in task payload as per duplicate_task_check field list configured
        )
        checksum = hashlib.sha256()
        expected_dupcheck_payload = {"a": 1, "c": 3}
        checksum.update(json.dumps(expected_dupcheck_payload, sort_keys=True).encode("utf-8"))
        expected_checksum =  checksum.hexdigest()

        subadmin_headers = dict(Authorization=subadmin.api_key)

        # duplicate task creation to fail
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        response = res.json
        assert response["status_code"] == 400 and response["exception_msg"] == "Error generating duplicate checksum due to missing checksum configured fields ['a', 'c']"

        # with duplicate task check not configured, no error reported and task created successfully
        project2 = ProjectFactory.create(
            owner=subadmin,
            short_name="testproject2",
            info={})
        task_data = dict(
            project_id = project2.id,
            info = {"a": 1, "b": 2, "c": 3}
        )
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        task = json.loads(res.data)
        assert res.status_code == 200


    @with_context
    def test_create_task_fails_with_duplicate_against_all_tasks(self):
        """Test create tasks performing duplicate check against all tasks fails with 409 conflict error"""

        subadmin = UserFactory.create(subadmin=True)
        subadmin_headers = dict(Authorization=subadmin.api_key)

        # project checking duplicate task against all tasks; ongoing and completed
        project = ProjectFactory.create(
            owner=subadmin,
            short_name="testproject",
            info={
                "duplicate_task_check": {
                    "duplicate_fields": ["a", "c"],
                    "completed_tasks": True
                }
            })

        # create task and complete it
        task_data = dict(
            project_id = project.id,
            info = {"a": 1, "b": 1, "c": 111}
        )
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.status_code == 200, res
        task1 = task_repo.get_task(res.json['id'])
        res = TaskRunFactory.create(task=task1, user=subadmin)
        assert res.task_id == task1.id, f"taskrun should be submitted against task {task1.id}"

        task_data["info"] = {"a": 2, "b": 22, "c": 222}
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.status_code == 200, res

        task_data["info"] = {"a": 3, "b": 33, "c": 333}
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.status_code == 200, res

        # create task duplicate of completed task
        # a and c are configured for dup check.
        # difft value of b doesn't matter and task creation should still fail w/ 409
        task_data = dict(
            project_id = project.id,
            info = {"a": 1, "b": 2, "c": 111}
        )

        subadmin_headers = dict(Authorization=subadmin.api_key)
        # duplicate task creation failed
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.status == "409 CONFLICT", res

    @with_context
    def test_create_task_pass_with_duplicate_against_ongoing_tasks(self):
        """Test create tasks performing duplicate check against ongoing tasks only"""

        subadmin = UserFactory.create(subadmin=True)
        subadmin_headers = dict(Authorization=subadmin.api_key)

        # project checking duplicate task against all tasks; ongoing and completed
        project = ProjectFactory.create(
            owner=subadmin,
            short_name="testproject",
            info={
                "duplicate_task_check": {
                    "duplicate_fields": ["a", "c"],
                    "completed_tasks": False        # only ongoing tasks
                }
            })

        # create task and complete it
        task_data = dict(
            project_id = project.id,
            info = {"a": 1, "b": 1, "c": 111}
        )
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.status_code == 200, res
        task1 = task_repo.get_task(res.json['id'])
        res = TaskRunFactory.create(task=task1, user=subadmin)
        assert res.task_id == task1.id, f"taskrun should be submitted against task {task1.id}"

        task_data["info"] = {"a": 2, "b": 22, "c": 222}
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.status_code == 200, res

        task_data["info"] = {"a": 3, "b": 33, "c": 333}
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.status_code == 200, res

        # create task duplicate of completed task
        # a and c are configured for dup check.
        # difft value of b doesn't matter and task creation should still pass
        # as similar task has been completed and project is configured to
        # perform duplicate check against ongoing tasks only
        task_data = dict(
            project_id = project.id,
            info = {"a": 1, "b": 2, "c": 111}
        )

        subadmin_headers = dict(Authorization=subadmin.api_key)
        # task creation should pass as duplicate check is against ongoing noncompleted tasks
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.status_code == 200, res

    @with_context
    def test_create_task_pass_with_duplicate_against_ongoing_unexipred_tasks(self):
        """Test create tasks performing duplicate check against ongoing unexpired tasks"""

        subadmin = UserFactory.create(subadmin=True)
        subadmin_headers = dict(Authorization=subadmin.api_key)

        # project checking duplicate task against all tasks; ongoing and completed
        project = ProjectFactory.create(
            owner=subadmin,
            short_name="testproject",
            info={
                "duplicate_task_check": {
                    "duplicate_fields": ["a", "c"],
                    "completed_tasks": False        # only ongoing tasks
                }
            })

        # create expired task
        task_data = dict(
            project_id = project.id,
            info = {"a": 1, "b": 1, "c": 111},
            expiration="2022-02-22T19:25:45.762592"
        )
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.json["expiration"] == "2022-02-22T19:25:45.762592"

        task_data["info"] = {"a": 2, "b": 22, "c": 222}
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)

        task_data["info"] = {"a": 3, "b": 33, "c": 333}
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)

        # create task duplicate of completed task
        # a and c are configured for dup check.
        # difft value of b doesn't matter and task creation should still pass
        # as similar task has been completed and project is configured to
        # perform duplicate check against ongoing tasks only
        task_data = dict(
            project_id = project.id,
            info = {"a": 1, "b": 2, "c": 111}
        )

        subadmin_headers = dict(Authorization=subadmin.api_key)
        # task creation to pass as similar task that is present has already expired
        res = self.app.post('/api/task', data=json.dumps(task_data), headers=subadmin_headers)
        assert res.status_code == 200, res
