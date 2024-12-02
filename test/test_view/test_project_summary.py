# -*- coding: utf8 -*-
import json
from unittest.mock import patch

from test import db, with_context
from test.factories import ProjectFactory
from test.factories.user_factory import UserFactory
from test.helper import web
from pybossa.repositories import ProjectRepository, UserRepository

project_repo = ProjectRepository(db)
user_repo = UserRepository(db)


class TestSummary(web.Helper):
    external_config_patch = {
        "EXTERNAL_CONFIGURATIONS_VUE": {
            "authorized_services": {
                "display": "Authorized Services",
                "fields": [
                    {
                        "type": "MultiSelect",
                        "choices": ["test-service-1", "test-service-2"],
                        "name": "service_key",
                    }
                ],
            }
        }
    }

    @with_context
    def test_get_config(self):
        project = ProjectFactory.create(published=True)
        url = '/project/%s/summary?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app.get(url)
        assert 'setting' in str(res.data), res.data
        assert 'ownership-setting' in str(res.data), res.data
        assert 'task-setting' in str(res.data), res.data
        assert 'fields-config' in str(res.data), res.data
        assert 'redundancy-config' in str(res.data), res.data
        assert 'consensus-setting' in str(res.data), res.data
        assert 'quiz-setting' in str(res.data), res.data

    @with_context
    def test_post_project_config_authorized_servcies_as_admin(self):
        with patch.dict(self.flask_app.config, self.external_config_patch):
            admin = UserFactory.create(admin=True)
            user = UserFactory.create(admin=False)
            project = ProjectFactory.create(owner=user)
            headers = [("Authorization", admin.api_key)]
            url = "/project/%s/project-config" % (project.short_name)
            payload = {"config": {"service_key": ["test-service"]}}
            self.app.post(
                url,
                method="POST",
                headers=headers,
                content_type="application/json",
                data=json.dumps(payload),
            )
            updated_project = project_repo.get(project.id)

            # Only admins user can update 'authorized_services'
            assert updated_project.info["ext_config"] == {
                "authorized_services": {"service_key": ["test-service"]}
            }

    @with_context
    def test_post_project_config_authorized_servcies_as_non_admin(self):
        with patch.dict(self.flask_app.config, self.external_config_patch):
            admin = UserFactory.create(admin=True)
            user = UserFactory.create(admin=False)
            project = ProjectFactory.create(owner=user)
            headers = [("Authorization", user.api_key)]
            url = "/project/%s/project-config" % (project.short_name)
            payload = {"config": {"service_key": ["test-service"]}}
            self.app.post(
                url,
                method="POST",
                headers=headers,
                content_type="application/json",
                data=json.dumps(payload),
            )
            updated_project = project_repo.get(project.id)

            # Regular user cannot update 'authorized_services'
            assert updated_project.info.get("ext_config") == None

    @with_context
    def test_post_project_config_setting(self):
        ext_config = {
            'ml_service': {
                'display': 'Active Learning Config',
                'fields': [{
                    'name': 'model',
                    'type': 'TextField'
                }]
            }
        }
        patch.dict(self.flask_app.config, {'EXTERNAL_CONFIGURATIONS_VUE': ext_config})
        project = ProjectFactory.create(published=True)
        url = '/project/%s/project-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = ""
        fields = {
            'config': {'model': 'test_model'},
            'data_access': ['L1', 'L2'],
            'select_users': ['1', '2']
        }
        res = self.app.post(url, method='POST', content_type='application/json',
                            data=json.dumps(fields),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'Configuration updated successfully'

    @with_context
    def test_post_ownership_setting(self):
        project = ProjectFactory.create(published=True)
        url = '/project/%s/coowners?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = ""
        fields = {'coowners': ['1111']}
        res = self.app.post(url, method='POST', content_type='application/json',
                            data=json.dumps(fields),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'Configuration updated successfully'

    @with_context
    def test_invalid_post(self):
        project = ProjectFactory.create(published=True)
        url = '/project/%s/project-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = ""
        res = self.app.post(url, content_type='application/json',
                            data={},
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'An error occurred.'
