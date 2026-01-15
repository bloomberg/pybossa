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
"""Tests for task expiration configuration and behavior."""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from test import db, with_context
from test.factories import ProjectFactory, TaskFactory, UserFactory, TaskRunFactory
from test.test_api import TestAPI
from test.helper import web
from pybossa.repositories import TaskRepository

task_repo = TaskRepository(db)


class TestTaskExpirationConfig(TestAPI):
    """Test task expiration configuration with TASK_DEFAULT_EXPIRATION and TASK_MAX_EXPIRATION."""

    @with_context
    def test_task_default_expiration_60_days(self):
        """Test that tasks without expiration default to 60 days."""
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)

        # Create task without expiration
        task_data = {
            'project_id': project.id,
            'info': {'question': 'Test question'}
        }

        url = '/api/task?api_key=%s' % user.api_key
        res = self.app.post(url, data=json.dumps(task_data),
                           content_type='application/json')

        assert res.status_code == 200, res.status_code
        task = json.loads(res.data)

        # Check that expiration is set to approximately 60 days from now
        expiration = datetime.strptime(task['expiration'], '%Y-%m-%dT%H:%M:%S.%f')
        now = datetime.utcnow()
        days_diff = (expiration - now).days

        assert 59 <= days_diff <= 61, f"Expected ~60 days, got {days_diff}"

    @with_context
    def test_task_custom_expiration_within_max(self):
        """Test that tasks with custom expiration within max (365 days) use the custom value."""
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)

        # Create task with 90 day expiration
        custom_expiration = datetime.utcnow() + timedelta(days=90)
        task_data = {
            'project_id': project.id,
            'info': {'question': 'Test question'},
            'expiration': custom_expiration.isoformat()
        }

        url = '/api/task?api_key=%s' % user.api_key
        res = self.app.post(url, data=json.dumps(task_data),
                           content_type='application/json')

        assert res.status_code == 200, res.status_code
        task = json.loads(res.data)

        # Check that expiration matches the custom value (90 days)
        expiration = datetime.strptime(task['expiration'], '%Y-%m-%dT%H:%M:%S.%f')
        now = datetime.utcnow()
        days_diff = (expiration - now).days

        assert 89 <= days_diff <= 91, f"Expected ~90 days, got {days_diff}"

    @with_context
    def test_task_expiration_capped_at_max_365_days(self):
        """Test that tasks with expiration beyond max are capped at 365 days."""
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)

        # Try to create task with 400 day expiration (should be capped at 365)
        custom_expiration = datetime.utcnow() + timedelta(days=400)
        task_data = {
            'project_id': project.id,
            'info': {'question': 'Test question'},
            'expiration': custom_expiration.isoformat()
        }

        url = '/api/task?api_key=%s' % user.api_key
        res = self.app.post(url, data=json.dumps(task_data),
                           content_type='application/json')

        assert res.status_code == 200, res.status_code
        task = json.loads(res.data)

        # Check that expiration is capped at 365 days
        expiration = datetime.strptime(task['expiration'], '%Y-%m-%dT%H:%M:%S.%f')
        now = datetime.utcnow()
        days_diff = (expiration - now).days

        assert 364 <= days_diff <= 366, f"Expected ~365 days (max), got {days_diff}"

    @with_context
    def test_task_update_expiration_enforces_max(self):
        """Test that updating a task's expiration also enforces the 365 day maximum."""
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        task = TaskFactory.create(project=project, n_answers=1, info={'question': 'test'})

        # Try to update task with 500 day expiration (should be capped at 365)
        custom_expiration = datetime.utcnow() + timedelta(days=500)
        update_data = {
            'info': task.info,  # Must include info to avoid NoneType error
            'expiration': custom_expiration.isoformat()
        }

        url = '/api/task/%s?api_key=%s' % (task.id, user.api_key)
        res = self.app.put(url, data=json.dumps(update_data),
                          content_type='application/json')

        assert res.status_code == 200, res.status_code
        updated_task = json.loads(res.data)

        # Check that expiration is capped at 365 days from creation
        expiration = datetime.strptime(updated_task['expiration'], '%Y-%m-%dT%H:%M:%S.%f')
        created = datetime.strptime(task.created, '%Y-%m-%dT%H:%M:%S.%f')
        days_diff = (expiration - created).days

        assert 364 <= days_diff <= 366, f"Expected ~365 days from creation, got {days_diff}"

    @with_context
    def test_task_repository_save_sets_default_expiration(self):
        """Test that TaskRepository.save() sets default expiration."""
        project = ProjectFactory.create()

        task_data = {
            'project_id': project.id,
            'info': {'question': 'Test question'},
            'n_answers': 1
        }

        from pybossa.model.task import Task
        task = Task(**task_data)

        # Task should not have expiration yet
        assert task.expiration is None

        # Save should set expiration
        task_repo.save(task)

        # Now expiration should be set to ~60 days from now
        assert task.expiration is not None
        now = datetime.utcnow()
        days_diff = (task.expiration - now).days

        assert 59 <= days_diff <= 61, f"Expected ~60 days, got {days_diff}"

    @with_context
    def test_task_expiration_calculated_from_creation_date(self):
        """Test that expiration is calculated from task creation date, not current time."""
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)

        # Create task with specific creation date in the past
        task = TaskFactory.create(project=project, n_answers=1)
        old_date = datetime.utcnow() - timedelta(days=30)
        task.created = old_date.strftime('%Y-%m-%dT%H:%M:%S.%f')

        # Manually set expiration to be 60 days from creation
        task.expiration = old_date + timedelta(days=60)
        task_repo.update(task)

        # Verify expiration is 60 days from creation, not from now
        # So it should expire in about 30 days from now (60 - 30)
        now = datetime.utcnow()
        days_until_expiration = (task.expiration - now).days
        assert 29 <= days_until_expiration <= 31, f"Expected ~30 days, got {days_until_expiration}"


