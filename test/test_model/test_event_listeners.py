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

from unittest.mock import patch, MagicMock

from sqlalchemy import func

from pybossa.model.event_listeners import *
from test import Test, with_context
from test.factories import TaskFactory, TaskRunFactory

"""Tests for model event listeners."""


class TestModelEventListeners(Test):

    @with_context
    @patch('pybossa.model.event_listeners.update_feed')
    def test_add_project_event(self, mock_update_feed):
        """Test add_project_event is called."""
        conn = MagicMock()
        target = MagicMock()
        tmp = Project(id=1, name='name', short_name='short_name',
                      info=dict(container=1, thumbnail="avatar.png"))
        target.id = tmp.id
        target.project_id = tmp.id
        target.name = tmp.name
        target.short_name = tmp.short_name
        target.info = tmp.info

        conn.execute.return_value = [tmp]
        add_project_event(None, conn, target)
        assert mock_update_feed.called
        obj = tmp.to_public_json()
        obj['action_updated'] = 'Project'
        mock_update_feed.assert_called_with(obj)

        mock_update_feed.assert_called_with(obj)

    @with_context
    @patch('pybossa.model.event_listeners.update_feed')
    def test_add_task_event(self, mock_update_feed):
        """Test add_task_event is called."""
        conn = MagicMock()
        target = MagicMock()
        target.id = 1
        target.project_id = 1
        tmp = Project(id=1, name='name', short_name='short_name',
                      info=dict(container=1, thumbnail="avatar.png"))
        conn.execute.return_value = [tmp]
        add_task_event(None, conn, target)
        assert mock_update_feed.called
        obj = tmp.to_public_json()
        obj['action_updated'] = 'Task'
        mock_update_feed.assert_called_with(obj)

    @with_context
    @patch('pybossa.sched.get_project_scheduler')
    @patch('pybossa.model.event_listeners.add_user_contributed_to_feed')
    @patch('pybossa.model.event_listeners.is_task_completed')
    def test_on_taskrun_submit_gold_and_published_projects(self, mock_is_task, mock_add_user,
                                                           mock_get_project_scheduler):
        """Test on_taskrun_submit only set exported = False for published projects"""
        task = TaskFactory.create(id=3, exported=True, n_answers=1, calibration=1)
        project = Project(id=1, name='name', short_name='short_name',
                      info=dict(container=1, thumbnail="avatar.png"),
                      published=True,
                      webhook='http://localhost.com')
        mock_get_project_scheduler.return_value = 'default'
        mock_task_run = MagicMock()
        mock_task_run.user_id = 42
        mock_task_run.exported = task.exported
        mock_task_run.task_id = task.id
        mock_task_run.calibration = task.calibration
        conn = MagicMock()
        conn.execute.return_value = [project]

        on_taskrun_submit(None, conn, mock_task_run)
        assert not mock_is_task.called
        expected_sql_query = ("""UPDATE task SET exported=False \
                           WHERE id=%s;""") % (task.id)
        conn.execute.assert_called_with(expected_sql_query)


    @with_context
    @patch('pybossa.model.event_listeners.sched.after_save')
    @patch('pybossa.model.event_listeners.push_webhook')
    @patch('pybossa.model.event_listeners.create_result', return_value=1)
    @patch('pybossa.model.event_listeners.update_task_state')
    @patch('pybossa.model.event_listeners.is_task_completed', return_value=True)
    @patch('pybossa.model.event_listeners.add_user_contributed_to_feed')
    @patch('pybossa.model.event_listeners.update_feed')
    def test_on_taskrun_submit_event(self, mock_update_feed,
                                     mock_add_user,
                                     mock_is_task,
                                     mock_update_task,
                                     mock_create_result,
                                     mock_push,
                                     mock_sched_after_save):
        """Test on_taskrun_submit is called."""
        conn = MagicMock()
        target = MagicMock()
        task = TaskFactory.create(id=4)
        target.id = 1
        target.project_id = 1
        target.task_id = 4
        target.user_id = 3

        tmp = Project(id=1, name='name', short_name='short_name',
                      info=dict(container=1, thumbnail="avatar.png"),
                      published=True,
                      webhook='http://localhost.com')
        conn.execute.return_value = [tmp]
        # update_feed is called during creation of other objects
        mock_update_feed.call_count = 0

        on_taskrun_submit(None, conn, target)
        obj = tmp.to_public_json()
        obj['action_updated'] = 'TaskCompleted'
        obj['published'] = None

        mock_update_feed.assert_called_once_with(obj)
        mock_add_user.assert_called_with(conn, target.user_id, obj)
        mock_update_task.assert_called_with(conn, target.task_id)
        mock_sched_after_save.assert_called_once_with(target, conn)
        obj_with_webhook = tmp.to_public_json()
        obj_with_webhook['webhook'] = tmp.webhook
        obj_with_webhook['action_updated'] = 'TaskCompleted'
        obj_with_webhook['published'] = None
        mock_push.assert_called_with(obj_with_webhook, target.task_id, 1)

    @with_context
    @patch('pybossa.model.event_listeners.update_feed')
    def test_add_user_event(self, mock_update_feed):
        """Test add_user_event is called."""
        conn = MagicMock()
        user = User(name="John", fullname="John")
        add_user_event(None, conn, user)
        assert mock_update_feed.called
        obj = user.to_public_json()
        obj['action_updated'] = 'User'
        mock_update_feed.assert_called_with(obj)

    @with_context
    @patch('pybossa.model.event_listeners.create_result')
    def test_create_result_event(self, mock_create_result):
        """Test create_result is called."""
        from pybossa.core import db
        task = TaskFactory.create(n_answers=1)
        TaskRunFactory.create(task=task)
        conn = db.engine.connect()
        result_id = create_result(conn, task.project_id, task.id)
        result = result_repo.filter_by(project_id=task.project_id,
                                       task_id=task.id,
                                       last_version=True)[0]

        assert mock_create_result.called
        err_msg = "The result should ID should be the same"
        assert result_id == result.id, err_msg

        task.n_answers = 2
        task_repo.update(task)
        TaskRunFactory.create(task=task)

        result_id = create_result(conn, task.project_id, task.id)
        assert mock_create_result.called
        result = result_repo.filter_by(project_id=task.project_id,
                                       task_id=task.id,
                                       last_version=True)
        assert len(result) == 1, len(result)
        result = result[0]
        err_msg = "The result should ID should be the same"
        assert result_id == result.id, err_msg
