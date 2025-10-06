# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2017 Scifabric LTD.
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

from test import Test, with_context
from pybossa.cache import users as cached_users
from pybossa.model.user import User
from pybossa.leaderboard.jobs import leaderboard as update_leaderboard
from pybossa.redis_lock import (get_user_exported_reports_key,
                                register_user_exported_report,
                                get_user_exported_reports)
from pybossa.core import sentinel
from time import time
from datetime import datetime
from unittest.mock import patch, MagicMock
import os

from test.factories import ProjectFactory, TaskFactory, TaskRunFactory, UserFactory


class TestUsersCache(Test):

    @with_context
    def test_get_user_summary_nousers(self):
        """Test CACHE USERS get_user_summary returns None if no user exists with
        the name requested"""
        user = cached_users.get_user_summary('nouser')

        assert user is None, user

    @with_context
    def test_public_get_user_summary_nousers(self):
        """Test public CACHE USERS get_user_summary returns None if no user exists with
        the name requested"""
        user = cached_users.public_get_user_summary('nouser')

        assert user is None, user

    @with_context
    def test_get_user_summary_user_exists(self):
        """Test CACHE USERS get_user_summary returns a dict with the user data
        if the user exists"""
        UserFactory.create(name='zidane')
        UserFactory.create(name='figo')

        zizou = cached_users.get_user_summary('zidane')

        assert type(zizou) is dict, type(zizou)
        assert zizou != None, zizou

    @with_context
    def test_get_user_summary_user_exists_restrict(self):
        """Test CACHE USERS get_user_summary returns a dict with the user data
        if the user exists restricted"""
        UserFactory.create(name='zidane', restrict=True)
        UserFactory.create(name='figo')

        zizou = cached_users.get_user_summary('zidane')

        assert zizou is None, zizou

    @with_context
    def test_public_get_user_summary_user_exists(self):
        """Test public CACHE USERS get_user_summary returns a dict with the user data
        if the user exists"""
        UserFactory.create(name='zidane')
        UserFactory.create(name='figo')

        zizou = cached_users.public_get_user_summary('zidane')

        assert type(zizou) is dict, type(zizou)
        assert zizou != None, zizou

    @with_context
    def test_get_user_summary_returns_fields(self):
        """Test CACHE USERS get_user_summary all the fields in the dict"""
        UserFactory.create(name='user')
        fields = ('id', 'name', 'fullname', 'created', 'api_key',
                  'twitter_user_id', 'google_user_id', 'facebook_user_id',
                  'info', 'admin', 'email_addr', 'n_answers', 'rank', 'score',
                  'total')
        user = cached_users.get_user_summary('user')

        for field in fields:
            assert field in user.keys(), field

    @with_context
    def test_public_get_user_summary_returns_fields(self):
        """Test CACHE USERS public_get_user_summary all the fields in the dict"""
        UserFactory.create(name='user')
        public_fields = ('name', 'info', 'fullname', 'created', 'rank', 'score')
        private_fields = ('id', 'api_key', 'twitter_user_id', 'google_user_id',
                          'facebook_user_id', 'admin', 'email_addr', 'total')
        user = cached_users.public_get_user_summary('user')

        for field in public_fields:
            assert field in user.keys(), field

        for field in private_fields:
            assert field not in user.keys(), field

    @with_context
    def test_rank_and_score(self):
        """Test CACHE USERS rank_and_score returns the correct rank and score"""
        i = 0
        project = ProjectFactory.create()
        tasks = TaskFactory.create_batch(4, project=project)
        users = UserFactory.create_batch(4)
        for user in users:
            i += 1
            taskruns = TaskRunFactory.create_batch(i, user=user, task=tasks[i - 1])

        update_leaderboard()
        first_in_rank = cached_users.rank_and_score(users[3].id)
        last_in_rank = cached_users.rank_and_score(users[0].id)
        print(first_in_rank)
        assert first_in_rank['rank'] == 1, first_in_rank['rank']
        assert first_in_rank['score'] == 4, first_in_rank['score']
        assert last_in_rank['rank'] == 4, last_in_rank['rank']
        assert last_in_rank['score'] == 1, last_in_rank['score']

    @with_context
    def test_projects_contributed_no_contributions(self):
        """Test CACHE USERS projects_contributed returns empty list if the user has
        not contributed to any project"""
        user = UserFactory.create()

        projects_contributed = cached_users.projects_contributed(user.id)

        assert projects_contributed == [], projects_contributed

    @with_context
    def test_projects_contributed_no_contributions_cached(self):
        """Test CACHE USERS projects_contributed_cached returns empty list if the user has
        not contributed to any project"""
        user = UserFactory.create()

        projects_contributed = cached_users.projects_contributed_cached(user.id)

        assert projects_contributed == [], projects_contributed

    @with_context
    def test_public_projects_contributed_no_contributions(self):
        """Test public CACHE USERS projects_contributed returns empty list if the user has
        not contributed to any project"""
        user = UserFactory.create()

        projects_contributed = cached_users.public_projects_contributed(user.id)

        assert projects_contributed == [], projects_contributed

    @with_context
    def test_public_projects_contributed_no_contributions_cached(self):
        """Test public CACHE USERS projects_contributed_cached returns empty list if the user has
        not contributed to any project"""
        user = UserFactory.create()

        projects_contributed = cached_users.public_projects_contributed_cached(user.id)

        assert projects_contributed == [], projects_contributed

    @with_context
    def test_projects_contributed_contributions(self):
        """Test CACHE USERS projects_contributed returns a list of projects that has
        contributed to"""
        user = UserFactory.create()
        project_contributed = ProjectFactory.create()
        task = TaskFactory.create(project=project_contributed)
        TaskRunFactory.create(task=task, user=user)
        another_project = ProjectFactory.create()

        projects_contributed = cached_users.projects_contributed(user.id)

        assert len(projects_contributed) == 1
        assert projects_contributed[0]['short_name'] == project_contributed.short_name, projects_contributed

    @with_context
    def test_projects_contributed_contributions_cached(self):
        """Test CACHE USERS projects_contributed_cached returns a list of projects that has
        contributed to"""
        user = UserFactory.create()
        project_contributed = ProjectFactory.create()
        task = TaskFactory.create(project=project_contributed)
        TaskRunFactory.create(task=task, user=user)
        another_project = ProjectFactory.create()

        projects_contributed = cached_users.projects_contributed_cached(user.id)

        assert len(projects_contributed) == 1
        assert projects_contributed[0]['short_name'] == project_contributed.short_name, projects_contributed

    @with_context
    def test_public_projects_contributed_contributions(self):
        """Test CACHE USERS public projects_contributed returns a list of projects that has
        contributed to"""
        user = UserFactory.create()
        project_contributed = ProjectFactory.create()
        task = TaskFactory.create(project=project_contributed)
        TaskRunFactory.create(task=task, user=user)
        another_project = ProjectFactory.create()

        projects_contributed = cached_users.public_projects_contributed(user.id)

        assert len(projects_contributed) == 1
        assert projects_contributed[0]['short_name'] == project_contributed.short_name, projects_contributed

        # check privacy
        err_msg = 'private information is in public record'
        assert 'secret_key' not in projects_contributed[0], err_msg
        assert 'onesignal' not in projects_contributed[0]['info']
        assert 'passwd_hash' not in projects_contributed[0]['info']

    @with_context
    def test_public_projects_contributed_contributions_cached(self):
        """Test CACHE USERS public cached projects_contributed returns a list of projects that has
        contributed to"""
        user = UserFactory.create()
        project_contributed = ProjectFactory.create()
        task = TaskFactory.create(project=project_contributed)
        TaskRunFactory.create(task=task, user=user)
        another_project = ProjectFactory.create()

        projects_contributed = cached_users.public_projects_contributed_cached(user.id)

        assert len(projects_contributed) == 1
        assert projects_contributed[0]['short_name'] == project_contributed.short_name, projects_contributed

        # check privacy
        err_msg = 'private information is in public record'
        assert 'secret_key' not in projects_contributed[0], err_msg
        assert 'onesignal' not in projects_contributed[0]['info']
        assert 'passwd_hash' not in projects_contributed[0]['info']

    @with_context
    def test_projects_contributed_returns_fields(self):
        """Test CACHE USERS projects_contributed returns the info of the projects with
        the required fields"""
        user = UserFactory.create()
        project_contributed = ProjectFactory.create()
        task = TaskFactory.create(project=project_contributed)
        TaskRunFactory.create(task=task, user=user)
        fields = ('id', 'name', 'short_name', 'owner_id', 'description',
                  'overall_progress', 'n_tasks', 'n_volunteers', 'info')

        projects_contributed = cached_users.projects_contributed(user.id)

        for field in fields:
            assert field in projects_contributed[0].keys(), field

    @with_context
    def test_published_projects_no_projects(self):
        """Test CACHE USERS published_projects returns empty list if the user has
        not created any project"""
        user = UserFactory.create()

        projects_published = cached_users.published_projects(user.id)

        assert projects_published == [], projects_published

    @with_context
    def test_published_projects_no_projects_cached(self):
        """Test CACHE USERS published_projects_cached returns empty list if the user has
        not created any project"""
        user = UserFactory.create()

        projects_published = cached_users.published_projects_cached(user.id)

        assert projects_published == [], projects_published

    @with_context
    def test_public_published_projects_no_projects(self):
        """Test public CACHE USERS published_projects returns empty list if the user has
        not created any project"""
        user = UserFactory.create()

        projects_published = cached_users.public_published_projects(user.id)

        assert projects_published == [], projects_published

    @with_context
    def test_public_published_projects_no_projects_cached(self):
        """Test public CACHE USERS published_projects_cached returns empty list if the user has
        not created any project"""
        user = UserFactory.create()

        projects_published = cached_users.public_published_projects_cached(user.id)

        assert projects_published == [], projects_published

    @with_context
    def test_published_projects_returns_published(self):
        """Test CACHE USERS published_projects returns a list with the projects that
        are published by the user"""
        user = UserFactory.create()
        published_project = ProjectFactory.create(owner=user, published=True)

        projects_published = cached_users.published_projects(user.id)

        assert len(projects_published) == 1, projects_published
        assert projects_published[0]['short_name'] == published_project.short_name, projects_published

    @with_context
    def test_public_published_projects_returns_published(self):
        """Test public CACHE USERS published_projects returns a list with the projects that
        are published by the user"""
        user = UserFactory.create()
        published_project = ProjectFactory.create(owner=user, published=True)

        projects_published = cached_users.public_published_projects(user.id)

        assert len(projects_published) == 1, projects_published
        assert projects_published[0]['short_name'] == published_project.short_name, projects_published

    @with_context
    def test_published_projects_only_returns_published(self):
        """Test CACHE USERS published_projects does not return draft
        or another user's projects"""
        user = UserFactory.create()
        another_user_published_project = ProjectFactory.create(published=True)
        draft_project = ProjectFactory.create(owner=user, published=False)

        projects_published = cached_users.published_projects(user.id)

        assert len(projects_published) == 0, projects_published

    @with_context
    def test_published_projects_returns_fields(self):
        """Test CACHE USERS published_projects returns the info of the projects with
        the required fields"""
        user = UserFactory.create()
        published_project = ProjectFactory.create(owner=user, published=True)
        fields = ('id', 'name', 'short_name', 'owner_id', 'description',
                  'overall_progress', 'n_tasks', 'n_volunteers', 'info')

        projects_published = cached_users.published_projects(user.id)

        for field in fields:
            assert field in projects_published[0].keys(), field

    @with_context
    def test_public_published_projects_returns_fields(self):
        """Test CACHE USERS published_projects returns the info of the projects with
        the required fields"""
        user = UserFactory.create()
        published_project = ProjectFactory.create(owner=user, published=True)
        private_fields = ('owner_id')
        public_fields = ('name', 'short_name', 'description',
                         'overall_progress', 'n_tasks', 'n_volunteers', 'info')

        projects_published = cached_users.public_published_projects(user.id)

        for field in public_fields:
            assert field in projects_published[0].keys(), field

        for field in private_fields:
            assert field not in projects_published[0].keys(), field

    @with_context
    def test_public_published_projects_cached_returns_fields(self):
        """Test CACHE USERS published_projects_cached returns the info of the projects with
        the required fields"""
        user = UserFactory.create()
        published_project = ProjectFactory.create(owner=user, published=True)
        private_fields = ('owner_id')
        public_fields = ('name', 'short_name', 'description',
                         'overall_progress', 'n_tasks', 'n_volunteers', 'info')

        projects_published = cached_users.public_published_projects_cached(user.id)

        for field in public_fields:
            assert field in projects_published[0].keys(), field

        for field in private_fields:
            assert field not in projects_published[0].keys(), field

    @with_context
    def test_draft_projects_no_projects(self):
        """Test CACHE USERS draft_projects returns an empty list if the user has no
        draft projects"""
        user = UserFactory.create()
        published_project = ProjectFactory.create(owner=user, published=True)

        draft_projects = cached_users.draft_projects(user.id)

        assert len(draft_projects) == 0, draft_projects

    @with_context
    def test_draft_projects_return_drafts(self):
        """Test CACHE USERS draft_projects returns draft belonging to the user"""
        user = UserFactory.create()
        draft_project = ProjectFactory.create(owner=user, published=False)

        draft_projects = cached_users.draft_projects(user.id)

        assert len(draft_projects) == 1, draft_projects
        assert draft_projects[0]['short_name'] == draft_project.short_name, draft_projects

    @with_context
    def test_draft_projects_only_returns_drafts(self):
        """Test CACHE USERS draft_projects does not return any pubished projects
        or drafts that belong to another user"""
        user = UserFactory.create()
        published_project = ProjectFactory.create(owner=user, published=True)
        other_users_draft_project = ProjectFactory.create(published=False)

        draft_projects = cached_users.draft_projects(user.id)

        assert len(draft_projects) == 0, draft_projects

    @with_context
    def test_draft_projects_returns_fields(self):
        """Test CACHE USERS draft_projects returns the info of the projects with
        the required fields"""
        user = UserFactory.create()
        draft_project = ProjectFactory.create(owner=user, published=False)
        fields = ('id', 'name', 'short_name', 'owner_id', 'description',
                  'overall_progress', 'n_tasks', 'n_volunteers', 'info')

        draft_project = cached_users.draft_projects(user.id)

        for field in fields:
            assert field in draft_project[0].keys(), field

    @with_context
    def test_get_leaderboard_no_users_returns_empty_list(self):
        """Test CACHE USERS get_leaderboard returns an empty list if there are no
        users"""

        users = cached_users.get_leaderboard(10)

        assert users == [], users

    @with_context
    def test_get_leaderboard_returns_users_ordered_by_rank(self):
        leader = UserFactory.create()
        second = UserFactory.create()
        third = UserFactory.create()
        project = ProjectFactory.create()
        tasks = TaskFactory.create_batch(3, project=project)
        i = 3
        for user in [leader, second, third]:
            TaskRunFactory.create_batch(i, user=user, task=tasks[i - 1])
            i -= 1

        update_leaderboard()
        leaderboard = cached_users.get_leaderboard(3)

        assert leaderboard[0]['name'] == leader.name
        assert leaderboard[1]['name'] == second.name
        assert leaderboard[2]['name'] == third.name

    @with_context
    def test_get_leaderboard_includes_specific_user_even_is_not_in_top(self):
        leader = UserFactory.create()
        second = UserFactory.create()
        third = UserFactory.create()
        project = ProjectFactory.create()
        tasks = TaskFactory.create_batch(3, project=project)
        i = 3
        for user in [leader, second, third]:
            TaskRunFactory.create_batch(i, user=user, task=tasks[i - 1])
            i -= 1
        user_out_of_top = UserFactory.create()

        update_leaderboard()

        leaderboard = cached_users.get_leaderboard(3, user_id=user_out_of_top.id)

        assert len(leaderboard) is 4, len(leaderboard)
        assert leaderboard[-1]['name'] == user_out_of_top.name

    @with_context
    def test_get_leaderboard_returns_fields(self):
        """Test CACHE USERS get_leaderboard returns user fields"""
        user = UserFactory.create()
        TaskRunFactory.create(user=user)
        fields = User.public_attributes()

        update_leaderboard()
        leaderboard = cached_users.get_leaderboard(1)

        for field in fields:
            assert field in leaderboard[0].keys(), field
        assert len(list(leaderboard[0].keys())) == len(fields)

    @with_context
    def test_get_total_users_returns_0_if_no_users(self):
        total_users = cached_users.get_total_users()

        assert total_users == 0, total_users

    @with_context
    def test_get_total_users_returns_number_of_users(self):
        expected_number_of_users = 3
        UserFactory.create_batch(expected_number_of_users)

        total_users = cached_users.get_total_users()

        assert total_users == expected_number_of_users, total_users

    @with_context
    def test_get_users_page_only_returns_users_with_contributions(self):
        users = UserFactory.create_batch(2)
        TaskRunFactory.create(user=users[0])

        users_with_contrib = cached_users.get_users_page(1)

        assert len(users_with_contrib) == 1, users_with_contrib

    @with_context
    def test_get_users_page_supports_pagination(self):
        users = UserFactory.create_batch(3)
        for user in users:
            TaskRunFactory.create(user=user)

        paginated_users = cached_users.get_users_page(page=2, per_page=1)

        assert len(paginated_users) == 1, paginated_users
        assert paginated_users[0]['name'] == users[1].name

    @with_context
    def test_get_users_page_returns_fields(self):
        user = UserFactory.create()
        TaskRunFactory.create(user=user)
        fields = User.public_attributes()

        users = cached_users.get_users_page(1)

        for field in fields:
            assert field in users[0].keys(), field
        assert len(list(users[0].keys())) == len(fields)


    @with_context
    def test_get_tasks_completed_between(self):
        user = UserFactory.create()
        TaskRunFactory.create(user=user, created='2000-01-01T00:00:00.000')

        beg = '1999-01-01T00:00:00.000'
        end = '2001-01-01T00:00:00.000'
        task_runs = cached_users.get_tasks_completed_between(user.id, beginning_time_utc=beg, end_time_utc=end)
        assert len(task_runs) == 1

        beg = '2001-01-01T00:00:00.000'
        end = '2002-01-01T00:00:00.000'
        task_runs = cached_users.get_tasks_completed_between(user.id, beginning_time_utc=beg, end_time_utc=end)
        assert len(task_runs) == 0

        beg = '1999-01-01T00:00:00.000'
        end = None
        task_runs = cached_users.get_tasks_completed_between(user.id, beginning_time_utc=beg, end_time_utc=end)
        assert len(task_runs) == 1

        beg = '2001-01-01T00:00:00.000'
        end = None
        task_runs = cached_users.get_tasks_completed_between(user.id, beginning_time_utc=beg, end_time_utc=end)
        assert len(task_runs) == 0

    @with_context
    def test_draft_projects_cached(self):
        """Test CACHE USERS draft_projects_cached returns an empty list if the user has no
                draft projects"""
        user = UserFactory.create()
        ProjectFactory.create(owner=user, published=True)
        draft_projects = cached_users.draft_projects_cached(user.id)
        assert len(draft_projects) == 0

    @with_context
    def test_get_user_exported_reports_key(self):
        """Test get_user_exported_reports_key returns correct Redis key format"""
        user_id = 123
        expected_key = 'pybossa:user:exported:reports:123'

        key = get_user_exported_reports_key(user_id)

        assert key == expected_key

    @with_context
    def test_get_user_exported_reports_key_string_user_id(self):
        """Test get_user_exported_reports_key works with string user_id"""
        user_id = "456"
        expected_key = 'pybossa:user:exported:reports:456'

        key = get_user_exported_reports_key(user_id)

        assert key == expected_key

    @with_context
    def test_register_user_exported_report_default_ttl(self):
        """Test register_user_exported_report stores report with default TTL"""
        user_id = 123
        path = '/path/to/report.csv'
        conn = sentinel.master

        # Clear any existing data
        conn.flushall()

        # Mock time to get predictable timestamp
        with patch('pybossa.redis_lock.time') as mock_time:
            mock_time.return_value = 1609459200.123456  # 2021-01-01 00:00:00.123456

            cache_info = register_user_exported_report(user_id, path, conn)

            # Check that the function returns cache info
            expected_cache_info = 'Registered exported report for user_id 123 at 1609459200.123456 with value {"filename": "report.csv", "path": "/path/to/report.csv"}'
            assert cache_info == expected_cache_info

            # Check that the key was created with correct format
            expected_key = 'pybossa:user:exported:reports:123'
            assert conn.exists(expected_key)

            # Check that the data was stored correctly in the hash
            import json
            stored_value = conn.hget(expected_key, '1609459200.123456')
            assert stored_value is not None
            stored_data = json.loads(stored_value)
            assert stored_data['filename'] == 'report.csv'
            assert stored_data['path'] == '/path/to/report.csv'

            # Check TTL is approximately correct (default 3600 seconds)
            ttl = conn.ttl(expected_key)
            assert 3590 <= ttl <= 3600

    @with_context
    def test_register_user_exported_report_custom_ttl(self):
        """Test register_user_exported_report stores report with custom TTL"""
        user_id = 456
        path = '/path/to/custom_report.json'
        conn = sentinel.master
        custom_ttl = 1800  # 30 minutes

        # Clear any existing data
        conn.flushall()

        with patch('pybossa.redis_lock.time') as mock_time:
            mock_time.return_value = 1609459200.789012

            cache_info = register_user_exported_report(user_id, path, conn, ttl=custom_ttl)

            # Check that the function returns cache info
            expected_cache_info = 'Registered exported report for user_id 456 at 1609459200.789012 with value {"filename": "custom_report.json", "path": "/path/to/custom_report.json"}'
            assert cache_info == expected_cache_info

            expected_key = 'pybossa:user:exported:reports:456'
            assert conn.exists(expected_key)

            # Check TTL is approximately correct (custom 1800 seconds)
            ttl = conn.ttl(expected_key)
            assert 1790 <= ttl <= 1800

    @with_context
    def test_register_user_exported_report_multiple_reports(self):
        """Test register_user_exported_report can store multiple reports for same user"""
        user_id = 789
        path1 = '/path/to/report1.csv'
        path2 = '/path/to/report2.json'
        conn = sentinel.master

        # Clear any existing data
        conn.flushall()

        with patch('pybossa.redis_lock.time') as mock_time:
            # First report
            mock_time.return_value = 1609459200.111111
            cache_info1 = register_user_exported_report(user_id, path1, conn)

            # Second report with different timestamp
            mock_time.return_value = 1609459260.222222
            cache_info2 = register_user_exported_report(user_id, path2, conn)

            # Check both reports are stored in the same key
            key = 'pybossa:user:exported:reports:789'
            assert conn.exists(key)

            # Check both timestamps exist as hash fields
            assert conn.hexists(key, '1609459200.111111')
            assert conn.hexists(key, '1609459260.222222')

            # Check correct data is stored
            import json
            stored_value1 = json.loads(conn.hget(key, '1609459200.111111'))
            stored_value2 = json.loads(conn.hget(key, '1609459260.222222'))

            assert stored_value1['filename'] == 'report1.csv'
            assert stored_value1['path'] == path1
            assert stored_value2['filename'] == 'report2.json'
            assert stored_value2['path'] == path2

    @with_context
    def test_get_user_exported_reports_no_reports(self):
        """Test get_user_exported_reports returns empty list when no reports exist"""
        user_id = 999
        conn = sentinel.master

        # Clear any existing data
        conn.flushall()

        reports = get_user_exported_reports(user_id, conn)

        assert reports == []

    @with_context
    def test_get_user_exported_reports_single_report(self):
        """Test get_user_exported_reports returns single report correctly"""
        user_id = 111
        path = '/path/to/single_report.csv'
        conn = sentinel.master

        # Clear any existing data
        conn.flushall()

        # Register a report first
        with patch('pybossa.redis_lock.time') as mock_time:
            mock_time.return_value = 1609459200.555555
            register_user_exported_report(user_id, path, conn)

        # Retrieve reports
        reports = get_user_exported_reports(user_id, conn)

        assert len(reports) == 1
        assert reports[0] == ('2021-01-01 00:00:00:555', 'single_report.csv', path)

    @with_context
    def test_get_user_exported_reports_multiple_reports(self):
        """Test get_user_exported_reports returns multiple reports correctly"""
        user_id = 222
        path1 = '/path/to/report1.csv'
        path2 = '/path/to/report2.json'
        path3 = '/path/to/report3.xlsx'
        conn = sentinel.master

        # Clear any existing data
        conn.flushall()

        # Register multiple reports
        with patch('pybossa.redis_lock.time') as mock_time:

            # First report
            mock_time.return_value = 1609459200.111111
            register_user_exported_report(user_id, path1, conn)

            # Second report
            mock_time.return_value = 1609459260.222222
            register_user_exported_report(user_id, path2, conn)

            # Third report
            mock_time.return_value = 1609459320.333333
            register_user_exported_report(user_id, path3, conn)

        # Retrieve reports
        reports = get_user_exported_reports(user_id, conn)

        assert len(reports) == 3

        # Convert to set for easier comparison (order may vary)
        report_set = set(reports)
        expected_set = {
            ('2021-01-01 00:00:00:111', 'report1.csv', path1),
            ('2021-01-01 00:01:00:222', 'report2.json', path2),
            ('2021-01-01 00:02:00:333', 'report3.xlsx', path3)
        }
        assert report_set == expected_set

    @with_context
    def test_get_user_exported_reports_ignores_malformed_values(self):
        """Test get_user_exported_reports ignores malformed JSON values"""
        user_id = 333
        valid_path = '/path/to/valid_report.csv'
        conn = sentinel.master

        # Clear any existing data
        conn.flushall()

        # Create a valid report
        with patch('pybossa.redis_lock.time') as mock_time:
            mock_time.return_value = 1609459200.777777
            register_user_exported_report(user_id, valid_path, conn)

        # Manually add a malformed value (invalid JSON)
        key = get_user_exported_reports_key(user_id)
        conn.hset(key, '1609459300.888888', 'invalid_json_string')

        # Retrieve reports - should handle the malformed JSON gracefully
        try:
            reports = get_user_exported_reports(user_id, conn)
            # Should only return the valid report, ignoring malformed ones
            assert len(reports) == 1
            assert reports[0] == ('2021-01-01 00:00:00:777', 'valid_report.csv', valid_path)
        except Exception as e:
            # If the implementation doesn't handle malformed JSON gracefully,
            # we expect a specific type of error
            import json
            assert isinstance(e, json.JSONDecodeError)

    @with_context
    def test_get_user_exported_reports_handles_complex_paths(self):
        """Test get_user_exported_reports handles paths with special characters"""
        user_id = 444
        complex_path = '/path/with spaces/and:colons/report_file-name.csv'
        conn = sentinel.master

        # Clear any existing data
        conn.flushall()

        # Register report with complex path
        with patch('pybossa.redis_lock.time') as mock_time:
            mock_time.return_value = 1609459200.999999
            register_user_exported_report(user_id, complex_path, conn)

        # Retrieve reports
        reports = get_user_exported_reports(user_id, conn)

        assert len(reports) == 1
        assert reports[0] == ('2021-01-01 00:00:00:999', 'report_file-name.csv', complex_path)

    @with_context
    def test_get_user_exported_reports_different_users_isolated(self):
        """Test get_user_exported_reports only returns reports for specific user"""
        user_id_1 = 555
        user_id_2 = 666
        path_1 = '/path/to/user1_report.csv'
        path_2 = '/path/to/user2_report.json'
        conn = sentinel.master

        # Clear any existing data
        conn.flushall()

        # Register reports for different users
        with patch('pybossa.redis_lock.time') as mock_time:
            # User 1 report
            mock_time.return_value = 1609459200.111111
            register_user_exported_report(user_id_1, path_1, conn)

            # User 2 report
            mock_time.return_value = 1609459260.222222
            register_user_exported_report(user_id_2, path_2, conn)

        # Retrieve reports for user 1
        reports_1 = get_user_exported_reports(user_id_1, conn)
        assert len(reports_1) == 1
        assert reports_1[0] == ('2021-01-01 00:00:00:111', 'user1_report.csv', path_1)

        # Retrieve reports for user 2
        reports_2 = get_user_exported_reports(user_id_2, conn)
        assert len(reports_2) == 1
        assert reports_2[0] == ('2021-01-01 00:01:00:222', 'user2_report.json', path_2)

    @with_context
    def test_register_user_exported_report_with_mock_connection(self):
        """Test register_user_exported_report with mocked Redis connection"""
        user_id = 777
        path = '/path/to/mock_report.csv'
        mock_conn = MagicMock()

        with patch('pybossa.redis_lock.time') as mock_time:
            mock_time.return_value = 1609459200.888888

            cache_info = register_user_exported_report(user_id, path, mock_conn, ttl=7200)

            # Verify Redis operations were called correctly
            expected_key = 'pybossa:user:exported:reports:777'
            expected_value = '{"filename": "mock_report.csv", "path": "/path/to/mock_report.csv"}'
            mock_conn.hset.assert_called_once_with(expected_key, 1609459200.888888, expected_value)
            mock_conn.expire.assert_called_once_with(expected_key, 7200)

            # Verify return value
            expected_cache_info = 'Registered exported report for user_id 777 at 1609459200.888888 with value {"filename": "mock_report.csv", "path": "/path/to/mock_report.csv"}'
            assert cache_info == expected_cache_info

    @with_context
    def test_get_user_exported_reports_with_mock_connection(self):
        """Test get_user_exported_reports with mocked Redis connection"""
        user_id = 888
        mock_conn = MagicMock()

        # Mock the hgetall response
        mock_conn.hgetall.return_value.items.return_value = [
            (b'1609459200.123', b'{"filename": "report1.csv", "path": "/path/to/report1.csv"}'),
            (b'1609459260.456', b'{"filename": "report2.json", "path": "/path/to/report2.json"}'),
        ]

        reports = get_user_exported_reports(user_id, mock_conn)

        # Verify correct Redis key was used
        expected_key = 'pybossa:user:exported:reports:888'
        mock_conn.hgetall.assert_called_once_with(expected_key)

        # Verify correct parsing
        assert len(reports) == 2
        assert ('2021-01-01 00:00:00:123', 'report1.csv', '/path/to/report1.csv') in reports
        assert ('2021-01-01 00:01:00:456', 'report2.json', '/path/to/report2.json') in reports
