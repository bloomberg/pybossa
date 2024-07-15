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
from test import Test, with_context, flask_app, db
from test.factories import ProjectFactory, UserFactory, TaskFactory
from pybossa.jobs import delete_bulk_tasks, delete_bulk_tasks_in_batches, cleanup_task_records
from pybossa.repositories import TaskRepository
from unittest.mock import patch

task_repo = TaskRepository(db)

class TestDeleteTasks(Test):

    @with_context
    @patch('pybossa.core.db')
    @patch('pybossa.jobs.send_mail')
    def test_delete_bulk_tasks(self, mock_send_mail, mock_db):
        """Test delete_bulk_tasks deletes tasks and sends email"""
        user = UserFactory.create(admin=True)
        project = ProjectFactory.create(name='test_project')
        TaskFactory.create_batch(5, project=project)
        tasks = task_repo.filter_tasks_by(project_id=project.id)
        assert len(tasks) == 5

        data = {'project_id': project.id, 'project_name': project.name,
        'curr_user': user.email_addr, 'force_reset': 'true',
        'coowners': [], 'current_user_fullname': user.fullname,
        'url': flask_app.config.get('SERVER_URL')}

        delete_bulk_tasks(data)

        mock_db.bulkdel_session.execute.assert_called_once()

        expected_subject = "Tasks deletion from {0}".format(project.name)
        msg_str = "Hello,\n\nTasks, taskruns and results associated have been deleted from project {0} on {1} as requested by {2}\n\nThe {3} team."
        expected_body = msg_str.format(project.name,
                                       flask_app.config.get("SERVER_URL"), 
                                       user.fullname,
                                       flask_app.config.get("BRAND")
                                       )
        expected = dict(recipients=[user.email_addr], subject=expected_subject, body=expected_body)
        mock_send_mail.assert_called_once_with(expected)

    @with_context
    @patch('time.sleep')
    @patch('pybossa.jobs.cleanup_task_records')
    @patch('pybossa.core.db.session.execute')
    @patch('pybossa.jobs.send_mail')
    def test_delete_bulk_tasks_in_batches(self, mock_send_mail, mock_db, mock_cleanup_task_records, mock_sleep):
        """Test delete_bulk_tasks_in_batches deletes tasks and sends email"""
        user = UserFactory.create(admin=True)
        project = ProjectFactory.create(name='test_project')
        TaskFactory.create_batch(5, project=project)
        tasks = task_repo.filter_tasks_by(project_id=project.id)
        assert len(tasks) == 5

        data = {'project_id': 123, 'project_name': project.name,
        'curr_user': user.email_addr, 'force_reset': 'true',
        'coowners': [], 'current_user_fullname': user.fullname,
        'url': flask_app.config.get('SERVER_URL')}

        mock_db.return_value.scalar.side_effect = [102, 3, 0, 105]
        data = {'project_id': 123, 'project_name': "xyz", 'curr_user': "user@a.com",
            'force_reset': True, 'coowners': [], 'current_user_fullname': "usera", 'url': "https://a.com"
        }

        with patch.dict(self.flask_app.config, {"DELETE_BULK_TASKS_IN_BATCHES": True}):
            delete_bulk_tasks(data) #delete_bulk_tasks_in_batches(data)

        assert mock_cleanup_task_records.call_count == 2
        mock_sleep.assert_called_with(2)

        expected_subject = "Tasks deletion from {0}".format(data["project_name"])
        msg_str = "Hello,\n\nTasks, taskruns and results associated have been deleted from project {0} on {1} as requested by {2}\n\nThe {3} team."
        expected_body = msg_str.format(data["project_name"], data["url"], data["current_user_fullname"], flask_app.config.get("BRAND"))
        expected = dict(recipients=[data["curr_user"]], subject=expected_subject, body=expected_body)
        mock_send_mail.assert_called_once_with(expected)


    @with_context
    @patch('pybossa.core.db.session.execute')
    def test_cleanup_task_records(self, mock_db):
        """"Test cleanup task pick records to delete and perform cleanup from all tables"""

        project_id = 123
        limit = 100
        mock_db.return_value.fetchall.side_effect = [[(1,), (2,), (3,), (4,)]]
        cleanup_task_records(project_id, limit, force_reset=True, task_filter_args={})
        mock_db.call_count = 5


    @with_context
    @patch('pybossa.core.db.session.execute')
    def test_cleanup_task_records_without_force_reset(self, mock_db):
        """"Test cleanup task pick records to delete and perform cleanup from task table"""
        project_id = 123
        limit = 100
        mock_db.return_value.fetchall.side_effect = [[(1,), (2,), (3,), (4,)]]
        cleanup_task_records(project_id, limit, force_reset=False, task_filter_args={})
        mock_db.call_count = 2
