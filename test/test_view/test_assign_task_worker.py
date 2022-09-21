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
    def test_get_assign_workers_by_bulk(self):
        """Test get assign worker by bulk."""
        admin = UserFactory.create(admin=True)
        admin.set_password('1234')
        user_repo.save(admin)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        # Create a project with a worker assigned.
        user1 = UserFactory.create(email_addr='a1@a.com', fullname="test_user1")
        user2 = UserFactory.create(email_addr='a2@a.com', fullname="test_user2")
        project = ProjectFactory.create(published=True, info={'project_users': [user1.id, user2.id]})

        task1 = TaskFactory.create(project=project)
        task_repo.update(task1)
        task2 = TaskFactory.create(project=project)
        task_repo.update(task2)
        task3 = TaskFactory.create(project=project, gold_answers={'answer': 1})
        task_repo.update(task3)

        # Assign user to all tasks by filter.
        req_data = dict(filters='{"add":[{"fullname":"' + user1.fullname + '","email":"' + user1.email_addr + '"}],"remove":[]}')

        url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app.post(url, content_type='application/json', data=json.dumps(req_data), follow_redirects=True, headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify users are returned.
        assert len(res_data['all_users']) > 1
        assert res_data['all_users'][0]['email']

        # Verify emails are returned.
        emails = [user['email'] for user in res_data['all_users']]
        assert user1.email_addr in emails
        assert user2.email_addr in emails

        # Test bulk assign users: skip gold task
        req_data = {
            "add": [{"fullname": user1.fullname, "email": user1.email_addr}],
            "remove": [],
            "filters": json.dumps({"changed": False})}
        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(req_data), follow_redirects=True,
                            headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)
        assert len(res_data["assign_users"]) == 2

    @with_context
    def test_update_assign_workers_by_task_id(self):
        """Test update assign worker by task id."""
        admin = UserFactory.create(admin=True)
        admin.set_password('1234')
        user_repo.save(admin)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        project = ProjectFactory.create(published=True)
        user = UserFactory.create(email_addr='a@a.com', fullname="test_user")

        task1 = TaskFactory.create(project=project)
        task_repo.update(task1)

        # Assign user to task by task id.
        req_data = dict(taskId=str(task1.id), add=[{'email':user.email_addr}])

        url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app.post(url, content_type='application/json', data=json.dumps(req_data), follow_redirects=True, headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify the user has been assigned to this task.
        assert res_data['assign_users'][0]['taskId'] == task1.id
        assert res_data['assign_users'][0]['assign_user'][0] == user.email_addr

        task1_modified = task_repo.get_task(task1.id)
        assert user.email_addr in task1_modified.user_pref.get('assign_user')

    @with_context
    def test_update_assign_workers_by_filter(self):
        """Test update assign worker by filter."""
        admin = UserFactory.create(admin=True)
        admin.set_password('1234')
        user_repo.save(admin)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        project = ProjectFactory.create(published=True)
        user = UserFactory.create(email_addr='a@a.com', fullname="test_user")

        task1 = TaskFactory.create(project=project)
        task_repo.update(task1)

        # Assign user to task by filter.
        req_data = dict(filters='{"task_id": "' + str(task1.id) + '"}', add=[{'email':user.email_addr}])

        url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app.post(url, content_type='application/json', data=json.dumps(req_data), follow_redirects=True, headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        # Verify the user has been assigned to this task.
        assert res_data['assign_users'][0]['taskId'] == task1.id
        assert res_data['assign_users'][0]['assign_user'][0] == user.email_addr

        task1_modified = task_repo.get_task(task1.id)
        assert user.email_addr in task1_modified.user_pref.get('assign_user')

    @with_context
    def test_update_assign_workers_remove(self):
        """Test remove assigned worker."""
        admin = UserFactory.create(admin=True)
        admin.set_password('1234')
        user_repo.save(admin)

        csrf = self.get_csrf('/account/signin')
        self.signin(email=admin.email_addr, csrf=csrf)

        project = ProjectFactory.create(published=True)
        user = UserFactory.create(email_addr='a@a.com', fullname="test_user")

        task1_user_pref = dict(assign_user=[user.email_addr])

        # Create a task with an assigned user.
        task1 = TaskFactory.create(project=project,  user_pref=task1_user_pref)
        task_repo.update(task1)

        # Verify the user has been assigned to the task.
        assert user.email_addr in task1.user_pref.get('assign_user')

        # Load the task and verify the user has been assigned to the task.
        task1_modified1 = task_repo.get_task(task1.id)
        assert user.email_addr in task1_modified1.user_pref.get('assign_user')

        # Remove the user.
        req_data = dict(taskId=str(task1.id), remove=[{'email':user.email_addr}])

        url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app.post(url, content_type='application/json', data=json.dumps(req_data), follow_redirects=True, headers={'X-CSRFToken': csrf})
        res_data = json.loads(res.data)

        assert not res_data['assign_users']

        # Verify the assign_user parameter has been deleted from the user_pref.
        task1_modified2 = task_repo.get_task(task1.id)
        assert not task1_modified2.user_pref.get('assign_user')
