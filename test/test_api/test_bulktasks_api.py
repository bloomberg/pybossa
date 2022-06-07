# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2022 Scifabric LTD.
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
import json
import datetime
from test import db, with_context, with_request_context
from nose.tools import assert_equal, assert_raises
from werkzeug.exceptions import MethodNotAllowed, Unauthorized


from test.test_api import TestAPI
from pybossa.core import project_repo, task_repo

from test.factories import ProjectFactory, TaskFactory, TaskRunFactory, UserFactory

from unittest.mock import patch
from pybossa.repositories import TaskRepository
from pybossa.api.bulktasks import BulkTasksAPI
from test.helper.gig_helper import make_subadmin


class TestBulkTasksApi(TestAPI):

    def setUp(self):
        super(TestBulkTasksApi, self).setUp()

    data_classification=dict(input_data="L4 - public", output_data="L4 - public")

    @with_context
    @patch('pybossa.api.task.TaskAPI._verify_auth')
    def test_api_unauthorized_access_disallowed_methods(self, auth):
        """Test bulktasks API unauthorized access and disallowed method works"""

        # test disallowed methods
        bulktasks = BulkTasksAPI()
        assert_raises(MethodNotAllowed, bulktasks.get)
        assert_raises(MethodNotAllowed, bulktasks.post)
        assert_raises(MethodNotAllowed, bulktasks.delete)

        # test unauthorized access
        admin, owner, user = UserFactory.create_batch(3)
        projects = ProjectFactory.create_batch(2, owner=owner)
        auth.return_value = True

        tasks = TaskFactory.create_batch(2, project=projects[0])
        for task in tasks:
            TaskRunFactory.create(task=task)

        tasks2 = TaskFactory.create_batch(2, project=projects[1])
        for task in tasks2:
            TaskRunFactory.create(task=task)

        res = self.app.put(f"/api/bulktasks/{projects[0].id}")
        assert_equal(res.status, "401 UNAUTHORIZED", "Anonymous user should not be allowed")

        # incorrect project id
        make_subadmin(user)
        res = self.app.put(f"/api/bulktasks/999?api_key={user.api_key}")
        assert_equal(res.status, "400 BAD REQUEST", "Update should fail due to incorrect project id")

        # missing payload to be updated
        res = self.app.put(f"/api/bulktasks/{projects[0].id}?api_key={user.api_key}")
        assert_equal(res.status, "400 BAD REQUEST", "Update should fail due to missing payload for update")

        # subadmin not coowner on project
        payload =[{"id": task.id, "priority_0": 0.6}]
        res = self.app.put(f"/api/bulktasks/{projects[0].id}?api_key={user.api_key}", json=payload)
        assert_equal(res.status, "401 UNAUTHORIZED", "User not admin/subadmin owner should should not be allowed to update task")

        # subadmin coowner on project updating task from another project
        payload =[{"id": tasks2[0].id, "priority_0": 0.6}]
        make_subadmin(owner)
        res = self.app.put(f"/api/bulktasks/{projects[0].id}?api_key={owner.api_key}", json=payload)
        assert res.status_code == 200, "Updating task for different project returns 200"

        # subadmin coowner on project; task from another project/unsupported attributes dropped from updating
        make_subadmin(owner)
        payload =[{"id": tasks[0].id, "xyz": 0.6}]
        res = self.app.put(f"/api/bulktasks/{projects[0].id}?api_key={owner.api_key}", json=payload)
        payload = [
            {"id": tasks[0].id, "priority_0": 0.2},
            {"id": tasks2[0].id, "priority_0": 0.6},
            {"id": tasks[1].id, "priority_0": 0.6}
        ]
        res = self.app.put(f"/api/bulktasks/{projects[0].id}?api_key={owner.api_key}", json=payload)
        assert res.status_code == 200, "Updating task for different project returns 200"


    @with_context
    @patch('pybossa.api.task.TaskAPI._verify_auth')
    def test_api_bulk_update_priority_works(self, auth):
        """Test bulktasks API updates task priorities in bulk"""

        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        auth.return_value = True

        tasks = TaskFactory.create_batch(5, project=project, priority_0=1)
        for task in tasks:
            TaskRunFactory.create(task=task)

        # subadmin coowner on project; task from another project dropped from updating
        payload = [
            {"id": tasks[0].id, "priority_0": 0.2},
            {"id": tasks[1].id, "priority_0": 0.6},
            {"id": tasks[3].id, "priority_0": 0.7}
        ]
        make_subadmin(owner)
        res = self.app.put(f"/api/bulktasks/{project.id}?api_key={owner.api_key}", json=payload)
        assert res.status_code == 200, "Updating task for different project returns 200"
        # tasks 1, 2 & 4 should have updated priority of 0.2, 0.6 & 0.7 respectively
        # tasks 3 & 5 to have original priority value 1
        assert tasks[0].priority_0 == 0.2 and tasks[1].priority_0 == 0.6 and tasks[3].priority_0 == 0.7, "Tasks should have updated priority"
        assert tasks[2].priority_0 == 1.0 and tasks[4].priority_0 == 1.0, "Tasks should have original priority"


    @with_context
    @patch('pybossa.api.task.TaskAPI._verify_auth')
    @patch('pybossa.api.bulktasks.task_repo.bulk_update')
    def test_api_bulk_update_handle_exception(self, bulk_update, auth):
        """Test bulktasks API handles db exception"""

        bulk_update.side_effect = Exception('Bad Request')
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        auth.return_value = True

        task = TaskFactory.create(project=project)
        make_subadmin(owner)
        payload = [{"id": task.id, "priority_0": 0.2}]
        res = self.app.put(f"/api/bulktasks/{project.id}?api_key={owner.api_key}", json=payload)
        assert res.status_code == 500, "PUT request to return 500"
