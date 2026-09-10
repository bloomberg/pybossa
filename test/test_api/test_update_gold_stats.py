# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2021 Scifabric LTD.
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

from copy import deepcopy
import json

from pybossa.api.task_run import update_gold_stats
from test import Test, with_context
from test.factories import (ProjectFactory, TaskFactory, TaskRunFactory,
                            PerformanceStatsFactory)
from test.factories import performance_repo


class TestUpdateGoldStats(Test):

    @with_context
    def test_create_new_row(self):
        answer_fields = {
            'hello': {
                'type': 'categorical',
                'config': {
                    'labels': ['A', 'B']
                }
            }
        }
        project = ProjectFactory.create(
            info={
                'answer_fields': answer_fields,
                'data_classification': dict(input_data="L4 - public", output_data="L4 - public")
            })
        task = TaskFactory.create(project=project, calibration=1, gold_answers={'hello': 'A'})
        task_run = TaskRunFactory.create(task=task, info={'hello': 'A'})

        update_gold_stats(task_run.user_id, task.id, task_run.dictize())
        stats = performance_repo.filter_by(project_id=project.id)
        assert len(stats) == 1
        assert stats[0].info['matrix'] == [[1, 0], [0, 0]]

    @with_context
    def test_update_row(self):
        answer_fields = {
            'hello': {
                'type': 'categorical',
                'config': {
                    'labels': ['A', 'B']
                }
            }
        }
        project = ProjectFactory.create(
            info={
                'answer_fields': answer_fields,
                'data_classification': dict(input_data="L4 - public", output_data="L4 - public")
            })
        task = TaskFactory.create(project=project, calibration=1, gold_answers={'hello': 'A'})
        task_run = TaskRunFactory.create(task=task, info={'hello': 'B'})
        stat = PerformanceStatsFactory.create(user_id=task_run.user_id,
            project_id=project.id, field='hello',
            info={'matrix': [[1, 4], [2, 3]]})

        update_gold_stats(task_run.user_id, task.id, task_run.dictize())
        stats = performance_repo.filter_by(project_id=project.id)
        assert len(stats) == 1
        assert stats[0].info['matrix'] == [[1, 5], [2, 3]]

    @with_context
    def test_editing_gold_taskrun_does_not_change_original_score(self):
        answer_fields = {
            'hello': {
                'type': 'categorical',
                'config': {
                    'labels': ['A', 'B']
                }
            }
        }
        project = ProjectFactory.create(
            info={
                'allow_taskrun_edit': True,
                'answer_fields': answer_fields,
                'data_classification': {
                    'input_data': 'L4 - public',
                    'output_data': 'L4 - public'
                }
            })
        task = TaskFactory.create(
            project=project, calibration=1, gold_answers={'hello': 'A'})
        task_run = TaskRunFactory.create(
            task=task, user=project.owner, info={'hello': 'A'})

        update_gold_stats(task_run.user_id, task.id, task_run.dictize())
        original_score = deepcopy(
            performance_repo.filter_by(project_id=project.id)[0].info)

        response = self.app.put(
            '/api/taskrun/{}?api_key={}'.format(
                task_run.id, project.owner.api_key),
            data=json.dumps({
                'project_id': project.id,
                'task_id': task.id,
                'info': {'hello': 'B'}
            })
        )

        assert response.status_code == 200, response.data
        assert json.loads(response.data)['info']['hello'] == 'B'
        current_score = performance_repo.filter_by(
            project_id=project.id)[0].info
        assert current_score == original_score
