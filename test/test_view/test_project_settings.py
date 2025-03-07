# -*- coding: utf8 -*-
import json
from unittest.mock import patch

from test import db, with_context
from test.factories import ProjectFactory
from test.helper import web
from pybossa import data_access
from pybossa.repositories import ProjectRepository


class TestProjectSettings(web.Helper):

    def setUp(self):
        super(TestProjectSettings, self).setUp()
        self.project_repo = ProjectRepository(db)

    @staticmethod
    def patched_levels(**kwargs):
        patch_data_access_levels = dict(
            valid_access_levels=["L1", "L2", "L3", "L4"],
            valid_user_levels_for_project_level=dict(
                L1=[], L2=["L1"], L3=["L1", "L2"], L4=["L1", "L2", "L3"]),
            valid_project_levels_for_user_level=dict(
                L1=["L2", "L3", "L4"], L2=["L3", "L4"], L3=["L4"], L4=[]),
            valid_user_access_levels=[("L1", "L1"), ("L2", "L2"),("L3", "L3"), ("L4", "L4")]
        )
        patch_data_access_levels.update(kwargs)
        return patch_data_access_levels

    @with_context
    def test_project_update_amp_store(self):
        with patch.dict(data_access.data_access_levels, self.patched_levels()):
            project = ProjectFactory.create(
                published=True,
                info={
                    'annotation_config': {'amp_store': True},
                    'data_classification': {
                        'input_data': 'L3 - community',
                        'output_data': 'L4 - public'
                    }
                })
            url = '/project/%s/update?api_key=%s' % (project.short_name, project.owner.api_key)
            res = self.app_get_json(url)
            data = json.loads(res.data)
            assert data['form']['amp_store'], 'opt-in amp store should be checked'

    @with_context
    def test_project_get_request_update_duplicate_tasks_setting(self):
        project = ProjectFactory.create(
            published=True,
            info={
                'duplicate_task_check': {
                    'duplicate_fields': ["company_name", "company_website"],
                    'completed_tasks': True
                }
            })
        url = f'/project/{project.short_name}/update?api_key={project.owner.api_key}'
        res = self.app_get_json(url)
        data = json.loads(res.data)
        assert data['form']['duplicate_task_check_completed_tasks'] == True, data['form']
        assert data['form']['duplicate_task_check_duplicate_fields'] == ['company_name', 'company_website'], data['form']
