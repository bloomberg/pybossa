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
from unittest.mock import patch

import pybossa
from pybossa.core import task_repo, project_repo, user_repo
from pybossa.model.task import Task
from pybossa.model.task_run import TaskRun
from pybossa.sched import release_user_locks_for_project, has_lock, TIMEOUT
from test import Test, db, with_context
from test.factories import AnonymousTaskRunFactory
from test.factories import TaskFactory, ProjectFactory, TaskRunFactory, \
    UserFactory
from test.helper import sched
import time
from pybossa.sched import release_reserve_task_lock_by_id


class TestSched(sched.Helper):

    endpoints = ['project', 'task', 'taskrun']

    # Tests
    @with_context
    def test_anonymous_01_newtask(self):
        """ Test SCHED newtask returns a Task for the Anonymous User"""
        project = ProjectFactory.create()
        TaskFactory.create_batch(2, project=project, info='hola')

        res = self.app.get('api/project/%s/newtask' %project.id)
        data = json.loads(res.data)
        task_id = data['id']
        assert 'error' in data['info'], data

        taskrun = dict(project_id=data['project_id'], task_id=data['id'], info="hola")
        res = self.app.post('api/taskrun', data=json.dumps(taskrun))

        res = self.app.get('api/project/%s/newtask' %project.id)
        data = json.loads(res.data)
        #assert data['info'] == 'hola', data
        #assert data['id'] != task_id, data

    @with_context
    def test_anonymous_01_newtask_limits(self):
        """ Test SCHED newtask returns a list of Tasks for the Anonymous User"""
        project = ProjectFactory.create()
        TaskFactory.create_batch(100, project=project, info='hola')

        url = 'api/project/%s/newtask?limit=100' % project.id
        res = self.app.get(url)
        data = json.loads(res.data)
        assert 'error' in data['info'], 'no anon contributions'

        url = 'api/project/%s/newtask?limit=200' % project.id
        res = self.app.get(url)
        data = json.loads(res.data)
        assert 'error' in data['info'], 'no anon contributions'

    @with_context
    def test_anonymous_02_gets_different_tasks_limits(self):
        """ Test SCHED newtask returns N different list of Tasks for the Anonymous User"""
        assigned_tasks = []
        # Get a Task until scheduler returns None
        project = ProjectFactory.create()
        tasks = TaskFactory.create_batch(10, project=project, info={})
        res = self.app.get('api/project/%s/newtask?limit=5' % project.id)
        data = json.loads(res.data)
        assert 'error' in data['info']

    @with_context
    def test_external_uid_02_gets_different_tasks_limits(self):
        """ Test SCHED newtask returns N different list of Tasks
        for a external User ID."""
        assigned_tasks = []
        # Get a Task until scheduler returns None
        project = ProjectFactory.create()
        tasks = TaskFactory.create_batch(10, project=project, info={})

        headers = self.get_headers_jwt(project)

        url = 'api/project/%s/newtask?limit=5&external_uid=%s' % (project.id, '1xa')

        res = self.app.get(url, headers=headers)
        data = json.loads(res.data)
        assert 'error' in data['info']

    @with_context
    def test_anonymous_03_respects_limit_tasks(self):
        """ Test SCHED newtask respects the limit of 30 TaskRuns per Task"""
        assigned_tasks = []
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(1, project=project, n_answers=10)

        # Get Task until scheduler returns None
        for i in range(10):
            res = self.app.get('api/project/%s/newtask' % project.id)
            data = json.loads(res.data)
            assert 'error' in data['info'], 'no anonymous contributors allowed'

            while data.get('id') is not None:
                # Check that we received a Task
                assert data.get('id'), data


    @with_context
    def test_user_01_newtask(self):
        """ Test SCHED newtask returns a Task for John Doe User"""
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(2, project=project, n_answers=2)

        # Register
        self.register()
        self.signin()
        url = 'api/project/%s/newtask' % project.id
        self.set_proj_passwd_cookie(project, username='johndoe')
        res = self.app.get(url)
        data = json.loads(res.data)
        task_id = data['id']
        assert data['id'], data

        taskrun = dict(project_id=data['project_id'], task_id=data['id'], info="hola")
        res = self.app.post('api/taskrun', data=json.dumps(taskrun))

        res = self.app.get(url)
        data = json.loads(res.data)
        assert data['id'], data
        assert data['id'] != task_id, data

        self.signout()

    @with_context
    def test_user_01_release_tasks(self):
        """ Test SCHED newtask returns a Task for John Doe User"""
        user = UserFactory.create(id=500)
        project = ProjectFactory.create(owner=user,info={'sched':'default'})
        TaskFactory.create_batch(2, project=project, n_answers=2)
        self.signin_user(user)
        url = 'api/project/%s/newtask' % project.id
        self.set_proj_passwd_cookie(project, user=user)
        res = self.app.get(url)
        data = json.loads(res.data)
        task_id = data['id']
        print(data)
        assert task_id, data
        assert has_lock(task_id, user.id, TIMEOUT)

        released_task_ids = release_user_locks_for_project(user.id, project.id)
        # TODO: Figure out how to test this
        # assert released_task_ids == [task_id]
        # assert not has_lock(task_id, user.id, TIMEOUT)
        self.signout()

    @with_context
    def test_user_01_newtask_limits(self):
        """ Test locked scheduler newtask returns single Task for John Doe User ignoring limits"""
        self.register()
        self.signin()
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        tasks = TaskFactory.create_batch(10, project=project, info=dict(foo=1))

        # Register
        url = 'api/project/%s/newtask?limit=2' % project.id
        res = self.app.get(url)
        data = json.loads(res.data)
        assert not isinstance(data, list), data
        assert data['info']['foo'] == 1, data
        self.signout()

    @with_context
    def test_user_02_gets_different_tasks(self):
        """ Test SCHED newtask returns N different Tasks for John Doe User"""
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(10, project=project)

        # Register
        self.register()
        self.signin()

        assigned_tasks = []
        # Get Task until scheduler returns None
        url = 'api/project/%s/newtask' % project.id
        self.set_proj_passwd_cookie(project, username='johndoe')
        res = self.app.get(url)
        data = json.loads(res.data)
        while data.get('id') is not None:
            # Check that we received a Task
            assert data.get('id'),  data

            # Save the assigned task
            assigned_tasks.append(data)

            # Submit an Answer for the assigned task
            tr = dict(project_id=data['project_id'], task_id=data['id'],
                      info={'answer': 'No'})
            tr = json.dumps(tr)

            self.app.post('/api/taskrun', data=tr)
            res = self.app.get(url)
            data = json.loads(res.data)

        # Check if we received the same number of tasks that the available ones
        tasks = db.session.query(Task).filter_by(project_id=1).all()
        assert len(assigned_tasks) == len(tasks), assigned_tasks
        # Check if all the assigned Task.id are equal to the available ones
        tasks = db.session.query(Task).filter_by(project_id=1).all()
        err_msg = "Assigned Task not found in DB Tasks"
        for at in assigned_tasks:
            assert self.is_task(at['id'], tasks), err_msg
        # Check that there are no duplicated tasks
        err_msg = "One Assigned Task is duplicated"
        for at in assigned_tasks:
            assert self.is_unique(at['id'], assigned_tasks), err_msg

    @with_context
    def test_user_02_gets_different_tasks_limit(self):
        """ Test SCHED newtask returns N different list of Tasks for John Doe User"""
        # Register
        self.register()
        self.signin()

        total_tasks = 10
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(total_tasks, project=project)

        assigned_tasks = []

        # with locked scheduler, only one task returned no matter what limit is passed
        # hence call newtask until the total number of tasks
        for i in range(total_tasks):
            # Get Task until scheduler returns None
            url = 'api/project/%s/newtask?limit=5' % project.id
            res = self.app.get(url)
            data = json.loads(res.data)
            assert data.get('id'), data

            # Save the assigned task
            assigned_tasks.append(data)

            # Submit an Answer for the assigned task
            tr = dict(project_id=data['project_id'], task_id=data['id'],
                        info={'answer': 'No'})
            tr = json.dumps(tr)

            self.app.post('/api/taskrun', data=tr)
            res = self.app.get(url)
            data = json.loads(res.data)
            self.redis_flushall()

        # Check if we received the same number of tasks that the available ones
        tasks = db.session.query(Task).filter_by(project_id=1).all()
        assert len(assigned_tasks) == len(tasks), assigned_tasks
        # Check if all the assigned Task.id are equal to the available ones
        tasks = db.session.query(Task).filter_by(project_id=1).all()
        err_msg = "Assigned Task not found in DB Tasks"
        for at in assigned_tasks:
            assert self.is_task(at['id'], tasks), err_msg
        # Check that there are no duplicated tasks
        err_msg = "One Assigned Task is duplicated"
        for at in assigned_tasks:
            assert self.is_unique(at['id'], assigned_tasks), err_msg


    @with_context
    @patch('pybossa.api.pwd_manager.ProjectPasswdManager.password_needed')
    def test_user_03_respects_limit_tasks(self, password_needed):
        """ Test SCHED newtask respects the limit of 30 TaskRuns per Task"""
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(1, project=project, n_answers=10)
        password_needed.return_value = False

        url = 'api/project/%s/newtask' % project.id
        assigned_tasks = []
        # We need one extra loop to allow the scheduler to mark a task as completed
        for i in range(11):
            self.register(fullname="John Doe" + str(i),
                          name="johndoe" + str(i),
                          password="1234" + str(i))
            self.signin(email="johndoe" + str(i) + "@example.com", password="1234" + str(i))
            # Get Task until scheduler returns None
            res = self.app.get(url)
            data = json.loads(res.data)

            # Check that we received a Task
            if data.get('id'):
                assert data.get('id'),  data

                # Save the assigned task
                assigned_tasks.append(data)

                # Submit an Answer for the assigned task
                tr = dict(project_id=data['project_id'], task_id=data['id'],
                          info={'answer': 'No'})
                tr = json.dumps(tr)
                self.app.post('/api/taskrun', data=tr)
                self.redis_flushall()
            self.signout()

        # Check if there are 30 TaskRuns per Task
        tasks = db.session.query(Task).filter_by(project_id=1).all()
        for t in tasks:
            assert len(t.task_runs) == 10, t.task_runs
        # Check that all the answers are from different IPs
        err_msg = "There are two or more Answers from same User"
        for t in tasks:
            for tr in t.task_runs:
                assert self.is_unique(tr.user_id, t.task_runs), err_msg
        # Check that task.state is updated to completed
        for t in tasks:
            assert t.state == "completed", t.state


    @with_context
    @patch('pybossa.api.pwd_manager.ProjectPasswdManager.password_needed')
    def test_user_03_respects_limit_tasks_limit(self, password_needed):
        """ Test SCHED limit arg newtask respects the limit of 20 TaskRuns per list of Tasks"""
        # Del previous TaskRuns
        password_needed.return_value = False
        assigned_tasks = []
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(2, project=project, n_answers=10)

        # We need one extra loop to allow the scheduler to mark a task as completed
        # 10 users accessing 2 tasks and submitting taskruns
        url = 'api/project/%s/newtask?limit=2' % project.id
        for i in range(10):
            name = "johndoe" + str(i)
            password = "1234" + str(i)
            self.register(fullname="John Doe" + str(i),
                          name=name, password=password)
            self.signin(email=name + "@example.com",
                        password=password)

            for j in range(2):
                # Get Task until scheduler returns None
                res = self.app.get(url)
                data = json.loads(res.data)

                # Check that we received a Task
                assert data.get('id'),  data

                # Save the assigned task
                assigned_tasks.append(data)

                # Submit an Answer for the assigned task
                tr = dict(project_id=data['project_id'], task_id=data['id'],
                            info={'answer': 'No'})
                tr = json.dumps(tr)
                self.app.post('/api/taskrun', data=tr).data
                self.redis_flushall()
            self.signout()

        # Check if there are 30 TaskRuns per Task
        tasks = db.session.query(Task).filter_by(project_id=1).all()
        for t in tasks:
            assert len(t.task_runs) == 10, t.task_runs
        # Check that all the answers are from different IPs
        err_msg = "There are two or more Answers from same User"
        for t in tasks:
            for tr in t.task_runs:
                assert self.is_unique(tr.user_id, t.task_runs), err_msg
        # Check that task.state is updated to completed
        for t in tasks:
            assert t.state == "completed", t.state


    @with_context
    def test_task_preloading(self):
        """Test TASK Pre-loading returns no task"""

        # locked scheduler (default) retuns only one locked task
        # passing offset to fetch task expected to return no task
        # https://github.com/bloomberg/pybossa/blob/main/pybossa/sched.py#L277-L278

        # Del previous TaskRuns
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(10, project=project)

        # Register
        self.register()
        self.signin()

        assigned_tasks = []
        # Get Task until scheduler returns None
        self.set_proj_passwd_cookie(project, username='johndoe')
        url = 'api/project/%s/newtask' % project.id
        res = self.app.get(url)
        task1 = json.loads(res.data)
        # Check that we received a Task
        assert task1.get('id'),  task1
        # Pre-load the next task for the user
        res = self.app.get(url + '?offset=1')
        task2 = json.loads(res.data)
        # Check that Task received is None with offset
        assert not task2,  task2
        ## Save the assigned task
        assigned_tasks.append(task1)

        # Submit an Answer for the assigned and pre-loaded task
        for t in assigned_tasks:
            tr = dict(project_id=t['project_id'], task_id=t['id'], info={'answer': 'No'})
            tr = json.dumps(tr)

            self.app.post('/api/taskrun', data=tr)
        # Get two tasks again
        res = self.app.get(url)
        task3 = json.loads(res.data)
        # Check that we received a Task
        assert task3.get('id'),  task1

    @with_context
    def test_task_priority(self):
        """Test SCHED respects priority_0 field"""
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(10, project=project)

        # Register
        self.register()
        self.signin()

        # By default, tasks without priority should be ordered by task.id (FIFO)
        tasks = db.session.query(Task).filter_by(project_id=1).order_by('id').all()
        url = 'api/project/%s/newtask' % project.id
        self.set_proj_passwd_cookie(project, username='johndoe')
        res = self.app.get(url)
        task1 = json.loads(res.data)
        # Check that we received a Task
        err_msg = "Task.id should be the same"
        assert task1.get('id') == tasks[0].id, err_msg

        url = f"/api/task/%s/canceltask" % task1["id"]
        res = self.app_post_json(url,
                            data={'projectname': project.short_name},
                            follow_redirects=False,
                            )
        data = json.loads(res.data)
        assert data.get('success') == True, data
        time.sleep(1)

        # Now let's change the priority to a random task
        import random
        t = random.choice(tasks)
        # Increase priority to maximum
        t.priority_0 = 1
        db.session.add(t)
        db.session.commit()
        # Request again a new task
        url = 'api/project/%s/newtask?orderby=priority_0&desc=true' % project.id
        res = self.app.get(url)
        task1 = json.loads(res.data)
        # Check that we received a Task
        err_msg = "Task.id should be the same"
        assert task1.get('id') == t.id, err_msg
        err_msg = "Task.priority_0 should be the 1"
        assert task1.get('priority_0') == 1, err_msg

    @with_context
    def test_task_priority_limit(self):
        """Test SCHED respects priority_0 field with limit"""
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(10, project=project)

        # Register
        self.register()
        self.signin()

        # By default, tasks without priority should be ordered by task.id (FIFO)
        tasks = db.session.query(Task).filter_by(project_id=project.id).order_by('id').all()
        url = 'api/project/%s/newtask?limit=2' % project.id
        self.set_proj_passwd_cookie(project, username='johndoe')
        res = self.app.get(url)
        task1 = json.loads(res.data)
        # Check that we received a Task
        err_msg = "Task.id should be the same"
        assert task1.get('id') == tasks[0].id, err_msg

        # cancel the tasks and obtain task upon changing priority
        url = f"/api/task/%s/canceltask" % task1["id"]
        res = self.app_post_json(url,
                            data={'projectname': project.short_name},
                            follow_redirects=False,
                            )
        data = json.loads(res.data)
        assert data.get('success') == True, data
        time.sleep(1)


        # Now let's change the priority to a random task
        import random
        t = random.choice(tasks)
        # Increase priority to maximum
        t.priority_0 = 1
        db.session.add(t)
        db.session.commit()
        # Request again a new task
        url = 'api/project/%s/newtask?limit=2' % project.id
        res = self.app.get(url + '&orderby=priority_0&desc=true')
        task1 = json.loads(res.data)
        # Check that we received a Task
        err_msg = "Task.id should be the same"
        assert task1.get('id') == t.id, (err_msg, task1)
        err_msg = "Task.priority_0 should be the 1"
        assert task1.get('priority_0') == 1, err_msg


    @with_context
    def test_task_priority_external_uid(self):
        """Test SCHED respects priority_0 field for externa uid"""
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(10, project=project)

        # By default, tasks without priority should be ordered by task.id (FIFO)
        tasks = db.session.query(Task).filter_by(project_id=1).order_by('id').all()
        project = project_repo.get(1)
        headers = self.get_headers_jwt(project)
        url = 'api/project/%s/newtask?external_uid=342' % project.id
        res = self.app.get(url, headers=headers)
        task1 = json.loads(res.data)
        assert 'error' in task1.get('info')

    @with_context
    def test_task_priority_external_uid_limit(self):
        """Test SCHED respects priority_0 field for externa uid with limit"""
        project = ProjectFactory.create(owner=UserFactory.create(id=500))
        TaskFactory.create_batch(10, project=project)

        # By default, tasks without priority should be ordered by task.id (FIFO)
        tasks = db.session.query(Task).filter_by(project_id=project.id).order_by('id').all()
        headers = self.get_headers_jwt(project)
        url = 'api/project/%s/newtask?external_uid=342&limit=2' % project.id
        res = self.app.get(url, headers=headers)
        tasks1 = json.loads(res.data)
        # Check that we received a Task
        err_msg = "Task.id should be the same"
        assert 'error' in tasks1['info']

    def _add_task_run(self, app, task, user=None):
        tr = AnonymousTaskRunFactory.create(project=app, task=task)

    @with_context
    def test_no_more_tasks(self):
        """Test that a users gets always tasks"""
        owner = UserFactory.create()
        project = ProjectFactory.create(owner=owner, short_name='egil', name='egil',
                  description='egil')

        project_id = project.id

        tasks = TaskFactory.create_batch(20, project=project, n_answers=10)

        for t in tasks[0:10]:
            TaskRunFactory.create_batch(10, task=t, project=project)

        # order by id ascending explicitly since default ordering is not supported in the model
        tasks = db.session.query(Task).filter_by(project_id=project.id, state='ongoing').order_by(Task.id).all()
        assert tasks[0].n_answers == 10

        url = 'api/project/%s/newtask?api_key=%s' % (project.id, owner.api_key)
        res = self.app.get(url)
        data = json.loads(res.data)

        err_msg = "User should get a task"
        assert 'project_id' in data.keys(), err_msg
        assert data['project_id'] == project_id, err_msg
        assert data['id'] == tasks[0].id, err_msg

    @with_context
    def test_no_more_tasks_limit(self):
        """Test that a users gets always tasks with limit"""
        owner = UserFactory.create()
        project = ProjectFactory.create(owner=owner, short_name='egil', name='egil',
                  description='egil')

        project_id = project.id

        tasks = TaskFactory.create_batch(20, project=project, n_answers=10)

        for t in tasks[0:10]:
            TaskRunFactory.create_batch(10, task=t, project=project)

        tasks = db.session.query(Task).filter_by(project_id=project.id, state='ongoing').order_by(Task.id).all()
        assert tasks[0].n_answers == 10

        url = 'api/project/%s/newtask?limit=2&orderby=id&api_key=%s' % (project_id, owner.api_key)
        res = self.app.get(url)
        data = json.loads(res.data)

        err_msg = "User should get a task"        
        assert 'project_id' in data.keys(), err_msg
        assert data['project_id'] == project_id, err_msg
        assert data['id'] == tasks[0].id, (err_msg, t, tasks[0].id)

    @with_context
    @patch('pybossa.sched.get_user_saved_partial_tasks')
    @patch('pybossa.view.projects.sentinel.master.get')
    def test_new_task_with_saved_task_position(self, sentinel_mock, task_id_map_mock):
        admin = UserFactory.create(admin=True)
        admin.set_password('1234')
        user_repo.save(admin)
        self.signin(email=admin.email_addr, password='1234')

        # Test locked_scheduler
        project = ProjectFactory.create(owner=admin, short_name='test', info={'sched':'locked_scheduler'})
        task1 = TaskFactory.create(project=project)
        task2 = TaskFactory.create(project=project)
        task3 = TaskFactory.create(project=project)
        task4 = TaskFactory.create(project=project)
        task5 = TaskFactory.create(project=project)

        # Simulate saved tasks
        task_id_map_mock.return_value = {task2.id: 1002, task4.id: 1004}

        url = f'/api/project/{project.id}/newtask'

        sentinel_mock.return_value = b'bad-value'
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 200, res.status_code

        sentinel_mock.return_value = b'first'
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 200, res.status_code
        assert res.json['id'] == task2.id

        sentinel_mock.return_value = b'last'
        res = self.app.get(url, follow_redirects=True)
        assert res.status_code == 200, res.status_code
        assert res.json['id'] == task1.id

