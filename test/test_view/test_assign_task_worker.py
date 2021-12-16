# -*- coding: utf8 -*-
import json
from mock import patch

from default import db, with_context
from factories import ProjectFactory, TaskFactory, UserFactory
from helper import web
from pybossa.repositories import ProjectRepository, TaskRepository, UserRepository

project_repo = ProjectRepository(db)
user_repo = UserRepository(db)
task_repo = TaskRepository(db)


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
        assert res_data['assign_users'][0]['email'] == invalid_email_addr
        assert res_data['assign_users'][0]['fullname'] == invalid_email_addr + " (user not found)"

        all_user_emails = [u['email'] for u in res_data['all_users']]
        assert invalid_email_addr not in all_user_emails, "existing users should be excluded from user list"


'''
bulk_priority_update() with and without task_ids,
 and one that calls bulk_update_assign_worker() for a specific task id and a bulk task id update

 REST call 
url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)

16:03:06 In fact, it looks like that test already calls bulk_update_assign_worker 
through /<name>/tasks/assign-workersupdate but you may just need to ensure all conditions in that code are hit.

16:04:33 Could also use a test to call get_tasks_by_filters()

res = self.app.get(url)

'''


    # @with_context
    # def test_get_users_multi_task_0(self):
    #     """Test a single task without assign_user."""
    #     project = ProjectFactory.create(published=True)
    #     task = TaskFactory.create(project=project)
    #     task = TaskFactory.create(project=project)

    #     url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
    #     req_data = dict(taskId=str(task.id))
    #     res = self.app.post(url, content_type='application/json',
    #       assign-workersupdate                  data=json.dumps(req_data))
    #     res_data = json.loads(res.data)
    #     assert not res_data['assign_users']
    #     assert len(res_data['all_users']) == len(user_repo.get_all())

    # @with_context
    # def test_get_users_multi_task_1(self):
    #     """Test a single task with assign_user."""
    #     project = ProjectFactory.create(published=True)
    #     user = UserFactory.create(email_addr='a@a.com', fullname="test_user")
    #     task_user_pref = dict(assign_user=[user.email_addr])
    #     task = TaskFactory.create(project=project, user_pref=json.dumps(task_user_pref))

    #     url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
    #     req_data = dict(taskId=str(task.id))
    #     res = self.app.post(url, content_type='application/json',
    #                         data=json.dumps(req_data))
    #     res_data = json.loads(res.data)
    #     assert len(res_data['assign_users']) == 1, res_data['assign_users']
    #     assert res_data['assign_users'][0]['email'] == user.email_addr
    #     assert res_data['assign_users'][0]['fullname'] == user.fullname

    #     all_user_emails = [u['email'] for u in res_data['all_users']]
    #     assert user.email_addr not in all_users_emails, "existing users should be excluded from user list"

    # @with_context
    # def test_get_users_single_task_2(self):
    #     """Test a single task with assign_user invalid email addr."""
    #     project = ProjectFactory.create(published=True)
    #     user = UserFactory.create(email_addr='a@a.com', fullname="test_user")
    #     invalid_email_addr = "invalid@email"
    #     task_user_pref = dict(assign_user=[user.email_addr, invalid_email_addr])
    #     task = TaskFactory.create(project=project, user_pref=json.dumps(task_user_pref))

    #     url = '/project/%s/tasks/assign-workersupdate?api_key=%s' % (project.short_name, project.owner.api_key)
    #     req_data = dict(taskId=str(task.id))
    #     res = self.app.post(url, content_type='application/json',
    #                         data=json.dumps(req_data))
    #     res_data = json.loads(res.data)
    #     assert len(res_data['assign_users']) == 2, res_data['assign_users']
    #     assert res_data['assign_users'][0]['email'] == user.email_addr
    #     assert res_data['assign_users'][0]['fullname'] == user.fullname

    #     all_user_emails = [u['email'] for u in res_data['all_users']]
    #     assert invalid_email_addr not in all_users_emails, "existing users should be excluded from user list"