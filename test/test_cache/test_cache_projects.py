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

from test import Test, with_context, with_request_context
from pybossa.cache import projects as cached_projects
from test.factories import UserFactory, ProjectFactory, TaskFactory, \
    TaskRunFactory, AnonymousTaskRunFactory, UserFactory
from unittest.mock import patch, call
import datetime
import json
from pybossa.core import result_repo, task_repo
from pybossa.model.project import Project
from pybossa.cache.project_stats import update_stats
from nose.tools import nottest, assert_raises
from pybossa.cache.task_browse_helpers import get_task_filters, parse_tasks_browse_args
import pybossa.cache.project_stats as stats
from pybossa.redis_lock import get_locked_tasks_project

class TestProjectsCache(Test):

    def create_project_with_tasks(self, completed_tasks, ongoing_tasks, gold_tasks=0):
        project = ProjectFactory.create()
        TaskFactory.create_batch(completed_tasks, state='completed', project=project)
        TaskFactory.create_batch(ongoing_tasks, state='ongoing', project=project)
        TaskFactory.create_batch(gold_tasks, calibration=1, project=project)
        return project

    def create_project_with_contributors(self, anonymous, registered,
                                     two_tasks=False, name='my_app', info={}):
        project = ProjectFactory.create(name=name, info=info)
        task = TaskFactory(project=project)
        if two_tasks:
            task2 = TaskFactory(project=project)
        for i in range(anonymous):
            task_run = AnonymousTaskRunFactory(task=task,
                               user_ip='127.0.0.%s' % i)
            if two_tasks:
                task_run2 = AnonymousTaskRunFactory(task=task2,
                               user_ip='127.0.0.%s' % i)
        for i in range(registered):
            user = UserFactory.create()
            task_run = TaskRunFactory(task=task, user=user)
            if two_tasks:
                task_run2 = TaskRunFactory(task=task2, user=user)
        return project


    @with_context
    def test_get_featured_only_returns_featured(self):
        """Test CACHE PROJECTS get_featured returns only featured projects"""

        featured_project = ProjectFactory.create(featured=True)
        non_featured_project = ProjectFactory.create()

        featured = cached_projects.get_featured()

        assert len(featured) == 1, featured


    @with_context
    def test_get_featured_returns_required_fields(self):
        """Test CACHE PROJECTS get_featured returns the required info
        about each featured project"""

        fields = ('id', 'name', 'short_name', 'info', 'created', 'description',
                  'last_activity', 'last_activity_raw', 'overall_progress',
                  'n_tasks', 'n_volunteers', 'owner', 'info', 'updated')

        ProjectFactory.create(featured=True)

        featured = cached_projects.get_featured()[0]

        for field in fields:
            assert field in featured, "%s not in project info" % field


    @with_context
    def test_get_only_return_published(self):
        """Test CACHE PROJECTS get returns only published projects"""

        project = ProjectFactory.create(published=True)
        ProjectFactory.create(category=project.category, published=False)
        projects = cached_projects.get(project.category.short_name)

        assert len(projects) == 1, projects


    @nottest
    @with_context
    def test_get_dont_return_projects_with_password(self):
        """Test CACHE PROJECTS get does not return projects with a password"""

        project = ProjectFactory.create(published=True, info={'passwd_hash': '2'})
        ProjectFactory.create(category=project.category, published=True)
        projects = cached_projects.get(project.category.short_name)

        assert len(projects) == 1, projects


    @with_context
    def test_get_only_returns_projects_from_category(self):
        """Test CACHE PROJECTS get returns only projects from required category"""

        project = ProjectFactory.create(published=True)
        ProjectFactory.create(published=True)

        projects = cached_projects.get(project.category.short_name)

        assert len(projects) == 1, projects


    @with_context
    def test_get_returns_required_fields(self):
        """Test CACHE PROJECTS get returns the required info
        about each project"""

        fields = ('id', 'name', 'short_name', 'info', 'created', 'description',
                  'last_activity', 'last_activity_raw', 'overall_progress',
                  'n_tasks', 'n_volunteers', 'owner', 'info', 'updated')

        project = ProjectFactory.create(published=True)

        retrieved_project = cached_projects.get(project.category.short_name)[0]

        for field in fields:
            assert field in retrieved_project, "%s not in project info" % field


    @with_context
    def test_get_draft_not_returns_published_projects(self):
        """Test CACHE PROJECTS get_draft does not return published projects"""

        published = ProjectFactory.create(published=True)

        drafts = cached_projects.get_draft()

        assert len(drafts) == 0, drafts


    @with_context
    def test_get_draft_returns_required_fields(self):
        """Test CACHE PROJECTS get_draft returns the required info
        about each project"""

        fields = Project().public_attributes()

        ProjectFactory.create(published=False)

        draft = cached_projects.get_draft()[0]

        for field in fields:
            assert field in draft, "%s not in project info" % field
            if field == 'info':
                assert sorted(draft['info'].keys()) == sorted(Project().public_info_keys())

    @with_request_context
    def test_get_top_returns_projects_with_most_taskruns(self):
        """Test CACHE PROJECTS get_top returns the projects with most taskruns in order"""

        ranked_3_project = self.create_project_with_contributors(8, 0, name='three')
        ranked_2_project = self.create_project_with_contributors(9, 0, name='two')
        ranked_1_project = self.create_project_with_contributors(10, 0, name='one')
        ranked_4_project = self.create_project_with_contributors(7, 0, name='four')

        stats.update_stats(ranked_3_project.id)
        stats.update_stats(ranked_2_project.id)
        stats.update_stats(ranked_1_project.id)
        stats.update_stats(ranked_4_project.id)

        top_projects = cached_projects.get_top()

        assert top_projects[0]['name'] == 'one', top_projects
        assert top_projects[1]['name'] == 'two', top_projects
        assert top_projects[2]['name'] == 'three', top_projects
        assert top_projects[3]['name'] == 'four', top_projects

    @with_request_context
    def test_get_top_respects_limit(self):
        """Test CACHE PROJECTS get_top returns only the top n projects"""

        ranked_3_project = self.create_project_with_contributors(8, 0, name='three')
        ranked_2_project = self.create_project_with_contributors(9, 0, name='two')
        ranked_1_project = self.create_project_with_contributors(10, 0, name='one')

        stats.update_stats(ranked_3_project.id)
        stats.update_stats(ranked_2_project.id)
        stats.update_stats(ranked_1_project.id)

        top_projects = cached_projects.get_top(n=2)

        assert len(top_projects) == 2, len(top_projects)

    @with_request_context
    def test_get_top_returns_not_only_projects_without_password(self):
        """Test CACHE PROJECTS get_top returns projects that don't have a password"""

        ranked_2_project = self.create_project_with_contributors(9, 0, name='two')
        ranked_1_project = self.create_project_with_contributors(
            10, 0, name='one', info={'passwd_hash': 'something'})

        stats.update_stats(ranked_2_project.id)
        stats.update_stats(ranked_1_project.id)

        top_projects = cached_projects.get_top()

        assert len(top_projects) == 2, len(top_projects)

    @with_context
    def test_n_completed_tasks_no_completed_tasks(self):
        """Test CACHE PROJECTS n_completed_tasks returns 0 if no completed tasks"""

        project = self.create_project_with_tasks(completed_tasks=0, ongoing_tasks=5)
        completed_tasks = cached_projects.n_completed_tasks(project.id)

        err_msg = "Completed tasks is %s, it should be 0" % completed_tasks
        assert completed_tasks == 0, err_msg


    @with_context
    def test_n_completed_tasks_with_completed_tasks(self):
        """Test CACHE PROJECTS n_completed_tasks returns number of completed tasks
        if there are any"""

        project = self.create_project_with_tasks(completed_tasks=5, ongoing_tasks=5)
        completed_tasks = cached_projects.n_completed_tasks(project.id)

        err_msg = "Completed tasks is %s, it should be 5" % completed_tasks
        assert completed_tasks == 5, err_msg


    @with_context
    def test_n_completed_tasks_with_all_tasks_completed(self):
        """Test CACHE PROJECTS n_completed_tasks returns number of tasks if all
        tasks are completed"""

        project = self.create_project_with_tasks(completed_tasks=4, ongoing_tasks=0)
        completed_tasks = cached_projects.n_completed_tasks(project.id)

        err_msg = "Completed tasks is %s, it should be 4" % completed_tasks
        assert completed_tasks == 4, err_msg


    @with_context
    def test_n_tasks_returns_number_of_total_tasks(self):
        project = self.create_project_with_tasks(completed_tasks=1, ongoing_tasks=1)

        tasks = cached_projects.n_tasks(project.id)

        assert tasks == 2, tasks


    @with_context
    def test_n_task_runs_returns_number_of_total_taskruns(self):
        project = self.create_project_with_contributors(anonymous=1, registered=1)

        taskruns = cached_projects.n_task_runs(project.id)

        assert taskruns == 2, taskruns


    @with_context
    def notest_n_results_returns_number_of_total_results(self):
        project = ProjectFactory.create()
        task = TaskFactory.create(n_answers=1, project=project)
        TaskRunFactory.create(task=task, project=project)

        results = cached_projects.n_results(project.id)

        assert results == 0, results

        result = result_repo.get_by(project_id=project.id)

        result.info = dict(foo='bar')

        result_repo.update(result)

        results = cached_projects.n_results(project.id)

        assert results == 1, results


    @with_context
    def test_n_registered_volunteers(self):
        """Test CACHE PROJECTS n_registered_volunteers returns number of volunteers
        that contributed to a project when each only submited one task run"""

        project = self.create_project_with_contributors(anonymous=0, registered=3)
        registered_volunteers = cached_projects.n_registered_volunteers(project.id)

        err_msg = "Volunteers is %s, it should be 3" % registered_volunteers
        assert registered_volunteers == 3, err_msg


    @with_context
    def test_n_registered_volunteers_with_more_than_one_taskrun(self):
        """Test CACHE PROJECTS n_registered_volunteers returns number of volunteers
        that contributed to a project when any submited more than one task run"""

        project = self.create_project_with_contributors(anonymous=0, registered=2, two_tasks=True)
        registered_volunteers = cached_projects.n_registered_volunteers(project.id)

        err_msg = "Volunteers is %s, it should be 2" % registered_volunteers
        assert registered_volunteers == 2, err_msg


    @with_context
    def test_n_anonymous_volunteers(self):
        """Test CACHE PROJECTS n_anonymous_volunteers returns number of volunteers
        that contributed to a project when each only submited one task run"""

        project = self.create_project_with_contributors(anonymous=3, registered=0)
        anonymous_volunteers = cached_projects.n_anonymous_volunteers(project.id)

        err_msg = "Volunteers is %s, it should be 3" % anonymous_volunteers
        assert anonymous_volunteers == 3, err_msg


    @with_context
    def test_n_anonymous_volunteers_with_more_than_one_taskrun(self):
        """Test CACHE PROJECTS n_anonymous_volunteers returns number of volunteers
        that contributed to a project when any submited more than one task run"""

        project = self.create_project_with_contributors(anonymous=2, registered=0, two_tasks=True)
        anonymous_volunteers = cached_projects.n_anonymous_volunteers(project.id)

        err_msg = "Volunteers is %s, it should be 2" % anonymous_volunteers
        assert anonymous_volunteers == 2, err_msg


    @with_context
    def test_n_volunteers(self):
        """Test CACHE PROJECTS n_volunteers returns the sum of the anonymous
        plus registered volunteers that contributed to a project"""

        project = self.create_project_with_contributors(anonymous=2, registered=3, two_tasks=True)
        total_volunteers = cached_projects.n_volunteers(project.id)

        err_msg = "Volunteers is %s, it should be 5" % total_volunteers
        assert total_volunteers == 5, err_msg


    @with_context
    def test_n_draft_no_drafts(self):
        """Test CACHE PROJECTS _n_draft returns 0 if there are no draft projects"""
        project = ProjectFactory.create(published=True)

        number_of_drafts = cached_projects._n_draft()

        assert number_of_drafts == 0, number_of_drafts


    @with_context
    def test_n_draft_with_drafts(self):
        """Test CACHE PROJECTS _n_draft returns 2 if there are 2 draft projects"""
        ProjectFactory.create_batch(2, published=False)

        number_of_drafts = cached_projects._n_draft()

        assert number_of_drafts == 2, number_of_drafts


    @with_context
    def test_browse_tasks_returns_no_tasks(self):
        """Test CACHE PROJECTS browse_tasks returns an empty list if a project
        has no tasks"""

        project = ProjectFactory.create()

        count, browse_tasks = cached_projects.browse_tasks(project.id, {})

        assert browse_tasks == [], browse_tasks


    @with_context
    def test_browse_tasks_returns_all_tasks(self):
        """Test CACHE PROJECTS browse_tasks returns a list with all the tasks
        from a given project"""

        project = ProjectFactory.create()
        TaskFactory.create_batch(2, project=project)

        count, browse_tasks = cached_projects.browse_tasks(project.id, {})

        assert len(browse_tasks) == 2, browse_tasks


    @with_context
    def test_browse_tasks_returns_required_attributes(self):
        """Test CACHE PROJECTS browse_tasks returns a list with objects
        with the required task attributes"""

        project = ProjectFactory.create()
        task = TaskFactory.create( project=project, info={})
        attributes = ('id', 'n_answers')

        count, cached_tasks = cached_projects.browse_tasks(project.id, {})
        cached_task = cached_tasks[0]

        for attr in attributes:
            assert cached_task.get(attr) == getattr(task, attr), attr


    @with_context
    def test_browse_tasks_returns_pct_status(self):
        """Test CACHE PROJECTS browse_tasks returns also the completion
        percentage of each task"""

        project = ProjectFactory.create()
        task = TaskFactory.create( project=project, info={}, n_answers=4)

        count, cached_tasks = cached_projects.browse_tasks(project.id, {})
        # 0 if no task runs
        assert cached_tasks[0].get('pct_status') == 0, cached_tasks[0].get('pct_status')

        TaskRunFactory.create(task=task)
        count, cached_tasks = cached_projects.browse_tasks(project.id, {})
        # Gets updated with new task runs
        assert cached_tasks[0].get('pct_status') == 0.25, cached_tasks[0].get('pct_status')

        TaskRunFactory.create_batch(3, task=task)
        count, cached_tasks = cached_projects.browse_tasks(project.id, {})
        # To a maximum of 1
        assert cached_tasks[0].get('pct_status') == 1.0, cached_tasks[0].get('pct_status')

        TaskRunFactory.create(task=task)
        count, cached_tasks = cached_projects.browse_tasks(project.id, {})
        # And it does not go over 1 (that is 100%!!)
        assert cached_tasks[0].get('pct_status') == 1.0, cached_tasks[0].get('pct_status')


    @with_context
    @patch('pybossa.cache.projects.get_locked_tasks_project')
    def test_browse_tasks_sort_by_task_locks(self, locks):
        """Test CACHE PROJECTS browse_tasks returns tasks sorted by lock_status"""

        owner = UserFactory.create(id=500)
        project = ProjectFactory.create(owner=owner, short_name="testproject")
        tasks = TaskFactory.create_batch(2, project=project, n_answers=2)

        locks.return_value = [{"task_id": str(tasks[0].id), "user_id": owner.id}]

        count, cached_tasks = cached_projects.browse_tasks(project.id, {"order_by": "lock_status asc"})
        assert count == 2
        assert cached_tasks[1]["id"] == tasks[0].id

        count, cached_tasks = cached_projects.browse_tasks(project.id, {"order_by": "lock_status desc"})
        assert count == 2
        assert cached_tasks[0]["id"] == tasks[0].id


    @with_context
    @patch('pybossa.cache.projects.get_user_saved_partial_tasks')
    def test_browse_tasks_sort_by_saved_tasks(self, task_id_map_mock):
        """Test CACHE PROJECTS browse_tasks returns tasks sorted by earliest saved tasks"""

        owner = UserFactory.create(id=500)
        project = ProjectFactory.create(owner=owner, short_name="testproject")
        tasks = TaskFactory.create_batch(2, project=project, n_answers=2)

        task_id_map_mock.return_value = {tasks[1].id : 1001}  # return task1 first

        user_profile = {"finance": 0.6}
        args = dict(filter_by_wfilter_upref={"current_user_pref": {},
                                             "current_user_email": "user@user.com",
                                             "current_user_profile": user_profile},
                    sql_params=dict(assign_user=json.dumps({'assign_user': ["user@user.com"]})))
        count, cached_tasks = cached_projects.browse_tasks(project.id, args, filter_user_prefs=True)
        assert count == 2
        assert cached_tasks[0]["id"] == tasks[1].id


    @with_context
    @patch('pybossa.cache.projects.get_user_saved_partial_tasks')
    def test_browse_tasks_sort_by_in_progress(self, task_id_map_mock):
        """
        Test CACHE PROJECTS browse_tasks returns tasks sorted by in
        progress values("Yes", "No" and "All")
        """

        owner = UserFactory.create(id=500)
        project = ProjectFactory.create(owner=owner, short_name="testproject")
        tasks = TaskFactory.create_batch(3, project=project, n_answers=2)
        tasks[2].priority_0 = 1.0
        task_repo.save(tasks[2])

        task_id_map_mock.return_value = None

        user_profile = {"finance": 0.6}
        args = dict(filter_by_wfilter_upref={"current_user_pref": {},
                                             "current_user_email": "user@user.com",
                                             "current_user_profile": user_profile},
                    sql_params=dict(assign_user=json.dumps({'assign_user': ["user@user.com"]})))

        args["order_by"] = "in_progress asc"
        count, cached_tasks = cached_projects.browse_tasks(project.id, args, filter_user_prefs=True)
        assert count == 3
        assert cached_tasks[0]["id"] == tasks[2].id # sort by priority - 3rd task first

        args["order_by"] = "in_progress desc"
        count, cached_tasks = cached_projects.browse_tasks(project.id, args, filter_user_prefs=True)
        assert count == 3
        assert cached_tasks[0]["id"] == tasks[2].id  # sort by priority - 3rd task first

        args["order_by"] = "id asc, in_progress desc"
        count, cached_tasks = cached_projects.browse_tasks(project.id, args, filter_user_prefs=True)
        assert count == 3
        assert cached_tasks[0]["id"] == tasks[0].id  # sort by priority - 1st task first

        args["order_by"] = "in_progress desc, id asc"
        count, cached_tasks = cached_projects.browse_tasks(project.id, args, filter_user_prefs=True)
        assert count == 3
        assert cached_tasks[0]["id"] == tasks[0].id  # sort by priority - 1st task first

        args["order_by"] = "id asc, in_progress desc, priority_0 desc"
        count, cached_tasks = cached_projects.browse_tasks(project.id, args, filter_user_prefs=True)
        assert count == 3
        assert cached_tasks[0]["id"] == tasks[0].id  # sort by priority - 1st task first

    @with_context
    @patch('pybossa.cache.projects.get_user_saved_partial_tasks')
    def test_browse_tasks_filter_by_in_progress(self, task_id_map_mock):
        """
        Test CACHE PROJECTS browse_tasks returns tasks filtered by in
        progress values("Yes", "No" and "All")
        """

        owner = UserFactory.create(id=500)
        project = ProjectFactory.create(owner=owner, short_name="testproject")
        tasks = TaskFactory.create_batch(5, project=project, n_answers=2)

        task_id_map_mock.return_value = {tasks[2].id: 1002, tasks[4].id: 1004}

        user_profile = {"finance": 0.6}
        args = dict(filter_by_wfilter_upref={"current_user_pref": {},
                                             "current_user_email": "user@user.com",
                                             "current_user_profile": user_profile},
                    sql_params=dict(assign_user=json.dumps({'assign_user': ["user@user.com"]})))

        # filter the 'Yes' in progress task
        args["in_progress"] = "Yes"
        count, cached_tasks = cached_projects.browse_tasks(project.id, args, filter_user_prefs=True)
        assert count == 2
        assert cached_tasks[0]["id"] == tasks[2].id
        assert cached_tasks[1]["id"] == tasks[4].id

        # filter the 'No' in progress task
        args["in_progress"] = "No"
        count, cached_tasks = cached_projects.browse_tasks(project.id, args, filter_user_prefs=True)
        assert count == 3
        assert cached_tasks[0]["id"] == tasks[0].id
        assert cached_tasks[1]["id"] == tasks[1].id
        assert cached_tasks[2]["id"] == tasks[3].id


    @with_context
    def test_browse_tasks_returns_filtered_tasks_for_workers_0(self):
        """Test CACHE PROJECTS browse_tasks returns a subset of tasks
        from a given project"""

        project = ProjectFactory.create()
        tasks = TaskFactory.create_batch(2, project=project)
        tasks[0].worker_filter = {'finance': [0.4, '>=']}
        task_repo.save(tasks[0])
        tasks[1].worker_filter = {'finance': [0.9, '>=']}
        task_repo.save(tasks[1])

        user_profile = {"finance": 0.6}
        user_info = dict(metadata={"profile": json.dumps(user_profile)})
        user = UserFactory.create(id=500, info=user_info)

        args = dict(filter_by_wfilter_upref={"current_user_pref": {}, "current_user_email": "user@user.com", "current_user_profile": user_profile},
                    sql_params=dict(assign_user=json.dumps({'assign_user': ["user@user.com"]})))

        count, browse_tasks = cached_projects.browse_tasks(project.id, args, True, user.id)

        assert len(browse_tasks) == 1, browse_tasks
        assert browse_tasks[0]["id"] == tasks[0].id, "task[1] does not match users profile"


    @with_context
    def test_browse_tasks_returns_filtered_tasks_for_workers_1(self):
        """Test CACHE PROJECTS browse_tasks returns a subset of tasks
        from a given project"""

        project = ProjectFactory.create()
        tasks = TaskFactory.create_batch(2, project=project, n_answers=1)
        task_run = TaskRunFactory.create(task=tasks[0])

        user_profile = {"finance": 0.6}
        user_info = dict(metadata={"profile": json.dumps(user_profile)})
        user = UserFactory.create(id=500, info=user_info)

        args = dict(filter_by_wfilter_upref={"current_user_pref": {}, "current_user_email": "user@user.com", "current_user_profile": user_profile},
                    sql_params=dict(assign_user=json.dumps({'assign_user': ["user@user.com"]})))

        count, browse_tasks = cached_projects.browse_tasks(project.id, args, True, user.id)

        assert len(browse_tasks) == 1, "complete tasks should not be shown"
        assert browse_tasks[0]["id"] == tasks[1].id, "complete task tasks[0] should not be shown"


    @with_context
    def test_browse_tasks_returns_filtered_sorted_tasks_for_workers_0(self):
        """Test CACHE PROJECTS browse_tasks returns a subset of tasks
        from a given project and by default sort based on user profile"""

        project = ProjectFactory.create()
        tasks = TaskFactory.create_batch(2, project=project)
        tasks[1].worker_pref = {'spanish': 0.9}
        task_repo.save(tasks[1])

        user_profile = {"spanish": 0.4}
        user_info = dict(metadata={"profile": json.dumps(user_profile)})
        user = UserFactory.create(id=500, info=user_info)

        args = dict(filter_by_wfilter_upref={"current_user_pref": {}, "current_user_email": "user@user.com", "current_user_profile": user_profile},
            sql_params=dict(assign_user=json.dumps({'assign_user': ["user@user.com"]})))


        count, browse_tasks = cached_projects.browse_tasks(project.id, args, True, user.id)

        assert len(browse_tasks) == 2
        assert browse_tasks[0]["id"] == tasks[1].id, "the second task should come first as it matches user profile"


    @with_context
    def test_browse_tasks_returns_filtered_sorted_tasks_for_workers_1(self):
        """Test CACHE PROJECTS browse_tasks returns a subset of tasks
        from a given project and sort based on arguments"""

        project = ProjectFactory.create()
        tasks = TaskFactory.create_batch(3, project=project)
        tasks[1].worker_pref = {'spanish': 0.9}
        task_repo.save(tasks[1])
        tasks[2].priority_0 = 1.0
        task_repo.save(tasks[2])

        user_profile = {"spanish": 0.4}
        user_info = dict(metadata={"profile": json.dumps(user_profile)})
        user = UserFactory.create(id=500, info=user_info)

        args = dict(filter_by_wfilter_upref={"current_user_pref": {}, "current_user_email": "user@user.com", "current_user_profile": user_profile},
            sql_params=dict(assign_user=json.dumps({'assign_user': ["user@user.com"]})))
        args["order_by"] = "priority_0 DESC"

        count, browse_tasks = cached_projects.browse_tasks(project.id, args, True, user.id)

        assert len(browse_tasks) == 3
        assert browse_tasks[0]["id"] == tasks[2].id, "the third task should come first as it sorts by priority"

    @with_context
    def test_browse_tasks_grey_out_unavailable_tasks_for_workers_0(self):
        """Test CACHE PROJECTS browse_tasks returns a subset of tasks
        from a given project"""

        admin, owner, user = UserFactory.create_batch(3)
        category_config = ["field_1", "field_2"]
        project = ProjectFactory.create(
            zip_download=True, owner=admin,
            info=dict(
                sched="task_queue_scheduler",
                reserve_tasks=dict(
                    category=category_config
                )
            )
        )
        tasks = TaskFactory.create_batch(3, project=project, info=dict(field_1=1, field_2=2))

        reserve_filter = " AND (task.info->>'field_1' = '1' AND task.info->>'field_2' = '2') IS NOT TRUE"
        filter_by_wfilter_upref = dict(current_user_pref={},
                                        current_user_email="user@user.com",
                                        current_user_profile={},
                                        reserve_filter=reserve_filter)
        args = dict(filter_by_wfilter_upref=filter_by_wfilter_upref,
                    sql_params=dict(assign_user=json.dumps({'assign_user': ["user@user.com"]})))

        count, browse_tasks = cached_projects.browse_tasks(project.id, args, True, user.id)

        assert len(browse_tasks) == 3, browse_tasks
        assert all(not t["available"] for t in browse_tasks), "all tasks is unavailable for user"


    @with_context
    def test_n_featured_returns_nothing(self):
        """Test CACHE PROJECTS _n_featured 0 if there are no featured projects"""
        number_of_featured = cached_projects._n_featured()

        assert number_of_featured == 0, number_of_featured


    @with_context
    def test_n_featured_returns_featured(self):
        """Test CACHE PROJECTS _n_featured returns number of featured projects"""
        ProjectFactory.create(featured=True)

        number_of_featured = cached_projects._n_featured()

        assert number_of_featured == 1, number_of_featured


    @with_context
    @patch('pybossa.cache.pickle')
    @patch('pybossa.cache.projects._n_draft')
    def test_n_count_calls_n_draft(self, _n_draft, pickle):
        """Test CACHE PROJECTS n_count calls _n_draft when called with argument
        'draft'"""
        pickle.dumps.return_value = 'str'
        cached_projects.n_count('draft')
        _n_draft.assert_called_with()


    @with_context
    @patch('pybossa.cache.pickle')
    @patch('pybossa.cache.projects._n_featured')
    def test_n_count_calls_n_featuredt(self, _n_featured, pickle):
        """Test CACHE PROJECTS n_count calls _n_featured when called with
        argument 'featured'"""
        pickle.dumps.return_value = 'str'
        cached_projects.n_count('featured')
        _n_featured.assert_called_with()


    @with_context
    def test_n_count_with_different_category(self):
        """Test CACHE PROJECTS n_count returns 0 if there are no published
        projects from requested category"""
        project = self.create_project_with_tasks(1, 0)

        n_projects = cached_projects.n_count('nocategory')

        assert n_projects == 0, n_projects


    @with_context
    def test_n_count_with_published_projects(self):
        """Test CACHE PROJECTS n_count returns the number of published projects
        of a given category"""
        project = ProjectFactory.create(published=True)
        ProjectFactory.create(published=True)
        ProjectFactory.create(category=project.category, published=False)

        n_projects = cached_projects.n_count(project.category.short_name)

        assert n_projects == 1, n_projects


    @nottest
    @with_context
    def test_n_count_with_password_protected_projects(self):
        """Test CACHE PROJECTS n_count returns the number of published projects
        of a given category, excluding projects with a password"""
        project = ProjectFactory.create(published=True, info={'passwd_hash': '2'})
        ProjectFactory.create(category=project.category, published=True)

        n_projects = cached_projects.n_count(project.category.short_name)

        assert n_projects == 1, n_projects


    @with_context
    def test_get_from_pro_user_projects_no_projects(self):
        """Test CACHE PROJECTS get_from_pro_user returns empty list if no projects
        with 'pro' owners"""
        pro_user = UserFactory.create(pro=True)
        ProjectFactory.create()

        pro_owned_projects = cached_projects.get_from_pro_user()

        assert pro_owned_projects == [], pro_owned_projects


    @with_context
    def test_get_from_pro_user_projects(self):
        """Test CACHE PROJECTS get_from_pro_user returns list of projects with
        'pro' owners only"""
        pro_user = UserFactory.create(pro=True)
        ProjectFactory.create()
        pro_project = ProjectFactory.create(owner=pro_user)

        pro_owned_projects = cached_projects.get_from_pro_user()

        assert len(pro_owned_projects) == 1, len(pro_owned_projects)
        assert pro_owned_projects[0]['short_name'] == pro_project.short_name


    @with_context
    def test_get_from_pro_users_returns_required_fields(self):
        """Test CACHE PROJECTS get_from_pro_user returns required fields"""
        pro_user = UserFactory.create(pro=True)
        ProjectFactory.create(owner=pro_user)
        fields = ('id', 'short_name')

        pro_owned_projects = cached_projects.get_from_pro_user()

        for field in fields:
            assert field in pro_owned_projects[0].keys(), field


    @with_context
    def test_overall_progress_returns_0_if_no_tasks(self):
        project = ProjectFactory.create()

        progress = cached_projects.overall_progress(project.id)

        assert progress == 0, progress


    @with_context
    def test_overall_progres_returns_actual_progress_percentage(self):
        total_tasks = 4
        completed_tasks = 2
        project = self.create_project_with_tasks(
                            completed_tasks=completed_tasks,
                            ongoing_tasks=total_tasks-completed_tasks)

        progress = cached_projects.overall_progress(project.id)

        assert progress == 50, progress


    @with_context
    def test_overall_progress_excludes_gold(self):
        total_tasks = 4
        completed_tasks = 2
        gold_tasks = 2
        project = self.create_project_with_tasks(
                            completed_tasks=completed_tasks,
                            ongoing_tasks=total_tasks-completed_tasks,
                            gold_tasks=gold_tasks)

        progress = cached_projects.overall_progress(project.id)

        assert len(project.tasks) == total_tasks + gold_tasks
        assert progress == 50, progress


    @with_context
    def test_last_activity_returns_None_if_no_contributions(self):
        project = ProjectFactory.create()

        activity = cached_projects.last_activity(project.id)

        assert activity is None, activity


    @with_context
    def test_last_activity_returns_date_of_latest_contribution(self):
        project = ProjectFactory.create()
        first_task_run = TaskRunFactory.create(project=project)
        last_task_run = TaskRunFactory.create(project=project)

        activity = cached_projects.last_activity(project.id)

        assert activity == last_task_run.finish_time, last_task_run


    @with_context
    def test_n_published_counts_published_projects(self):
        published_project = ProjectFactory.create_batch(2, published=True)
        ProjectFactory.create(published=False)

        number_of_published = cached_projects.n_published()

        assert number_of_published == 2, number_of_published


    @with_context
    def test_average_contribution_time_returns_0_if_no_contributions(self):
        project = ProjectFactory.create()

        average_time = cached_projects.average_contribution_time(project.id)

        assert average_time == 0, average_time

    @with_request_context
    def test_average_contribution_time_returns_average_contribution_time(self):
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project)
        first_task_time = datetime.timedelta(0, 5)
        second_task_time = datetime.timedelta(0, 7)
        expected_average_time = datetime.timedelta(0, 6)
        now = datetime.datetime.utcnow()
        TaskRunFactory.create(task=task, created=now, finish_time=now+first_task_time)
        TaskRunFactory.create(task=task, created=now, finish_time=now+second_task_time)
        update_stats(project.id)
        average_time = cached_projects.average_contribution_time(project.id)

        assert average_time == expected_average_time.total_seconds(), average_time

    def test_parse_tasks_browse_args_raise_exception(self):
        """Test parse_tasks_browse_args raise exception"""
        args = dict(in_progress='Bad')
        assert_raises(ValueError, parse_tasks_browse_args, args)

    def test_parse_tasks_browse_args_assign_user(self):
        """Test parse_tasks_browse_args for assign_user"""
        args = dict(assign_user='worker')
        result = parse_tasks_browse_args(args)

        assert 'assign_user' in result

    @with_context
    @patch('pybossa.cache.task_browse_helpers.map_locations')
    @patch('pybossa.cache.task_browse_helpers.app_settings.upref_mdata.get_valid_user_preferences')
    @patch('pybossa.cache.task_browse_helpers.app_settings.upref_mdata')
    def test_task_browse_user_pref_args_no_upref_mdata_config(self, upref_mdata, get_valid_user_preferences, map_locations):
        """Test task browse user preference without user_pref settings loaded under pybossa.core.upref_mdata_choices"""
        args = dict(
            task_id=12345, pcomplete_from=0,
            pcomplete_to=50,hide_completed='true',
            created_from='2018-01-24T19:49:21.799870',
            created_to='2018-01-24T19:49:21.799870',
            ftime_from='2018-01-24T19:49:21.799870',
            ftime_to='2018-01-24T19:49:21.799870',
            priority_from=0, priority_to=0.5,
            display_columns='["task_id", "priority"]',display_info_columns='["co_id"]',
            filter_by_upref='{"languages": ["English"], "locations": ["Fiji"]}',
            in_progress='Yes')

        valid_args = dict(
            task_id=12345,
            pcomplete_from=0.0,
            pcomplete_to=0.5,
            hide_completed=True,
            created_from='2018-01-24T19:49:21.799870',
            created_to='2018-01-24T19:49:21.799870',
            ftime_from='2018-01-24T19:49:21.799870',
            ftime_to='2018-01-24T19:49:21.799870',
            priority_from=0.0,
            priority_to=0.5, order_by_dict={},
            display_columns=['task_id', 'priority'], display_info_columns=['co_id'],
            filter_by_upref={'languages': ['English'], 'locations': ['Fiji']},
            in_progress='Yes')

        get_valid_user_preferences.return_value = {}
        map_locations.return_value = {
            'locations': ['Fiji']
        }
        pargs = parse_tasks_browse_args(args)
        assert pargs == valid_args, pargs

    @with_context
    @patch('pybossa.cache.task_browse_helpers.map_locations')
    @patch('pybossa.cache.task_browse_helpers.app_settings.upref_mdata.get_valid_user_preferences')
    @patch('pybossa.cache.task_browse_helpers.app_settings.upref_mdata')
    def test_task_browse_user_pref_args(self, upref_mdata, get_valid_user_preferences, map_locations):
        """Test task browse user preference works with valid user_pref settings"""
        get_valid_user_preferences.return_value = dict(languages=["en", "sp"],
                                    locations=["us", "uk"])
        args = dict(
            task_id=12345, pcomplete_from=0,
            pcomplete_to=50,hide_completed='true',
            created_from='2018-01-24T19:49:21.799870',
            created_to='2018-01-24T19:49:21.799870',
            ftime_from='2018-01-24T19:49:21.799870',
            ftime_to='2018-01-24T19:49:21.799870',
            priority_from=0, priority_to=0.5,
            display_columns='["task_id", "priority"]',display_info_columns='["co_id"]',
            filter_by_upref='{"languages": ["en"], "locations": ["us"]}')

        valid_args = dict(
            task_id=12345,
            pcomplete_from=0.0,
            pcomplete_to=0.5,
            hide_completed=True,
            created_from='2018-01-24T19:49:21.799870',
            created_to='2018-01-24T19:49:21.799870',
            ftime_from='2018-01-24T19:49:21.799870',
            ftime_to='2018-01-24T19:49:21.799870',
            priority_from=0.0,
            priority_to=0.5, order_by_dict={},
            display_columns=['task_id', 'priority'], display_info_columns=['co_id'],
            filter_by_upref={'languages': ['en'], 'locations': ['us']})

        map_locations.return_value = {
            'locations': ['us']
        }

        pargs = parse_tasks_browse_args(args)
        assert pargs == valid_args, pargs

    @with_context
    def test_task_browse_get_task_filters(self):
        filters = dict(task_id=1,hide_completed=True,pcomplete_from='0.5',
            pcomplete_to='0.7', priority_from=0.0, priority_to=0.5,
            created_from='2018-01-01T00:00:00.0001', created_to='2018-12-12T00:00:00.0001',
            ftime_from='2018-01-01T00:00:00.0001', ftime_to='2018-12-12T00:00:00.0001',
            order_by='task_id', filter_by_field=[('CompanyName', 'starts with', 'abc')],
            filter_by_upref=dict(languages=['en'], locations=['us']), state='ongoing')
        expected_filter_query = ''' AND task.id = :task_id AND task.state=\'ongoing\' AND (coalesce(ct, 0)/float4(task.n_answers)) >= :pcomplete_from AND LEAST(coalesce(ct, 0)/float4(task.n_answers), 1.0) <= :pcomplete_to AND priority_0 >= :priority_from AND priority_0 <= :priority_to AND task.created >= :created_from AND task.created <= :created_to AND ft >= :ftime_from AND ft <= :ftime_to AND state = :state AND (COALESCE(task.info->>\'CompanyName\', \'\') ilike :filter_by_field_0 escape \'\\\') AND ( ( (task.user_pref-> \'locations\' IS NULL AND task.user_pref-> \'languages\' IS NULL) OR (task.user_pref @> \'{"languages": ["en"]}\' OR task.user_pref @> \'{"locations": ["us"]}\') ) )'''
        expected_params = {'task_id': 1, 'pcomplete_from': '0.5', 'pcomplete_to': '0.7', 'ftime_to': '2018-12-12T05:00:00.000100+00:00', 'created_from': '2018-01-01T05:00:00.000100+00:00', 'ftime_from': '2018-01-01T05:00:00.000100+00:00', 'state':'ongoing', 'priority_to': 0.5, 'priority_from': 0.0, 'filter_by_field_0': 'abc%', 'created_to': '2018-12-12T05:00:00.000100+00:00'}

        filters, params = get_task_filters(filters)
        assert filters == expected_filter_query, filters
        assert params == expected_params, params

        # with allow_taskrun_edit, user submitted responses to be returned
        user_submitted_responses = "(SELECT 1 FROM task_run WHERE project_id=:project_id AND\n        user_id=:user_id AND task_id=task.id)"
        expected_user_id = 239
        filters = dict(task_id=1, allow_taskrun_edit=True, order_by='task_id', user_id=expected_user_id)
        filters, params = get_task_filters(filters)
        assert filters.find(user_submitted_responses) > -1, "only user submitted responses to be returned by the query"
        assert params["user_id"] == expected_user_id, "user id to be present to filter user responses by id"

        filters = dict(task_id=1, allow_taskrun_edit=False, order_by='task_id', user_id=239)
        filters, params = get_task_filters(filters)
        assert filters.find(user_submitted_responses) == -1, "user submitted responses NOT to be returned by the query"
        assert "user_id" not in params



    def test_task_browse_gold_task_filters(self):
        filters = dict(task_id=1,hide_completed=True, gold_task='1', order_by='task_id')
        expected_filter_query = " AND task.id = :task_id AND task.state='ongoing' AND task.calibration = :calibration"
        expected_params = {'task_id': 1, 'calibration': '1'}
        filters, params = get_task_filters(filters)
        assert filters == expected_filter_query, filters
        assert params == expected_params, params

        filters = dict(task_id=1,hide_completed=True, gold_task='0', order_by='task_id')
        expected_params = {'task_id': 1, 'calibration': '0'}
        filters, params = get_task_filters(filters)
        assert filters == expected_filter_query, filters
        assert params == expected_params, params

        args = dict(task_id=12345, gold_task='1')
        valid_args = dict(task_id=12345, gold_task='1', order_by_dict={},
            display_columns=['task_id', 'priority', 'pcomplete', 'created', 'finish_time', 'gold_task', 'actions', 'lock_status'])
        pargs = parse_tasks_browse_args(args)
        assert pargs == valid_args, pargs

        args = dict(task_id=12345, gold_task='0')
        valid_args = dict(task_id=12345, gold_task='0', order_by_dict={},
            display_columns=['task_id', 'priority', 'pcomplete', 'created', 'finish_time', 'gold_task', 'actions', 'lock_status'])
        pargs = parse_tasks_browse_args(args)
        assert pargs == valid_args, pargs

        args = dict(task_id=12345, gold_task='All')
        valid_args = dict(task_id=12345, order_by_dict={},
            display_columns=['task_id', 'priority', 'pcomplete', 'created', 'finish_time', 'gold_task', 'actions', 'lock_status'])
        pargs = parse_tasks_browse_args(args)
        assert pargs == valid_args, pargs

        args = dict(task_id=12345, gold_task='7')
        assert_raises(ValueError, parse_tasks_browse_args, args)

    @with_context
    def test_browse_completed(self):
        project = ProjectFactory.create()
        task = TaskFactory.create(project=project, info={}, n_answers=2)
        TaskRunFactory.create_batch(3, task=task)

        count, cached_tasks = cached_projects.browse_tasks(project.id, {
            'pcomplete_to': 100
        })

        assert count == 1
        assert cached_tasks[0]['id'] == task.id

    @with_context
    def test_browse_task_assigned_users(self):
        project = ProjectFactory.create()
        user_pref = dict(assign_user=["y@def.com", "z@ijk.com", "x@abc.com"])
        tasks = TaskFactory.create_batch(1, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])
        user_x = UserFactory.create(email_addr="x@abc.com", fullname="user_x at_abc")
        user_y = UserFactory.create(email_addr="y@def.com", fullname="user_y at_def")

        count, cached_tasks = cached_projects.browse_tasks(project.id, {
            "display_columns": ["assigned_users"]
        })

        assert count == 1
        assert cached_tasks[0]["id"] == tasks[0].id
        assert "assigned_users" in cached_tasks[0], "assigned_users column selected. assigned users should be part of task."
        assert "z@ijk.com" in cached_tasks[0]["assigned_users"], "user email to be present for user email not found in the system."
        assert len(cached_tasks[0]["assigned_users"]) == 3, "assigned_users count should be 3"
        assert cached_tasks[0]["assigned_users"][0] == 'user_x at_abc', "assigned users full names to be present in sorted order."
        assert cached_tasks[0]["assigned_users"][1] == 'user_y at_def', "assigned users full names to be present in sorted order."
        assert cached_tasks[0]["assigned_users"][2] == 'z@ijk.com', "assigned users full names to be present in sorted order."


    @with_context
    @patch('pybossa.cache.projects.get_user_saved_partial_tasks')
    def test_browse_tasks_filter_by_assigned_user(self, task_id_map_mock):
        """
        Test CACHE PROJECTS browse_tasks returns tasks filtered by assigned user.
        """

        project = ProjectFactory.create()
        user_pref = dict(assign_user=["y@def.com", "z@ijk.com", "x@abc.com"])
        tasks = TaskFactory.create_batch(1, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])
        user_x = UserFactory.create(email_addr="x@abc.com", fullname="user_x at_abc")
        user_y = UserFactory.create(email_addr="y@def.com", fullname="user_y at_def")

        count, cached_tasks = cached_projects.browse_tasks(project.id, {
            "display_columns": ["assigned_users"],
            "assign_user": "z@ijk.com"
        })

        assert count == 1
        assert cached_tasks[0]["id"] == tasks[0].id
        assert "assigned_users" in cached_tasks[0], "assigned_users column selected. assigned users should be part of task."
        assert "z@ijk.com" in cached_tasks[0]["assigned_users"], "user email to be present for user email not found in the system."
        assert len(cached_tasks[0]["assigned_users"]) == 3, "assigned_users count should be 3"
        assert cached_tasks[0]["assigned_users"][0] == 'user_x at_abc', "assigned users full names to be present in sorted order."
        assert cached_tasks[0]["assigned_users"][1] == 'user_y at_def', "assigned users full names to be present in sorted order."
        assert cached_tasks[0]["assigned_users"][2] == 'z@ijk.com', "assigned users full names to be present in sorted order."



    @with_context
    @patch('pybossa.cache.projects.get_user_saved_partial_tasks')
    def test_browse_tasks_filter_by_assigned_user_partial(self, task_id_map_mock):
        """
        Test CACHE PROJECTS browse_tasks returns tasks filtered by assigned user partial match.
        """

        project = ProjectFactory.create()
        user_pref = dict(assign_user=["y@def.com", "z@ijk.com", "x@abc.com"])
        tasks = TaskFactory.create_batch(1, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])
        user_x = UserFactory.create(email_addr="x@abc.com", fullname="user_x at_abc")
        user_y = UserFactory.create(email_addr="y@def.com", fullname="user_y at_def")

        count, cached_tasks = cached_projects.browse_tasks(project.id, {
            "display_columns": ["assigned_users"],
            "assign_user": "ijk"
        })

        assert count == 1
        assert cached_tasks[0]["id"] == tasks[0].id
        assert "assigned_users" in cached_tasks[0], "assigned_users column selected. assigned users should be part of task."
        assert "z@ijk.com" in cached_tasks[0]["assigned_users"], "user email to be present for user email not found in the system."
        assert len(cached_tasks[0]["assigned_users"]) == 3, "assigned_users count should be 3"
        assert cached_tasks[0]["assigned_users"][0] == 'user_x at_abc', "assigned users full names to be present in sorted order."
        assert cached_tasks[0]["assigned_users"][1] == 'user_y at_def', "assigned users full names to be present in sorted order."
        assert cached_tasks[0]["assigned_users"][2] == 'z@ijk.com', "assigned users full names to be present in sorted order."


    @with_context
    @patch('pybossa.cache.projects.get_user_saved_partial_tasks')
    def test_browse_tasks_filter_by_assigned_user_no_match(self, task_id_map_mock):
        """
        Test CACHE PROJECTS browse_tasks returns no tasks filtered by assigned user no match.
        """

        project = ProjectFactory.create()
        user_pref = dict(assign_user=["y@def.com", "z@ijk.com", "x@abc.com"])
        tasks = TaskFactory.create_batch(1, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])
        user_x = UserFactory.create(email_addr="x@abc.com", fullname="user_x at_abc")
        user_y = UserFactory.create(email_addr="y@def.com", fullname="user_y at_def")

        count, cached_tasks = cached_projects.browse_tasks(project.id, {
            "display_columns": ["assigned_users"],
            "assign_user": "no_match"
        })

        assert count == 0


    @with_context
    @patch('pybossa.cache.projects.get_user_saved_partial_tasks')
    def test_browse_tasks_filter_by_assigned_user_multi_match_1(self, task_id_map_mock):
        """
        Test CACHE PROJECTS browse_tasks returns tasks filtered by assigned user multiple matches.
        Same keyword match two users.
        """

        project = ProjectFactory.create()
        user_pref = dict(assign_user=["y@one.abc" ])
        tasks = TaskFactory.create_batch(3, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])


        user_pref = dict(assign_user=["x@two.abc"])
        tasks = TaskFactory.create_batch(3, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])

        user_pref = dict(assign_user=["z@ijk.com"])
        tasks = TaskFactory.create_batch(3, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])

        user_x = UserFactory.create(email_addr="x@two.abc", fullname="user_x at_abc")
        user_y = UserFactory.create(email_addr="y@one.abc", fullname="user_y at_def")

        count, cached_tasks = cached_projects.browse_tasks(project.id, {
            "display_columns": ["assigned_users"],
            "assign_user": ".abc"
        })

        assert count == 6


    @with_context
    @patch('pybossa.cache.projects.get_user_saved_partial_tasks')
    def test_browse_tasks_filter_by_assigned_user_multi_match_2(self, task_id_map_mock):
        """
        Test CACHE PROJECTS browse_tasks returns tasks filtered by assigned user multiple matches.
        Same keyword match three users.
        """

        project = ProjectFactory.create()
        user_pref = dict(assign_user=["y@one.abc" ])
        tasks = TaskFactory.create_batch(3, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])


        user_pref = dict(assign_user=["x@two.abc"])
        tasks = TaskFactory.create_batch(3, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])

        user_pref = dict(assign_user=["z@three.abcom"])
        tasks = TaskFactory.create_batch(3, project=project, info={}, n_answers=2, user_pref=user_pref)
        TaskRunFactory.create_batch(3, task=tasks[0])

        user_x = UserFactory.create(email_addr="x@two.abc", fullname="user_x at_abc")
        user_y = UserFactory.create(email_addr="y@one.abc", fullname="user_y at_def")

        count, cached_tasks = cached_projects.browse_tasks(project.id, {
            "display_columns": ["assigned_users"],
            "assign_user": ".ab"
        })

        assert count == 9


    @with_context
    @patch('pybossa.redis_lock.get_task_users_key')
    @patch('pybossa.redis_lock.get_user_tasks_key')
    @patch('pybossa.core.sentinel.master')
    @patch('pybossa.redis_lock.LockManager')
    @patch('pybossa.core.task_repo')
    def test_deleted_locked_task(self, mock_task_repo, mock_lock_manager, mock_redis, mock_get_user_tasks_key, mock_get_task_users_key):
        """Test deleting a locked task should clear it from the cache."""
        project_id = 1
        user_id = '12'
        task_id = '123'
        user_tasks_key = '12_123'
        task_users_key = '123_12'
        mock_get_user_tasks_key.return_value = user_tasks_key
        mock_get_task_users_key.return_value = task_users_key
        mock_redis.hgetall.return_value = {user_id: user_id}
        mock_lock_manager.return_value.get_locks.return_value = {task_id: task_id}

        # Simulate deleted task.
        mock_redis.mget.return_value = [None]
        mock_task_repo.get_task.return_value = None

        # Execute method.
        result = get_locked_tasks_project(project_id)

        # Verify no tasks are returned and cache clear has been called.
        assert result == []
        calls = [call(task_users_key, user_id), call(user_tasks_key, task_id)]
        mock_lock_manager.return_value.release_lock.assert_has_calls(calls, any_order=True)
