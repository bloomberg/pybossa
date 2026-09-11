import json
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from test import with_context
from test.factories import (ProjectFactory, TaskFactory, TaskRunFactory,
                            UserFactory)
from test.helper.web import Helper


PYBOSSA_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PYBOSSA_ROOT / 'pybossa/themes/default/templates/projects'


class TestGoldTaskBrowseDisclosure(Helper):

    @with_context
    @patch('pybossa.view.projects._check_if_redirect_to_password')
    def test_worker_cannot_filter_or_receive_gold_task_metadata(self,
                                                                check_password):
        check_password.return_value = None
        owner = UserFactory.create()
        worker = UserFactory.create()
        project = ProjectFactory.create(
            owner=owner,
            published=True,
            info={
                'sched': 'task_queue_scheduler',
                'project_users': [worker.id]
            }
        )
        gold_task = TaskFactory.create(project=project, calibration=1)
        ordinary_task = TaskFactory.create(project=project, calibration=0)

        response = self.app.get(
            '/project/{}/tasks/browse?view=tasklist&response_format=json'
            '&gold_task=1&api_key={}'.format(project.short_name,
                                             worker.api_key)
        )

        assert response.status_code == 200, response.data
        payload = json.loads(response.data)
        tasks = payload['tasks']
        assert {task['id'] for task in tasks} == {
            gold_task.id, ordinary_task.id
        }
        assert all('calibration' not in task for task in tasks), tasks
        assert 'gold_task' not in payload['filter_data'], payload['filter_data']

    @with_context
    @patch('pybossa.view.projects._check_if_redirect_to_password')
    def test_admin_can_still_filter_and_receive_gold_task_metadata(self,
                                                                   check_password):
        check_password.return_value = None
        admin = UserFactory.create(admin=True)
        owner = UserFactory.create()
        project = ProjectFactory.create(
            owner=owner,
            published=True,
            info={'sched': 'task_queue_scheduler'}
        )
        gold_task = TaskFactory.create(project=project, calibration=1)
        TaskFactory.create(project=project, calibration=0)

        response = self.app.get(
            '/project/{}/tasks/browse?view=tasklist&response_format=json'
            '&gold_task=1&api_key={}'.format(project.short_name,
                                             admin.api_key)
        )

        assert response.status_code == 200, response.data
        payload = json.loads(response.data)
        assert [task['id'] for task in payload['tasks']] == [gold_task.id]
        assert payload['tasks'][0]['calibration'] == 1
        assert payload['filter_data']['gold_task'] == '1'

    @with_context
    @patch('pybossa.view.projects._check_if_redirect_to_password')
    def test_worker_edit_links_do_not_reveal_gold_task_status(self,
                                                              check_password):
        check_password.return_value = None

        owner = UserFactory.create()
        worker = UserFactory.create()
        project = ProjectFactory.create(
            owner=owner,
            published=True,
            info={
                'project_users': [worker.id],
                'allow_taskrun_edit': True
            }
        )
        gold_task = TaskFactory.create(project=project, calibration=1)
        ordinary_task = TaskFactory.create(project=project, calibration=0)
        TaskRunFactory.create(task=gold_task, user=worker)
        TaskRunFactory.create(task=ordinary_task, user=worker)

        response = self.app.get(
            '/project/{}/tasks/browse?view=edit_submission&api_key={}'
            .format(project.short_name, worker.api_key)
        )

        assert response.status_code == 200, response.data
        dom = BeautifulSoup(response.data, 'html.parser')
        editable_task_labels = {
            link.get_text(strip=True)
            for link in dom.find_all('a', href=True)
            if 'mode=edit_submission' in link['href']
        }
        assert editable_task_labels == {
            '#{}'.format(gold_task.id),
            '#{}'.format(ordinary_task.id)
        }, editable_task_labels


class TestGoldTaskBrowseThemeGuards(unittest.TestCase):

    templates = ('tasks_browse.html', 'tasks_browse.webpack.ejs')

    def test_sensitive_columns_have_role_guards_at_every_table_sink(self):
        expected_guards = {
            'gold_task': 'can_know_task_is_gold',
            'lock_status': 'admin_subadmin_coowner',
            'completed_by': 'admin_subadmin_coowner',
            'assigned_users': 'admin_subadmin_coowner',
        }

        for template in self.templates:
            source = (TEMPLATE_ROOT / template).read_text(encoding='utf-8')
            for column, guard in expected_guards.items():
                expression = (
                    "{{% if {} and '{}' in filter_data.display_columns %}}"
                    .format(guard, column)
                )
                self.assertEqual(source.count(expression), 3,
                                 '{}: {}'.format(template, column))


if __name__ == '__main__':
    unittest.main()
