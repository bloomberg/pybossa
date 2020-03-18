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

from pybossa.jobs import check_and_send_project_progress
from default import Test, with_context, flask_app
from factories import BlogpostFactory
from factories import TaskRunFactory
from factories import ProjectFactory
from factories import UserFactory
from mock import patch, MagicMock

queue = MagicMock()
queue.enqueue.return_value = True

class TestSendProgressReminder(Test):

    @with_context
    @patch('pybossa.cache.helpers.n_available_tasks')
    @patch('pybossa.jobs.notify_project_progress')
    def test_remaining_tasks_drop_below_configuration_1(self, notify, n_tasks):
        """Send email if remaining tasks drops below"""
        n_tasks.return_value = 0
        reminder = dict(target_remaining=0, sent=False)
        project_id = '1'
        project = ProjectFactory.create(id=project_id,
                                        owners_ids=[],
                                        published=True,
                                        featured=True,
                                        info={'progress_reminder':reminder})

        check_and_send_project_progress(project_id)
        assert notify.called
        assert project.info['progress_reminder']['sent']


    @with_context
    @patch('pybossa.cache.helpers.n_available_tasks')
    @patch('pybossa.jobs.notify_project_progress')
    def test_remaining_tasks_drop_below_configuration_2(self, notify, n_tasks):
        """Do not sent multiple email"""
        n_tasks.return_value = 0
        reminder = dict(target_remaining=0, sent=True)
        project_id = '1'
        project = ProjectFactory.create(id=project_id,
                                        owners_ids=[],
                                        published=True,
                                        featured=True,
                                        info={'progress_reminder':reminder})

        check_and_send_project_progress(project_id)
        assert not notify.called
        assert project.info['progress_reminder']['sent']



    @with_context
    @patch('pybossa.cache.helpers.n_available_tasks')
    @patch('pybossa.jobs.notify_project_progress')
    def test_remaining_tasks_do_not_drop_below_configuration(self, notify, n_tasks):
        """Do not send email if #remaining tasks is greater than configuration"""
        n_tasks.return_value = 1
        reminder = dict(target_remaining=0, sent=False)
        project_id = '1'
        project = ProjectFactory.create(id=project_id,
                                        owners_ids=[],
                                        published=True,
                                        featured=True,
                                        info={'progress_reminder':reminder})

        check_and_send_project_progress(project_id)
        assert not notify.called
        assert not project.info['progress_reminder']['sent']