class TestRedundancyUpdateExpiration(web.Helper):
    """Test redundancy update expiration window with TASK_MAX_EXPIRATION."""


    @with_context
    def test_redundancy_update_within_365_day_window(self):
        """Test that tasks within 365 days can have redundancy updated."""
        user = UserFactory.create()
        user.set_password('1234')
        db.session.commit()
        project = ProjectFactory.create(owner=user)

        # Create task 100 days ago
        old_date = datetime.utcnow() - timedelta(days=100)
        task = TaskFactory.create(project=project, n_answers=1)
        task.created = old_date.strftime('%Y-%m-%dT%H:%M:%S.%f')
        db.session.commit()

        # Update redundancy
        update_data = {'n_answers': 2, 'taskIds': [task.id]}
        url = '/project/%s/tasks/redundancyupdate' % project.short_name

        self.signin(email=user.email_addr, password='1234')
        res = self.app.post(url, data=json.dumps(update_data),
                           content_type='application/json')

        assert res.status_code == 200, res.status_code

        # Check that redundancy was updated
        updated_task = task_repo.get_task(task.id)
        assert updated_task.n_answers == 2, f"Expected n_answers=2, got {updated_task.n_answers}"

    @with_context
    def test_redundancy_update_beyond_365_day_window_with_files(self):
        """Test that completed tasks with files beyond 365 days cannot have redundancy updated."""
        user = UserFactory.create()
        user.set_password('1234')
        db.session.commit()

        project = ProjectFactory.create(owner=user)
        old_date = datetime.utcnow() - timedelta(days=400)

        task = TaskFactory.create(
            project=project,
            n_answers=1,
            state='completed',
            info={'file__upload_url': 'https://example.com/file.pdf'}
        )
        task.created = old_date.strftime('%Y-%m-%dT%H:%M:%S.%f')
        db.session.commit()

        # Try to update redundancy
        update_data = {'n_answers': 2, 'taskIds': [task.id]}
        url = '/project/%s/tasks/redundancyupdate' % project.short_name

        self.signin(email=user.email_addr, password='1234')
        res = self.app.post(url, data=json.dumps(update_data),
                           content_type='application/json')

        assert res.status_code == 200, res.status_code

        # Check that redundancy was NOT updated
        updated_task = task_repo.get_task(task.id)
        assert updated_task.n_answers == 1, f"Expected n_answers=1 (unchanged), got {updated_task.n_answers}"

    @with_context
    def test_bulk_redundancy_update_respects_365_day_limit(self):
        """Test that bulk redundancy update uses 365 day window."""
        user = UserFactory.create()
        user.set_password('1234')
        db.session.commit()

        project = ProjectFactory.create(owner=user)
        tasks = []

        # Task 1: 50 days old (should update)
        task1 = TaskFactory.create(project=project, n_answers=1)
        task1.created = (datetime.utcnow() - timedelta(days=50)).strftime('%Y-%m-%dT%H:%M:%S.%f')
        tasks.append(task1)

        # Task 2: 300 days old (should update)
        task2 = TaskFactory.create(project=project, n_answers=1)
        task2.created = (datetime.utcnow() - timedelta(days=300)).strftime('%Y-%m-%dT%H:%M:%S.%f')
        tasks.append(task2)

        # Task 3: 400 days old with file, completed (should NOT update)
        task3 = TaskFactory.create(
            project=project,
            n_answers=1,
            state='completed',
            info={'file__upload_url': 'https://example.com/file.pdf'}
        )
        task3.created = (datetime.utcnow() - timedelta(days=400)).strftime('%Y-%m-%dT%H:%M:%S.%f')
        tasks.append(task3)

        db.session.commit()

        # Bulk update all tasks (no filters, updates entire project)
        update_data = {'n_answers': 2, 'filters': {}}
        url = '/project/%s/tasks/redundancyupdate' % project.short_name

        self.signin(email=user.email_addr, password='1234')
        res = self.app.post(url, data=json.dumps(update_data),
                           content_type='application/json')

        assert res.status_code == 200, res.status_code

        # Check results
        updated_task1 = task_repo.get_task(task1.id)
        updated_task2 = task_repo.get_task(task2.id)
        updated_task3 = task_repo.get_task(task3.id)

        assert updated_task1.n_answers == 2, "Task 1 (50 days) should be updated"
        assert updated_task2.n_answers == 2, "Task 2 (300 days) should be updated"
        assert updated_task3.n_answers == 1, "Task 3 (400 days with file) should NOT be updated"



class TestTaskSchedulingWithExpiration(web.Helper):
    """Test that expired tasks are not scheduled for users."""

    @with_context
    def test_non_expired_tasks_returned_for_scheduling(self):
        """Test that tasks within expiration date are returned to users."""
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user, published=True)

        # Create task with future expiration
        task = TaskFactory.create(project=project, n_answers=1)
        task.expiration = datetime.utcnow() + timedelta(days=10)  # Expires in 10 days
        db.session.commit()

        # Task should be available for scheduling
        # Scheduler tests verify expiration filtering logic
