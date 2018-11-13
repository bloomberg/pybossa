# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2018 Scifabric LTD.
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
from StringIO import StringIO
from default import db, with_context
from nose.tools import assert_equal, assert_raises
from test_api import TestAPI
from mock import patch
from factories import ProjectFactory, TaskFactory, TaskRunFactory, UserFactory
from pybossa.model.task_run import TaskRun
from helper.gig_helper import make_subadmin, make_admin
from pybossa.repositories import TaskRepository
from werkzeug.exceptions import MethodNotAllowed
from pybossa.api.gold_task_run import GoldTaskRunAPI


task_repo = TaskRepository(db)

class TestGoldTaskAPI(TestAPI):

    @with_context
    def test_create_update_gold_answers(self):
        [admin, subadminowner, subadmin, reguser] = UserFactory.create_batch(4)
        make_admin(admin)
        make_subadmin(subadminowner)
        make_subadmin(subadmin)

        project = ProjectFactory.create(owner=subadminowner)
        admin_headers = dict(Authorization=admin.api_key)
        task_info = dict(field_1='one', field_2='two')
        gold_answers = dict(field_3='some ans', field_4='some ans 2')

        # POST gold_answers successful
        data = dict(project_id=project.id, info=task_info, gold_answers=gold_answers,
            n_answers=2)
        res = self.app.post('/api/task', data=json.dumps(data), headers=admin_headers)
        assert res.data, res
        jdata = json.loads(res.data)
        assert_equal(jdata['info'], task_info), jdata
        assert_equal(jdata['gold_answers'], gold_answers), jdata
        assert jdata['calibration'] == 1, 'calibration should have been set with updating gold_answers'

        # GET task by subadmin not owner user does not get gold answers,
        # whereas admin/subadmin gets gold answers
        subadminowner_headers = dict(Authorization=subadminowner.api_key)
        subadmin_headers = dict(Authorization=subadmin.api_key)
        reguser_headers = dict(Authorization=reguser.api_key)
        res = self.app.get('/api/task/1', headers=admin_headers)
        jdata = json.loads(res.data)
        assert_equal(jdata['gold_answers'], gold_answers), jdata
        res = self.app.get('/api/task/1', headers=subadminowner_headers)
        jdata = json.loads(res.data)
        assert_equal(jdata['gold_answers'], gold_answers), jdata
        res = self.app.get('/api/task/1', headers=subadmin_headers)
        jdata = json.loads(res.data)
        assert 'gold_answers' not in jdata, jdata
        assert 'calibration' not in jdata, jdata
        # regular users should not receive gold_answers and calibration info
        res = self.app.get('/api/task/1', headers=reguser_headers)
        jdata = json.loads(res.data)
        assert 'gold_answers' not in jdata, jdata
        assert 'calibration' not in jdata, jdata

        # PUT request updates gold answers
        updated_gold_answers = dict(field_3='some ans - updated', field_5='one more ans')
        data = dict(project_id=project.id, gold_answers=updated_gold_answers)
        res = self.app.put('/api/task/1', data=json.dumps(data), headers=subadminowner_headers)
        jdata = json.loads(res.data)
        gold_answers.update(updated_gold_answers)
        assert_equal(jdata['gold_answers'], updated_gold_answers), jdata

        # Beyond redundancy, submitting task runs to task with gold_answers
        # is permitted. such task run submissions should not mark task as complete
        task = task_repo.get_task(jdata['id'])
        n_taskruns = 8
        taskruns = TaskRunFactory.create_batch(n_taskruns, project=project, task=task)
        assert task.state == 'ongoing', 'Gold task state should be ongoing beyond task submissions > task redundancy'
        assert len(taskruns) == n_taskruns, 'For gold task, number of task runs submissions can be beyond task redundancy'
        assert task.exported == False, 'Gold tasks to be marked exported as False upon task run submission'

        task.exported = True
        taskruns = TaskRunFactory.create_batch(1, project=project, task=task)
        assert task.exported == False, 'Gold tasks to be marked exported as False upon task run submission'

        # reset gold answer
        data = dict(project_id=project.id, gold_answers={})
        res = self.app.put('/api/task/1', data=json.dumps(data), headers=subadminowner_headers)
        jdata = json.loads(res.data)
        assert_equal(jdata['gold_answers'], {}), jdata
        assert jdata['calibration'] == 0, 'Calibration should be reset upon gold_answers reset'

    @with_context
    @patch('pybossa.api.task.task_repo.find_duplicate')
    @patch('pybossa.api.task.validate_required_fields')
    def test_task_post_api_exceptions(self, inv_field, dup):
        """Get a list of tasks using a list of project_ids."""
        [admin, subadminowner] = UserFactory.create_batch(2)
        make_admin(admin)
        make_subadmin(subadminowner)

        project = ProjectFactory.create(owner=subadminowner)
        admin_headers = dict(Authorization=admin.api_key)
        task_info = dict(field_1='one', field_2='two')
        gold_answers = dict(field_3='some ans')
        data = dict(project_id=project.id, info=task_info, gold_answers=gold_answers,
            n_answers=2)

        dup.return_value = True
        res = self.app.post('/api/task', data=json.dumps(data), headers=admin_headers)
        res_data = json.loads(res.data)
        assert json.loads(res_data['exception_msg'])['reason'] == 'DUPLICATE_TASK', res

        dup.return_value = False
        inv_field = True
        res = self.app.post('/api/task', data=json.dumps(data), headers=admin_headers)
        res_data = json.loads(res.data)
        assert res_data['exception_msg'] == 'Missing or incorrect required fields: ', res

    @with_context
    @patch('pybossa.api.task.TaskAPI._verify_auth')
    def test_gold_taskrun_api(self, auth):
        auth.return_value = True
        admin, owner, user = UserFactory.create_batch(3)
        make_admin(admin)
        make_subadmin(owner)
        admin_headers = dict(Authorization=admin.api_key)
        owner_headers = dict(Authorization=owner.api_key)
        user_headers = dict(Authorization=user.api_key)

        project = ProjectFactory.create(owner=owner)
        tasks = TaskFactory.create_batch(10, project=project,
                                         info=dict(foo='fox'))

        gold_answers = dict(field_3='some ans')
        gold_tasks = TaskFactory.create_batch(10, project=project,
            info=dict(foo='dog'), gold_answers=gold_answers,
            calibration=1, exported=False)
        TaskRunFactory.create(task=tasks[0], user=user)
        TaskRunFactory.create(task=tasks[1], user=user)
        TaskRunFactory.create(task=tasks[2], user=user)

        gold_taskruns = []
        gold_taskruns.append(TaskRunFactory.create(task=gold_tasks[0], user=user).id)
        gold_taskruns.append(TaskRunFactory.create(task=gold_tasks[0], user=admin).id)
        gold_taskruns.append(TaskRunFactory.create(task=gold_tasks[0], user=owner).id)
        gold_taskruns.append(TaskRunFactory.create(task=gold_tasks[1], user=owner).id)
        gold_taskruns.append(TaskRunFactory.create(task=gold_tasks[1], user=user).id)
        gold_taskruns.append(TaskRunFactory.create(task=gold_tasks[2], user=user).id)

        res = self.app.get('/api/goldtaskrun', headers=admin_headers)
        taskruns = json.loads(res.data)
        assert all(tr['id'] in  gold_taskruns for tr in taskruns)

        # owner of a project requesting gold taskrun without project id fails
        res = self.app.get('/api/goldtaskrun', headers=owner_headers)
        err = json.loads(res.data)
        assert res.status_code == 401, res.status_code
        assert err['exception_cls'] == 'Unauthorized', err

        # owner requesting gold answers for project owned
        url = '/api/goldtaskrun?project_id={}'.format(project.id)
        res = self.app.get(url, headers=owner_headers)
        taskruns = json.loads(res.data)
        assert all(tr['id'] in  gold_taskruns for tr in taskruns)

        res = self.app.get('/api/goldtaskrun', headers=user_headers)
        err = json.loads(res.data)
        assert res.status_code == 401, res.status_code
        assert err['exception_cls'] == 'Unauthorized', err

    @with_context
    def test_not_allowed_methods(self):
        goldtaskrun = GoldTaskRunAPI()
        # only get allowed on goldtaskrun api
        res = self.app.post('/api/goldtaskrun')
        assert res.status_code == 405, res.status_code
        assert_raises(MethodNotAllowed, goldtaskrun.post)
        res = self.app.delete('/api/goldtaskrun')
        assert res.status_code == 405, res.status_code
        assert_raises(MethodNotAllowed, goldtaskrun.delete)
        res = self.app.put('/api/goldtaskrun')
        assert res.status_code == 405, res.status_code
        assert_raises(MethodNotAllowed, goldtaskrun.put)
