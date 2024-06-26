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

from unittest.mock import patch
from test.helper import sched
from test import with_context
from pybossa.core import project_repo, task_repo, user_repo
from pybossa.jobs import send_email_notifications
from test.factories import TaskFactory, ProjectFactory, UserFactory, TaskRunFactory
from pybossa.sched import get_user_pref_task, Schedulers
from pybossa.cache.helpers import n_available_tasks_for_user
from pybossa.cache.users import get_user_preferences
import datetime
from test.helper.gig_helper import make_admin, make_subadmin
import json


class TestSched(sched.Helper):

    map_locations = {
        'country_codes': ['US'],
        'country_names': ['United States'],
        'locations': ['US', 'United States']
    }

    @with_context
    def test_no_pref(self):
        """
        User and task don't have preferences
        """
        owner = UserFactory.create(id=500)
        project = ProjectFactory.create(owner=owner)
        TaskFactory.create_batch(1, project=project, n_answers=10)
        tasks = get_user_pref_task(1, 500)
        assert tasks

    @with_context
    def test_task_no_pref(self):
        """
        User has preferences set, task doesn't
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['en']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        TaskFactory.create_batch(1, project=project, n_answers=10)
        tasks = get_user_pref_task(1, 500)
        assert tasks

    @with_context
    def test_no_user_pref(self):
        """
        Task has preferences set, user doesn't
        """
        owner = UserFactory.create(id=500)
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en', 'de']}
        task_repo.save(task)
        tasks = get_user_pref_task(1, 500)
        assert not tasks

    @with_context
    def test_task_0(self):
        """
        Task has multiple preferences, user has single preference; match
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['en']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en', 'de']}
        task_repo.save(task)
        tasks = get_user_pref_task(1, 500)
        assert tasks

    @with_context
    def test_task_1(self):
        """
        Task has single preference, user has multiple preferences; match
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['en', 'de']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en']}
        task_repo.save(task)
        tasks = get_user_pref_task(1, 500)
        assert tasks

    @with_context
    def test_task_2(self):
        """
        Task has multiple preferences, user has multiple preferences; match
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['en', 'de']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en', 'es']}
        task_repo.save(task)
        tasks = get_user_pref_task(1, 500)
        assert tasks

    @with_context
    def test_task_3(self):
        """
        User has single preference, task has single preference, no match
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en']}
        task_repo.save(task)
        tasks = get_user_pref_task(1, 500)
        assert not tasks

    @with_context
    @patch('pybossa.cache.users.map_locations')
    def test_task_4(self, map_locations):
        """
        User has multiple preferences of different kinds,
        task has single preference, match
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de'], 'locations': ['us']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['de']}
        task_repo.save(task)
        map_locations.return_value = self.map_locations
        tasks = get_user_pref_task(1, 500)
        assert tasks

    @with_context
    @patch('pybossa.cache.users.map_locations')
    def test_task_5(self, map_locations):
        """
        User has multiple preferences of different kinds,
        task has single preference, match
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de'], 'locations': ['us']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'locations': ['us']}
        task_repo.save(task)
        map_locations.return_value = self.map_locations
        tasks = get_user_pref_task(1, 500)
        assert tasks

    @with_context
    @patch('pybossa.cache.users.map_locations')
    def test_task_6(self, map_locations):
        """
        User has multiple preferences of different kinds,
        task has multiple preferences of different kinds, no match
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de'], 'locations': ['us']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en', 'zh'], 'locations': ['es']}
        task_repo.save(task)
        map_locations.return_value = self.map_locations
        tasks = get_user_pref_task(1, 500)
        assert not tasks

    @with_context
    def test_task_7(self):
        """
        Invalid user preference
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': 'invalid_user_pref'}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en', 'zh']}
        task_repo.save(task)
        tasks = get_user_pref_task(1, 500)
        assert not tasks

    @with_context
    @patch('pybossa.cache.users.map_locations')
    def test_get_user_preferences_cc(self, map_locations):
        """
        Test mapping from country code to country name
        """
        user = UserFactory.create()
        user.user_pref = {'locations': ['US']}
        user_repo.save(user)

        map_locations.return_value = self.map_locations

        prefs = get_user_preferences(user.id)
        assert 'us' in prefs and 'united states' in prefs

    @with_context
    @patch('pybossa.cache.users.map_locations')
    def test_get_user_preferences_cn(self, map_locations):
        """
        Test mapping from country name to country code
        """
        user = UserFactory.create()
        user.user_pref = {'locations': ['United States']}
        user_repo.save(user)

        map_locations.return_value = self.map_locations

        prefs = get_user_preferences(user.id)

        assert 'us' in prefs and 'united states' in prefs

    @with_context
    @patch('pybossa.cache.users.map_locations')
    def test_get_user_preferences_invalid(self, map_locations):
        """
        Test invalid location preference
        """
        user = UserFactory.create()
        user.user_pref = {'locations': ['invalid country']}
        user_repo.save(user)

        map_locations.return_value = {
        'country_codes': [],
        'country_names': [],
        'locations': ['invalid country']
    }

        prefs = get_user_preferences(user.id)

        assert 'invalid country' in prefs

    @with_context
    def test_get_unique_user_pref(self):
        """
        Test get_unique_user_preferences returns unique user preferences
        upon flattening input user preferences
        """

        from pybossa.util import get_unique_user_preferences

        user_prefs = [{'languages': ['en'], 'locations': ['us']}, {'languages': ['en', 'ru']}]
        duser_prefs = get_unique_user_preferences(user_prefs)
        err_msg = 'There should be 3 unique user_prefs after dropping 1 duplicate user_pref'
        assert len(duser_prefs) == 3, err_msg

        err_msg = 'user_pref mismatch; duplicate user_pref languages as en should be dropped'
        expected_user_pref = set(['\'{"languages": ["en"]}\'', '\'{"languages": ["ru"]}\'', '\'{"locations": ["us"]}\''])
        assert duser_prefs == expected_user_pref, err_msg

    @with_context
    def test_recent_contributors_list_as_per_user_pref(self):
        """
        Notify users about new tasks imported based on user preference and those who were not notified previously
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['en']}         # owner is english user
        user_repo.save(owner)
        ch_user = UserFactory.create(id=501)
        ch_user.user_pref = {'languages': ['ch']}       # chinese language user
        user_repo.save(ch_user)
        ru_user = UserFactory.create(id=502)
        ru_user.user_pref = {'languages': ['ru']}       # russian language user
        user_repo.save(ru_user)

        # Stage 1 :
        # Create 4 tasks - 3 english, 1 chinese.
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(4, project=project, n_answers=1)
        tasks[0].user_pref = {'languages': ['en']}
        task_repo.save(tasks[0])
        tasks[1].user_pref = {'languages': ['en']}
        task_repo.save(tasks[1])
        tasks[2].user_pref = {'languages': ['ru']}
        task_repo.save(tasks[2])
        tasks[3].user_pref = {'languages': ['ch']}
        task_repo.save(tasks[3])

        # Complete 2 english and 1 russian tasks
        # completing 1 russian task will mark all russian tasks completed
        # and such users to be notified about new task imported
        taskrun1 = TaskRunFactory.create(task=tasks[0], user=owner)
        taskrun2 = TaskRunFactory.create(task=tasks[1], user=owner)
        taskrun3 = TaskRunFactory.create(task=tasks[2], user=ru_user)

        # Stage 2 :
        # create 3 more tasks; 2 russian and 1 chinese

        # at this stage, record current time.
        # chinese user has existing ongoing task, hence won't be notified
        # russian user has all tasks completed, hence will be notified
        now = datetime.datetime.utcnow().isoformat()

        tasks = TaskFactory.create_batch(3, project=project, n_answers=1)
        tasks[0].user_pref = {'languages': ['ru']}
        task_repo.save(tasks[0])
        tasks[1].user_pref = {'languages': ['ru']}
        task_repo.save(tasks[1])
        tasks[2].user_pref = {'languages': ['ch']}
        task_repo.save(tasks[2])

        recent_contributors = user_repo.get_user_pref_recent_contributor_emails(project.id, now)
        # with russian task completed, russian user will be notified about new task imported
        err_msg = 'There should be 1 contributors'
        assert len(recent_contributors) == 1, err_msg

        err_msg = 'only user3 that has language preference russian should be notified'
        assert recent_contributors[0] == 'user3@test.com', err_msg

    @with_context
    def test_recent_contributors_list_with_multiple_user_pref(self):
        """
        User with multiple user pref to be excluded from notifying when there are
        existing ongoing tasks matching any one of same user pref
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['en']}                 # owner is english user
        user_repo.save(owner)
        sp_fr_user = UserFactory.create(id=501)
        sp_fr_user.user_pref = {'languages': ['sp', 'fr']}      # spanish french language user
        user_repo.save(sp_fr_user)
        ch_user = UserFactory.create(id=502)
        ch_user.user_pref = {'languages': ['ch']}               # russian language user
        user_repo.save(ch_user)

        # Stage 1 :
        # Create 4 tasks - 3 english, 1 chinese.
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(6, project=project, n_answers=1)
        tasks[0].user_pref = {'languages': ['en']}
        task_repo.save(tasks[0])
        tasks[1].user_pref = {'languages': ['sp']}
        task_repo.save(tasks[1])
        tasks[2].user_pref = {'languages': ['sp']}
        task_repo.save(tasks[2])
        tasks[3].user_pref = {'languages': ['fr']}
        task_repo.save(tasks[3])
        tasks[4].user_pref = {'languages': ['fr']}
        task_repo.save(tasks[4])
        tasks[5].user_pref = {'languages': ['ch']}
        task_repo.save(tasks[5])

        # Submit 1 english and chinese task runs. this will complete
        # such tasks and assoicated users to be notified about new task imported
        taskrun1 = TaskRunFactory.create(task=tasks[0], user=owner)
        taskrun2 = TaskRunFactory.create(task=tasks[5], user=ch_user)
        # Submit 1 spanish and 1 french task runs. since there are 1 each onging
        # tasks, assoicated users wont be notified about new task imported
        taskrun1 = TaskRunFactory.create(task=tasks[1], user=sp_fr_user)
        taskrun2 = TaskRunFactory.create(task=tasks[3], user=sp_fr_user)

        # Stage 2 :
        # create 3 more tasks; 1 spanish, 1 french and 1 chinese

        # at this stage, record current time.
        # spanish and french user has existing ongoing task, hence won't be notified
        # chinese and english user has all tasks completed, hence will be notified
        now = datetime.datetime.utcnow().isoformat()

        tasks = TaskFactory.create_batch(4, project=project, n_answers=1)
        tasks[0].user_pref = {'languages': ['en']}
        task_repo.save(tasks[0])
        tasks[1].user_pref = {'languages': ['sp']}
        task_repo.save(tasks[1])
        tasks[2].user_pref = {'languages': ['fr']}
        task_repo.save(tasks[2])
        tasks[3].user_pref = {'languages': ['ch']}
        task_repo.save(tasks[3])

        recent_contributors = user_repo.get_user_pref_recent_contributor_emails(project.id, now)
        # with english and chinese task completed, two such user will be notified about new task imported
        err_msg = 'There should be 2 contributors'
        assert len(recent_contributors) == 2, err_msg
        err_msg = 'user1 and user3 with english and chinese language preference should be notified'
        assert ('user1@test.com' in recent_contributors and
                'user3@test.com' in recent_contributors and
                'user2@test.com' not in recent_contributors), err_msg

    @with_context
    def test_recent_contributor_with_multiple_user_pref_notified(self):
        """
        User with multiple user pref to be notified when one of his/her
        user pref matches any new task user pref
        """
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['en']}                 # owner is english user
        user_repo.save(owner)
        sp_fr_user = UserFactory.create(id=501)
        sp_fr_user.user_pref = {'languages': ['sp', 'fr']}      # spanish french language user
        user_repo.save(sp_fr_user)

        # Stage 1 :
        # Create 3 tasks - 1 english, 1 spanish, 1 french.
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(6, project=project, n_answers=1)
        tasks[0].user_pref = {'languages': ['en']}
        task_repo.save(tasks[0])
        tasks[1].user_pref = {'languages': ['sp']}
        task_repo.save(tasks[1])
        tasks[2].user_pref = {'languages': ['fr']}
        task_repo.save(tasks[2])

        # Submit 1 english and spanish tasks. this will complete
        # such tasks and assoicated users to be notified about new task imported
        taskrun1 = TaskRunFactory.create(task=tasks[0], user=owner)
        taskrun2 = TaskRunFactory.create(task=tasks[1], user=sp_fr_user)

        # Stage 2 :
        # create 1 spanish task
        # at this stage, record current time.
        # there is french ongoing task, but since spanish task is complete
        # sp_fr_user will be notified
        now = datetime.datetime.utcnow().isoformat()

        tasks = TaskFactory.create_batch(1, project=project, n_answers=1)
        tasks[0].user_pref = {'languages': ['sp']}
        task_repo.save(tasks[0])
        recent_contributors = user_repo.get_user_pref_recent_contributor_emails(project.id, now)
        # with one spanish task completed, user2 will be notified about new spanish task imported
        err_msg = 'There should be 1 contributors'
        assert len(recent_contributors) == 1, err_msg
        err_msg = 'user1 and user3 with english and chinese language preference should be notified'
        assert 'user2@test.com' in recent_contributors, err_msg

    @with_context
    @patch('pybossa.jobs.user_repo.get_user_pref_recent_contributor_emails')
    def test_no_email_notif(self, get_contrib_emails):
        """
        if the project is not configured, email notifications won't be sent
        """
        owner = UserFactory.create(id=500, user_pref={'languages': ['en']})

        project = ProjectFactory.create(owner=owner, email_notif=False)
        project.info['sched'] = Schedulers.user_pref
        project_repo.save(project)
        tasks = TaskFactory.create_batch(1, project=project, n_answers=1,
                                         user_pref={'languages': ['en']})

        TaskRunFactory.create(task=tasks[0], user=owner)

        TaskFactory.create_batch(1, project=project, n_answers=1,
                                 user_pref={'languages': ['en']})
        send_email_notifications()
        get_contrib_emails.assert_not_called()

    @with_context
    @patch('pybossa.jobs.user_repo.get_user_pref_recent_contributor_emails')
    def test_email_notif(self, get_contrib_emails):
        """
        if the project is configured, email notifications will be sent
        """
        owner = UserFactory.create(id=500, user_pref={'languages': ['en']})

        project = ProjectFactory.create(owner=owner, email_notif=True)
        project.info['sched'] = Schedulers.user_pref
        project_repo.save(project)
        tasks = TaskFactory.create_batch(1, project=project, n_answers=1,
                                         user_pref={'languages': ['en']})

        TaskRunFactory.create(task=tasks[0], user=owner)

        TaskFactory.create_batch(1, project=project, n_answers=1,
                                 user_pref={'languages': ['en']})
        send_email_notifications()
        get_contrib_emails.assert_called()

    @with_context
    @patch('pybossa.jobs.user_repo.get_user_pref_recent_contributor_emails')
    def test_email_notif_with_email_addr(self, get_contrib_emails):
        """
        if the project is configured, email notifications will be sent
        """
        get_contrib_emails.return_value = ["dummy@dummy.com"]
        owner = UserFactory.create(id=500, user_pref={'languages': ['en']})

        project = ProjectFactory.create(owner=owner, email_notif=True)
        project.info['sched'] = Schedulers.user_pref
        project_repo.save(project)
        tasks = TaskFactory.create_batch(1, project=project, n_answers=1,
                                         user_pref={'languages': ['en']})

        TaskRunFactory.create(task=tasks[0], user=owner)

        TaskFactory.create_batch(1, project=project, n_answers=1,
                                 user_pref={'languages': ['en']})
        send_email_notifications()
        get_contrib_emails.assert_called()


class TestNTaskAvailable(sched.Helper):

    @with_context
    def test_task_0(self):
        '''
        Task doesn't match user profile
        '''
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en', 'zh']}
        task_repo.save(task)
        assert n_available_tasks_for_user(project, 500) == 0

    @with_context
    def test_task_1(self):
        '''
        Default user scheduler doesn't check user preference
        '''
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.locked
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en', 'zh']}
        task_repo.save(task)
        assert n_available_tasks_for_user(project, 500) == 1

    @with_context
    def test_task_2(self):
        '''
        Task matches user profile
        '''
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de', 'en']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['en', 'zh']}
        task_repo.save(task)
        assert n_available_tasks_for_user(project, 500) == 1

    @with_context
    def test_task_3(self):
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de', 'en']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(2, project=project, n_answers=10)
        tasks[0].user_pref = {'languages': ['en', 'zh']}
        task_repo.save(tasks[0])
        tasks[1].user_pref = {'languages': ['zh']}
        task_repo.save(tasks[0])
        assert n_available_tasks_for_user(project, 500) == 1

    @with_context
    def test_task_4(self):
        '''
        Tasks match user profile
        '''
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de', 'en']}
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(2, project=project, n_answers=10)
        tasks[0].user_pref = {'languages': ['en', 'zh']}
        task_repo.save(tasks[0])
        tasks[1].user_pref = {'languages': ['de']}
        task_repo.save(tasks[1])
        assert n_available_tasks_for_user(project, 500) == 2

    @with_context
    def test_task_5(self):

        from pybossa import data_access

        owner = UserFactory.create(id=500)
        user = UserFactory.create(id=501, info=dict(data_access=["L1"]))
        patch_data_access_levels = dict(
            valid_access_levels=["L1", "L2", "L3", "L4"],
            valid_user_levels_for_project_level=dict(L1=[], L2=["L1"]),
            valid_project_levels_for_user_level=dict(L1=["L2", "L3", "L4"], L2=["L3", "L4"]),
        )

        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner, info=dict(project_users=[owner.id]))
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(3, project=project, n_answers=2, info=dict(data_access=["L1"]))
        tasks[0].info['data_access'] = ["L1"]
        task_repo.save(tasks[0])
        tasks[1].info['data_access'] = ["L1"]
        task_repo.save(tasks[1])
        tasks[2].info['data_access'] = ["L2"]
        task_repo.save(tasks[2])

        with patch.object(data_access, 'data_access_levels', patch_data_access_levels):
            assert n_available_tasks_for_user(project, 501) == 3

    @with_context
    def test_task_6(self):
        '''
        Task is assigned to a user whose profile doesn't match task preference
        '''
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de', 'en']}
        owner.email_addr = 'test@test.com'
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        task = TaskFactory.create_batch(1, project=project, n_answers=10)[0]
        task.user_pref = {'languages': ['ch', 'zh'], 'assign_user': ['test@test.com']}
        task_repo.save(task)
        assert n_available_tasks_for_user(project, 500) == 0

    @with_context
    def test_task_7(self):
        '''
        task[0]: doesn't have any language/country preference, should be able to
        assign to the user.
        task[1]: both preference and email match, should be able to assign to the user
        '''
        owner = UserFactory.create(id=500)
        owner.user_pref = {'languages': ['de', 'en']}
        owner.email_addr = 'test@test.com'
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(3, project=project, n_answers=10)
        tasks[0].user_pref = {'assign_user': ['test@test.com']}
        task_repo.save(tasks[0])
        tasks[1].user_pref = {'languages': ['de'], 'assign_user': ['dummy@dummy.com']}
        task_repo.save(tasks[1])
        assert n_available_tasks_for_user(project, 500) == 2

    @with_context
    def test_task_routing_1(self):
        '''
        task[0]: needs finance skill at least 0.4, should be able to assign to the user
        task[1]: needs marketing skill at least 0.3, should be able to assign to the user
        task[3]: doesnt have filters, should be able to assign to the user
        '''
        user_info = dict(metadata={"profile": json.dumps({"finance": 0.6, "marketing": 0.4})})
        owner = UserFactory.create(id=500, info=user_info)
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(3, project=project, n_answers=10)
        tasks[0].worker_filter = {'finance': [0.4, '>=']}
        task_repo.save(tasks[0])
        tasks[1].worker_filter = {'marketing': [0.3, '>=']}
        task_repo.save(tasks[1])
        assert n_available_tasks_for_user(project, 500) == 3

    @with_context
    def test_task_routing_2(self):
        '''
        task[0]: needs finance skill at least 0.8, should not be able to assign to the user
        task[1]: needs geography skill at least 0.5, should not be able to assign to the user
        task[3]: doesnt have filters, should be able to assign to the user
        '''
        user_info = dict(metadata={"profile": json.dumps({"finance": 0.6, "marketing": 0.4})})
        owner = UserFactory.create(id=500, info=user_info)
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(3, project=project, n_answers=10)
        tasks[0].worker_filter = {'finance': [0.8, '>=']}
        task_repo.save(tasks[0])
        tasks[1].worker_filter = {'geography': [0.5, '>=']}
        task_repo.save(tasks[1])
        assert n_available_tasks_for_user(project, 500) == 1

    @with_context
    def test_task_routing_3(self):
        '''
        User has empty profile set, only tasks that have empty filter can be assigned to user
        '''
        user_info = dict(metadata={"profile": json.dumps({})})
        owner = UserFactory.create(id=500, info=user_info)
        user_repo.save(owner)
        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        tasks = TaskFactory.create_batch(3, project=project, n_answers=10)
        tasks[0].worker_filter = {'finance': [0.8, '>=']}
        task_repo.save(tasks[0])
        tasks[1].worker_filter = {'geography': [0.5, '>=']}
        task_repo.save(tasks[1])
        assert n_available_tasks_for_user(project, 500) == 1

    @with_context
    def test_upref_sched_gold_task(self):
        """ Test gold tasks presented with user pref scheduler """

        [admin, owner, user] = UserFactory.create_batch(3)
        make_admin(admin)
        make_subadmin(owner)

        project = ProjectFactory.create(owner=owner)
        project.info['sched'] = Schedulers.user_pref
        project.set_gold_task_probability(1)
        project_repo.save(project)

        tasks = TaskFactory.create_batch(4, project=project, n_answers=1)
        gold_task = tasks[3]
        gold_task.calibration = 1; gold_task.gold_answers = dict(field_3='someans')

        # user #1
        self.set_proj_passwd_cookie(project, user)
        res = self.app.get('api/project/{}/newtask?api_key={}'
                           .format(project.id, user.api_key))
        assert res.status_code == 200, res.status_code
        resp = json.loads(res.data)
        assert resp['id'] == gold_task.id, \
            'task presented to regular user under user pref should be gold task'
        # submit answer for gold task
        task_run = dict(project_id=project.id, task_id=gold_task.id, info='hi there!')
        res = self.app.post('api/taskrun?api_key={}'.format(user.api_key),
                            data=json.dumps(task_run))
        assert res.status_code == 200, res.status_code

        # user #2 also gets gold_task even when redundancy was set to 1
        res = self.app.get('api/project/{}/newtask?api_key={}'
                           .format(project.id, owner.api_key))
        assert res.status_code == 200, res.status_code
        resp = json.loads(res.data)
        assert resp['id'] == gold_task.id, \
            'task presented to owner under user pref sched should be gold task'

        # after two task run submissions for gold task, state is unchanged to ongoing
        task_run = dict(project_id=project.id, task_id=gold_task.id, info='hi there!')
        res = self.app.post('api/taskrun?api_key={}'.format(owner.api_key),
                            data=json.dumps(task_run))
        assert res.status_code == 200, res.status_code
        res = self.app.get('api/task/{}?api_key={}'
                           .format(gold_task.id, admin.api_key))
        assert res.status_code == 200, res.status_code
        resp = json.loads(res.data)
        assert resp['id'] == gold_task.id and resp['state'] == 'ongoing', \
            'gold task state should be unchanged to ongoing'

        project.set_gold_task_probability(0)
        res = self.app.get('api/project/{}/newtask?api_key={}'
                           .format(project.id, admin.api_key))
        assert res.status_code == 200, res.status_code
        resp = json.loads(res.data)
        assert resp['id'] == tasks[0].id, \
            'task presented should not be gold task'
