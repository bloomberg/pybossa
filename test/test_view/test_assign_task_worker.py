# -*- coding: utf8 -*-
import json

from pybossa.core import user_repo, task_repo
from test import with_context
from test.factories import ProjectFactory, TaskFactory, UserFactory
from test.helper import web


class TestAssignTaskWorker(web.Helper):

    @with_context
    def test_get_users_single_task_0(self):
        """Test a single task without assign_user."""
        project = ProjectFactory.create(published=True)
        task = TaskFactory.create(project=project)

        url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        req_data = dict(taskId=str(task.id))
        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(req_data))
        res_data = json.loads(res.data)
        assert not res_data['assign_users']
        assert len(res_data['all_users']) == len(user_repo.get_all())

    @with_context
    def test_get_users_single_task_1(self):
        """Test a single task with assign_user."""
        project = ProjectFactory.create(published=True)
        user = UserFactory.create(email_addr='a@a.com', fullname="test_user")
        task_user_pref = dict(assign_user=[user.email_addr])
        task = TaskFactory.create(project=project, user_pref=task_user_pref)

        url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        req_data = dict(taskId=str(task.id))
        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(req_data))
        res_data = json.loads(res.data)
        assert len(res_data['assign_users']) == 1, res_data['assign_users']
        assert res_data['assign_users'][0]['email'] == user.email_addr
        assert res_data['assign_users'][0]['fullname'] == user.fullname

        all_user_emails = [u['email'] for u in res_data['all_users']]
        assert user.email_addr not in all_user_emails, "existing users should be excluded from user list"

    @with_context
    def test_get_users_single_task_2(self):
        """Test a single task with assign_user invalid email addr."""
        project = ProjectFactory.create(published=True)
        user = UserFactory.create(email_addr='a@a.com', fullname="test_user")
        invalid_email_addr = "invalid@email"
        task_user_pref = dict(assign_user=[user.email_addr, invalid_email_addr])
        task = TaskFactory.create(project=project, user_pref=task_user_pref)

        url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        req_data = dict(taskId=str(task.id))
        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(req_data))
        res_data = json.loads(res.data)
        assert len(res_data['assign_users']) == 2, res_data['assign_users']

        all_user_emails = [u['email'] for u in res_data['all_users']]
        assert invalid_email_addr not in all_user_emails, "existing users should be excluded from user list"

    @with_context
    def test_get_users_bulk_task_0(self):
        """Test a bulk task without assign_user."""
        project = ProjectFactory.create(published=True)
        user = UserFactory.create(email_addr='a@a.com', fullname="test_user")

        task1_user_pref = dict(assign_user=[user.email_addr])

        task1 = TaskFactory.create(project=project,  user_pref=task1_user_pref)
        task2 = TaskFactory.create(project=project,  user_pref=task1_user_pref)
        task_repo.update(task1)
        task_repo.update(task2)

        url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        req_data = dict(taskId=None)
        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(req_data))
        res_data = json.loads(res.data)
        assert res_data['assign_users'][0]['fullname'] == user.fullname
        assert res_data['assign_users'][0]['email'] == user.email_addr


    @with_context
    def test_bulk_priority_update(self):
        """Test bulk priority update."""
        project = ProjectFactory.create(published=True)
        user = UserFactory.create(email_addr='a@a.com', fullname="test_user")

        task1_user_pref = dict(assign_user=[user.email_addr], priority_0=1)

        task1 = TaskFactory.create(project=project,  user_pref=task1_user_pref)
        task_repo.update(task1)
        req_data = dict(taskIds=str(task1.id), priority_0=0.5)

        url = '/project/%s/tasks/priorityupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(req_data))
        res_data = json.loads(res.data)
        assert task1.priority_0 == .5, task1.priority_0



    @with_context
    def test_update_assign_workers(self):
        """Test update assign worker."""
        project = ProjectFactory.create(published=True)
        user = UserFactory.create(email_addr='a@a.com', fullname="test_user")

        task1_user_pref = dict(assign_user=[user.email_addr])

        task1 = TaskFactory.create(project=project,  user_pref=task1_user_pref)
        task_repo.update(task1)
        req_data = dict(taskIds=str(task1.id), add=user)


        url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        req_data = dict(taskId=None)
        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(req_data))
        res_data = json.loads(res.data)
        assert res_data['assign_users'][0]['fullname'] == user.fullname
        assert res_data['assign_users'][0]['email'] == user.email_addr
