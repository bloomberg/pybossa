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
# along with PYBOSSA.  If not,  see <http://www.gnu.org/licenses/>.

import datetime
from collections import OrderedDict
from test import db, Test, with_context, with_request_context
from pybossa.cache import site_stats as stats
from test.factories import (UserFactory, ProjectFactory, AnonymousTaskRunFactory,
                       TaskRunFactory, TaskFactory, CategoryFactory)
from pybossa.repositories import ResultRepository
from unittest.mock import patch
from pybossa.cache import management_dashboard_stats, delete_cache_group
from pybossa.jobs import get_management_dashboard_stats, load_usage_dashboard_data
from pybossa.view.admin import sort_stats_by_last_submission
from flask import current_app
import pybossa.cache.project_stats as project_stats

result_repo = ResultRepository(db)


class TestSiteStatsCache(Test):

    @with_context
    def create_result(self, n_results=1, n_answers=1, owner=None,
                      filter_by=False):
        if owner:
            owner = owner
        else:
            owner = UserFactory.create()
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
    def test_n_auth_users_returns_number_of_registered_users(self):
        UserFactory.create_batch(2)
        users = stats.n_auth_users()

        assert users == 2, users

    @with_context
    def test_n_anon_users_returns_number_of_distinct_anonymous_contributors(self):
        AnonymousTaskRunFactory.create(user_ip="1.1.1.1")
        AnonymousTaskRunFactory.create(user_ip="1.1.1.1")
        AnonymousTaskRunFactory.create(user_ip="2.2.2.2")

        anonymous_users = stats.n_anon_users()

        # No anonymous users supported in Gigwork. Return 0 to speed up

        assert anonymous_users == 0, anonymous_users

    @with_context
    def test_n_tasks_site_returns_number_of_total_tasks_default(self):
        TaskFactory.create_batch(2)

        tasks = stats.n_tasks_site()
        assert tasks == 2, tasks

    @with_context
    def test_n_tasks_site_with_parameter(self):
        """Test total tasks"""
        date_20_mo = (datetime.datetime.utcnow() -  datetime.timedelta(600)).isoformat()
        date_8_mo = (datetime.datetime.utcnow() -  datetime.timedelta(240)).isoformat()
        date_2_mo = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()
        date_1_mo = (datetime.datetime.utcnow() -  datetime.timedelta(30)).isoformat()

        ProjectFactory.create()

        TaskFactory.create(created=date_1_mo)
        TaskFactory.create(created=date_2_mo)
        TaskFactory.create(created=date_8_mo)
        TaskFactory.create(created=date_20_mo)

        expected_tasks_6_mo = 2
        total_tasks_6_mo = stats.n_tasks_site(days=183)
        assert total_tasks_6_mo == expected_tasks_6_mo, \
                f"{total_tasks_6_mo} active tasks in last 6 months, expected {expected_tasks_6_mo}"

        expected_tasks_12_mo = 3
        total_tasks_12_mo = stats.n_tasks_site(days=365)
        assert total_tasks_12_mo == expected_tasks_12_mo, \
                f"{total_tasks_12_mo} active tasks in last 12 months, expected {expected_tasks_12_mo}"

    @with_context
    def test_n_total_tasks_site_returns_aggregated_number_of_required_tasks(self):
        TaskFactory.create(n_answers=2)
        TaskFactory.create(n_answers=2)

        tasks = stats.n_total_tasks_site()

        assert tasks == 4, tasks

    @with_context
    def test_n_total_task_runs_site_returns_total_number_of_answers(self):
        AnonymousTaskRunFactory.create()
        TaskRunFactory.create()

        task_runs = stats.n_task_runs_site()

        assert task_runs == 2, task_runs

    @with_context
    def test_n_results_site_returns_zero_results_when_no_info(self):
        n_results = stats.n_results_site()

        assert n_results == 0, n_results

        self.create_result()
        n_results = stats.n_results_site()

        assert n_results == 0, n_results

        self.create_result(n_results=2)
        n_results = stats.n_results_site()

        assert n_results == 0, n_results

    @with_context
    def test_n_results_site_returns_valid_results_with_info(self):
        project = ProjectFactory.create()
        task = TaskFactory.create(n_answers=1, project=project)
        TaskRunFactory.create(task=task, project=project)
        result = result_repo.get_by(project_id=project.id)
        result.info = dict(foo='bar')
        result_repo.update(result)
        n_results = stats.n_results_site()

        assert n_results == 1, n_results

        project = ProjectFactory.create()
        task = TaskFactory.create(n_answers=1, project=project)
        TaskRunFactory.create(task=task, project=project)
        result = result_repo.get_by(project_id=project.id)
        result.info = dict(foo='bar2')
        result_repo.update(result)
        n_results = stats.n_results_site()

        assert n_results == 2, n_results

        self.create_result(n_results=10)

        assert n_results == 2, n_results

    @with_context
    def test_get_top5_projects_24_hours_returns_best_5_only(self):
        projects = ProjectFactory.create_batch(5)
        i = 5
        for project in projects:
            TaskRunFactory.create_batch(i, project=project)
            i -= 1

        worst_project = ProjectFactory.create()

        top5 = stats.get_top5_projects_24_hours()
        top5_ids = [top['id'] for top in top5]

        assert len(top5) == 5
        assert worst_project.id not in top5_ids
        for i in range(len(top5)):
            assert projects[i].id == top5_ids[i]

    @with_context
    def test_get_top5_projects_24_hours_considers_last_24_hours_contributions_only(self):
        recently_contributed_project = ProjectFactory.create()
        long_ago_contributed_project = ProjectFactory.create()
        two_days_ago = (datetime.datetime.utcnow() -  datetime.timedelta(2)).isoformat()

        TaskRunFactory.create(project=recently_contributed_project)
        TaskRunFactory.create(project=long_ago_contributed_project, finish_time=two_days_ago)

        top5 = stats.get_top5_projects_24_hours()
        top5_ids = [top['id'] for top in top5]

        assert recently_contributed_project.id in top5_ids
        assert long_ago_contributed_project.id not in top5_ids

    @with_context
    def test_get_top5_projects_24_hours_returns_required_fields(self):
        fields = ('id', 'name', 'short_name', 'info', 'n_answers')
        TaskRunFactory.create()

        top5 = stats.get_top5_projects_24_hours()

        for field in fields:
            assert field in top5[0].keys()

    @with_context
    def test_get_top5_users_24_hours_returns_best_5_users_only(self):
        users = UserFactory.create_batch(4)
        restricted = UserFactory.create(restrict=True)
        users.append(restricted)
        i = 5
        for user in users:
            TaskRunFactory.create_batch(i, user=user)
            i -= 1

        worst_user = UserFactory.create()

        top5 = stats.get_top5_users_24_hours()
        top5_ids = [top['id'] for top in top5]

        assert len(top5) == 4, len(top5)
        assert worst_user.id not in top5_ids
        for i in range(len(top5)):
            assert users[i].id == top5_ids[i]
            assert users[i].restrict is False
            assert users[i].id != restricted.id

    @with_context
    def test_get_top5_users_24_hours_considers_last_24_hours_contributions_only(self):
        recently_contributing_user = UserFactory.create()
        long_ago_contributing_user = UserFactory.create()
        two_days_ago = (datetime.datetime.utcnow() -  datetime.timedelta(2)).isoformat()

        TaskRunFactory.create(user=recently_contributing_user)
        TaskRunFactory.create(user=long_ago_contributing_user, finish_time=two_days_ago)

        top5 = stats.get_top5_users_24_hours()
        top5_ids = [top['id'] for top in top5]

        assert recently_contributing_user.id in top5_ids
        assert long_ago_contributing_user.id not in top5_ids

    @with_context
    def test_number_of_created_jobs(self):
        """Test number of projects created in last 30 days"""
        date_now = datetime.datetime.utcnow()
        date_60_days_old = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()
        projects = ProjectFactory.create_batch(5, created=date_now)
        old_project = ProjectFactory.create(created=date_60_days_old)
        total_projects = stats.number_of_created_jobs()
        assert total_projects == 5, "Total number of projects created in last 30 days should be 5"

    @with_context
    def test_number_of_created_jobs(self):
        """Test total projects by interval"""
        date_20_mo = (datetime.datetime.utcnow() -  datetime.timedelta(600)).isoformat()
        date_8_mo = (datetime.datetime.utcnow() -  datetime.timedelta(240)).isoformat()
        date_2_mo = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()
        date_1_mo = (datetime.datetime.utcnow() -  datetime.timedelta(30)).isoformat()

        ProjectFactory.create(created=date_1_mo, updated=date_1_mo)
        ProjectFactory.create(created=date_2_mo, updated=date_2_mo)
        ProjectFactory.create(created=date_8_mo, updated=date_8_mo)
        ProjectFactory.create(created=date_20_mo, updated=date_20_mo)

        expected_projects_6_mo = 2
        total_active_projects_6_mo = stats.number_of_created_jobs(days=183)
        assert total_active_projects_6_mo == expected_projects_6_mo, \
                f"{total_active_projects_6_mo} active projects in last 6 months, expected {expected_projects_6_mo}"

        expected_projects_12_mo = 3
        total_active_projects_12_mo = stats.number_of_created_jobs(days=365)
        assert total_active_projects_12_mo == expected_projects_12_mo, \
                f"{total_active_projects_12_mo} active projects in last 12 months, expected {expected_projects_12_mo}"


    @with_request_context
    def test_number_of_active_jobs(self):
        """Test number of active projects with submissions in last 30 days"""
        date_60_days_old = (datetime.datetime.utcnow() - datetime.timedelta(60)).isoformat()

        recently_contributed_project = ProjectFactory.create()
        long_ago_contributed_project = ProjectFactory.create()

        task = TaskFactory.create(n_answers=1, project=recently_contributed_project)
        TaskRunFactory.create(task=task, project=recently_contributed_project)

        old_task = TaskFactory.create(n_answers=1, project=long_ago_contributed_project, created=date_60_days_old)
        TaskRunFactory.create(task=old_task, project=long_ago_contributed_project, finish_time=date_60_days_old)

        project_stats.update_stats(recently_contributed_project.id)
        project_stats.update_stats(long_ago_contributed_project.id)

        total_active_projects = stats.number_of_active_jobs()
        assert total_active_projects == 1, "Total number of active projects in last 30 days should be 1"

        all_projects = stats.number_of_active_jobs(days='all')
        assert all_projects == 2, "Total number of all projects should be 2"

    @with_context
    def test_number_of_created_tasks(self):
        """Test number of tasks created in last 30 days"""
        date_60_days_old = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()

        TaskFactory.create()
        TaskFactory.create()
        TaskFactory.create(created=date_60_days_old)
        tasks = stats.number_of_created_tasks()

        assert tasks == 2, "Total number tasks created in last 30 days should be 2"

    @with_context
    def test_number_of_completed_tasks(self):
        """Test number of tasks completed in last 30 days"""
        date_now = datetime.datetime.utcnow()
        date_60_days_old = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()

        recent_project = ProjectFactory.create(created=date_now)
        old_project = ProjectFactory.create(created=date_60_days_old)

        # recent tasks completed
        recent_taskruns = 5
        for i in range(recent_taskruns):
            task = TaskFactory.create(n_answers=1, project=recent_project, created=date_now)
            TaskRunFactory.create(task=task, project=recent_project, finish_time=date_now)

        # old tasks completed
        for i in range(3):
            task = TaskFactory.create(n_answers=1, project=old_project, created=date_60_days_old)
            TaskRunFactory.create(task=task, project=recent_project, finish_time=date_60_days_old)

        total_tasks = stats.number_of_completed_tasks()
        assert total_tasks == recent_taskruns, "Total completed tasks in last 30 days should be {}".format(recent_taskruns)

    @with_context
    def test_number_of_active_users(self):
        """Test number of active users in last 30 days"""
        date_now = datetime.datetime.utcnow()
        date_60_days_old = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()

        recent_users = 4
        users = UserFactory.create_batch(recent_users)
        i = recent_users
        for user in users:
            TaskRunFactory.create_batch(i, user=user, finish_time=date_now)
            i -= 1

        old_user = UserFactory.create()
        TaskRunFactory.create(user=old_user, finish_time=date_60_days_old)

        total_users = stats.number_of_active_users()
        assert total_users == recent_users, "Total active users in last 30 days should be {}".format(recent_users)

    @with_context
    def test_get_categories_with_recent_projects(self):
        """Test categories with projects created in last 30 days"""
        date_now = datetime.datetime.utcnow()
        date_60_days_old = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()

        categories = CategoryFactory.create_batch(3)
        unused_category = CategoryFactory.create()

        ProjectFactory.create(category=categories[0], created=date_now)
        ProjectFactory.create(category=categories[1], created=date_now)
        ProjectFactory.create(category=categories[0], created=date_now)

        ProjectFactory.create(category=categories[2], created=date_60_days_old)
        total_categories = stats.categories_with_new_projects()
        assert total_categories == 2, "Total categories with recent projects should be 2"

    @with_request_context
    def test_avg_task_per_job(self):
        """Test average task per job created since current time"""
        date_recent = (datetime.datetime.utcnow() -  datetime.timedelta(29)).isoformat()
        date_old = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()
        date_now = datetime.datetime.utcnow().isoformat()
        expected_avg_tasks = 5

        project = ProjectFactory.create(created=date_recent)
        old_project = ProjectFactory.create(created=date_old)

        TaskFactory.create_batch(5, n_answers=1, project=project, created=date_now)
        TaskFactory.create_batch(5, n_answers=1, project=old_project, created=date_old)

        # update the project_stats data so that avg_task_per_job get the correct data
        project_stats.update_stats(project.id)
        project_stats.update_stats(old_project.id)

        avg_tasks = stats.avg_task_per_job()
        assert avg_tasks == expected_avg_tasks, "Average task created per job should be {}".format(expected_avg_tasks)

    @with_context
    def test_avg_time_to_complete_task(self):
        """Test average time to complete tasks in last 30 days"""
        date_15m_old = (datetime.datetime.utcnow() -  datetime.timedelta(minutes=15)).isoformat()
        date_now = datetime.datetime.utcnow()

        expected_avg_time = '15m 00s'
        for i in range(5):
            TaskRunFactory.create(created=date_15m_old, finish_time=date_now)

        avg_time = stats.avg_time_to_complete_task()
        assert avg_time == expected_avg_time, \
            "Average time to complete tasks in last 30 days should be {}".format(expected_avg_time)

    @with_request_context
    def test_avg_tasks_per_category(self):
        """Test average tasks per category created since current time"""
        date_recent = (datetime.datetime.utcnow() -  datetime.timedelta(31)).isoformat()
        date_now = (datetime.datetime.utcnow() -  datetime.timedelta(1)).isoformat()
        expected_avg_tasks = 3

        categories = CategoryFactory.create_batch(3)
        project1 = ProjectFactory.create(category=categories[0], created=date_now)
        project2 = ProjectFactory.create(category=categories[1], created=date_recent)
        project3 = ProjectFactory.create(category=categories[2], created=date_recent)

        for i in range(5):
            TaskFactory.create(project=project1, created=date_now)

        for i in range(2):
            TaskFactory.create(project=project2, created=date_recent)

        for i in range(3):
            TaskFactory.create(project=project3, created=date_recent)

        project_stats.update_stats(project1.id)
        project_stats.update_stats(project2.id)
        project_stats.update_stats(project3.id)

        avg_tasks = round(stats.tasks_per_category())
        assert avg_tasks == expected_avg_tasks, "Average tasks created per category should be {}".format(expected_avg_tasks)

    @with_context
    def test_charts(self):
        """Test project chart"""
        return #to fix
        date_old = (datetime.datetime.utcnow() -  datetime.timedelta(30*36)).isoformat()
        date_4_mo = (datetime.datetime.utcnow() -  datetime.timedelta(120)).isoformat()
        date_3_mo = (datetime.datetime.utcnow() -  datetime.timedelta(90)).isoformat()
        date_2_mo = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()
        date_1_mo = (datetime.datetime.utcnow() -  datetime.timedelta(30)).isoformat()
        expected_tasks = 6
        expected_categories = 2
        expected_projects = 4
        expected_taskruns = 5

        CategoryFactory.create(created=date_1_mo)
        CategoryFactory.create(created=date_2_mo)
        CategoryFactory.create(created=date_3_mo)

        ProjectFactory.create(created=date_1_mo)
        ProjectFactory.create(created=date_2_mo)
        ProjectFactory.create(created=date_3_mo)
        ProjectFactory.create(created=date_4_mo)
        ProjectFactory.create(created=date_old)

        TaskFactory.create(created=date_1_mo)
        TaskFactory.create(created=date_2_mo)
        TaskFactory.create(created=date_3_mo)

        TaskRunFactory.create(created=date_1_mo)
        TaskRunFactory.create(created=date_2_mo)
        TaskRunFactory.create(created=date_3_mo)
        TaskRunFactory.create(created=date_4_mo)
        TaskRunFactory.create(created=date_old)

        projects = stats.project_chart()
        assert projects['series'][0][24] == expected_projects, "{} projects created in last 24 months".format(expected_projects)
        categories = stats.category_chart()
        assert categories['series'][0][24] == expected_categories, "{} categories created in last 24 months".format(expected_categories)
        tasks = stats.task_chart()
        assert tasks['series'][0][24] == expected_tasks, "{} tasks created in last 24 months".format(expected_tasks)
        taskruns = stats.submission_chart()
        assert taskruns['series'][0][24] == expected_taskruns, "{} taskruns created in last 24 months".format(expected_taskruns)


    @with_context
    def test_n_task_runs_site_with_interval(self):
        """Test total taskruns"""
        date_20_mo = (datetime.datetime.utcnow() -  datetime.timedelta(600)).isoformat()
        date_8_mo = (datetime.datetime.utcnow() -  datetime.timedelta(240)).isoformat()
        date_2_mo = (datetime.datetime.utcnow() -  datetime.timedelta(60)).isoformat()
        date_1_mo = (datetime.datetime.utcnow() -  datetime.timedelta(30)).isoformat()

        ProjectFactory.create()
        TaskFactory.create()

        TaskRunFactory.create(finish_time=date_1_mo)
        TaskRunFactory.create(finish_time=date_2_mo)
        TaskRunFactory.create(finish_time=date_8_mo)
        TaskRunFactory.create(finish_time=date_20_mo)

        expected_taskruns_6_mo = 2
        total_taskruns_6_mo = stats.n_task_runs_site(days=183)
        assert total_taskruns_6_mo == expected_taskruns_6_mo, \
                f"{total_taskruns_6_mo} active taskruns in last 6 months, expected {expected_taskruns_6_mo}"

        expected_taskruns_12_mo = 3
        total_taskruns_12_mo = stats.n_task_runs_site(days=365)
        assert total_taskruns_12_mo == expected_taskruns_12_mo, \
                f"{total_taskruns_12_mo} active taskruns in last 12 months, expected {expected_taskruns_12_mo}"


    @with_context
    @patch('pybossa.jobs.send_mail')
    def test_management_dashboard_stats(self, mail):
        """Test management dashboard stats"""

        # reset cache and built just one stats, avg_time_to_complete_task
        list(map(delete_cache_group, management_dashboard_stats))
        date_15m_old = (datetime.datetime.utcnow() -  datetime.timedelta(minutes=15)).isoformat()
        date_now = datetime.datetime.utcnow()

        expected_avg_time = '15m 00s'
        for i in range(5):
            TaskRunFactory.create(created=date_15m_old, finish_time=date_now)

        avg_time = stats.avg_time_to_complete_task()
        assert avg_time == expected_avg_time, \
            "Average time to complete tasks in last 30 days should be {}".format(expected_avg_time)

        stats_cached = stats.management_dashboard_stats_cached()
        assert not stats_cached, 'management dashboard stats should be reported as unavailable'
        if not stats_cached:
            user_email = 'john@got.com'
            get_management_dashboard_stats(user_email)
            subject = 'Management Dashboard Statistics'
            msg = 'Management dashboard statistics is now available. It can be accessed by refreshing management dashboard page.'
            body = ('Hello,\n\n{}\nThe {} team.'
                    .format(msg, current_app.config.get('BRAND')))
            mail_dict = dict(recipients=[user_email], subject=subject, body=body)
            mail.assert_called_with(mail_dict)

    @with_context
    def test_load_usage_dashboard_data(self):
        """Test load usage dashboard data"""
        with patch.dict(self.flask_app.config, {'USAGE_DASHBOARD_COMPONENTS':
            {
                'Annex' : 'annex-shell',
                'DocX' : 'loadDocument',
                'NLP Component' : 'text-tagging'
            }
        }):

            stats = load_usage_dashboard_data(days='all')
            assert 'Projects' in stats.keys() ,"Expected 'Projects' key in stats"
            assert 'Tasks' in stats.keys(), "Expected 'Tasks' key in stats"
            assert 'Taskruns' in stats.keys(), "Expected 'Taskruns' key in stats"
            assert 'Annex' in stats.keys(), "Expected 'Annex' key in stats"
            assert 'DocX' in stats.keys(), "Expected 'DocX' key in stats"
            assert 'NLP Component' in stats.keys(), "Expected 'NLP Component' key in stats"

    @with_context
    def test_n_projects_using_component(self):
        """Test number of projects using component works correctly"""
        date_1_mo = (datetime.datetime.utcnow() -  datetime.timedelta(30)).isoformat()
        date_12_mo = (datetime.datetime.utcnow() -  datetime.timedelta(360)).isoformat()

        project_info = {"task_presenter" : "<text-tagging></text-tagging>"}

        ProjectFactory.create_batch(5)
        ProjectFactory.create(created=date_1_mo, updated=date_1_mo, info=project_info)
        ProjectFactory.create(created=date_1_mo, updated=date_1_mo)
        ProjectFactory.create(created=date_12_mo, updated=date_12_mo, info=project_info)

        res = stats.n_projects_using_component(days=183, component='text-tagging')
        assert len(res) == 1, "Expected 1 project in last 6 months using text-tagging"

        res = stats.n_projects_using_component(days='all', component='text-tagging')
        assert len(res) == 2, "Expected 2 projects in all time using text-tagging"

    @with_context
    def test_n_projects_using_component_sort(self):
        """Test number of projects using component works correctly with sort"""
        data = OrderedDict([('Task Presenter', [(1, '34', 'second-project', '1', 'User One', 'user@user.com', '2024-11-12T15:42:43.020270', 'true'), (1, '35', 'helloworld2', '1', 'User One', 'user@user.com', None, 'true'), (1, '36', 'helloworld3', '1', 'User One', 'user@user.com', None, 'false'), (1, '37', 'first-project', '1', 'User One', 'user@user.com', '2024-11-12T16:37:45.682369', 'false')]), ('All Buttons', []), ('Submit Button', []), ('Submit and Leave Button', []), ('Cancel Button', []), ('Task Timer', [(1, '37', 'first-project', '1', 'User One', 'user@user.com', '2024-11-12T16:37:45.682369', 'false')]), ('Conditional Display', []), ('File Upload', []), ('Text Input', [(1, '35', 'helloworld2', '1', 'User One', 'user@user.com', None, 'true'), (1, '36', 'helloworld3', '1', 'User One', 'user@user.com', None, 'false'), (1, '37', 'first-project', '1', 'User One', 'user@user.com', '2024-11-12T16:37:45.682369', 'false')]), ('Checkbox Input', [(1, '36', 'helloworld3', '1', 'User One', 'user@user.com', None, 'false')]), ('Radio Group Input', []), ('Dropdown Input', []), ('Multiselect Input', []), ('Table', []), ('Input Text Area', []), ('Assistant LLM', []), ('compx', [])])

        # Sort mock data.
        sorted_data = sort_stats_by_last_submission(data)

        # Verify the correct sort is returned for first-project, second-project, followed by projects with no data provided.
        assert sorted_data['Task Presenter'][0][2] == 'first-project'
        assert sorted_data['Task Presenter'][1][2] == 'second-project'

        # Verify correct dates in sorted descending order.
        assert sorted_data['Task Presenter'][0][6] == '2024-11-12T16:37:45.682369'
        assert sorted_data['Task Presenter'][1][6] == '2024-11-12T15:42:43.020270'
        assert sorted_data['Task Presenter'][2][6] == None
        assert sorted_data['Task Presenter'][3][6] == None
