# -*- coding: utf8 -*-
import json
from unittest.mock import patch

from test import db, with_context
from test.factories import ProjectFactory
from test.helper import web
from pybossa.repositories import ProjectRepository, UserRepository

project_repo = ProjectRepository(db)
user_repo = UserRepository(db)


class TestSchemaConfig(web.Helper):

    @with_context
    def test_get_config(self):
        """Test GET request returns schema config page"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app.get(url)
        assert 'schema-setting' in str(res.data), res.data

    @with_context
    def test_get_config_with_existing_schemas(self):
        """Test GET request returns existing schema config values"""
        info = {
            'task_info_schema': {
                'type': 'object',
                'properties': {
                    'question': {'type': 'string'}
                }
            },
            'task_answer_schema': {
                'type': 'object',
                'properties': {
                    'answer': {'type': 'string'}
                }
            },
            'strict_validation': True
        }
        project = ProjectFactory.create(published=True, info=info)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)

        # Parse the JSON strings back to objects
        task_info_schema = json.loads(data['task_info_schema'])
        task_answer_schema = json.loads(data['task_answer_schema'])

        assert task_info_schema == info['task_info_schema']
        assert task_answer_schema == info['task_answer_schema']
        assert data['strict_validation'] == info['strict_validation']

    @with_context
    def test_post_task_info_schema_config(self):
        """Test POST request with task_info_schema updates project"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        schema_config = {
            'task_info_schema': {
                'type': 'object',
                'properties': {
                    'question': {'type': 'string'},
                    'options': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    }
                },
                'required': ['question']
            }
        }

        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(schema_config),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'Configuration updated successfully'

        # Verify the project was updated
        updated_project = project_repo.get(project.id)
        assert updated_project.info['task_info_schema'] == schema_config['task_info_schema']

    @with_context
    def test_post_task_answer_schema_config(self):
        """Test POST request with task_answer_schema updates project"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        schema_config = {
            'task_answer_schema': {
                'type': 'object',
                'properties': {
                    'answer': {'type': 'string'},
                    'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}
                },
                'required': ['answer']
            }
        }

        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(schema_config),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'Configuration updated successfully'

        # Verify the project was updated
        updated_project = project_repo.get(project.id)
        assert updated_project.info['task_answer_schema'] == schema_config['task_answer_schema']

    @with_context
    def test_post_strict_validation_config(self):
        """Test POST request with strict_validation updates project"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        schema_config = {
            'strict_validation': True
        }

        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(schema_config),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'Configuration updated successfully'

        # Verify the project was updated
        updated_project = project_repo.get(project.id)
        assert updated_project.info['strict_validation'] == True

    @with_context
    def test_post_all_schema_configs(self):
        """Test POST request with all schema configs updates project"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        schema_config = {
            'task_info_schema': {
                'type': 'object',
                'properties': {
                    'question': {'type': 'string'},
                    'image_url': {'type': 'string', 'format': 'uri'}
                }
            },
            'task_answer_schema': {
                'type': 'object',
                'properties': {
                    'answer': {'type': 'string'},
                    'timestamp': {'type': 'string', 'format': 'date-time'}
                }
            },
            'strict_validation': False
        }

        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(schema_config),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'Configuration updated successfully'

        # Verify the project was updated
        updated_project = project_repo.get(project.id)
        assert updated_project.info['task_info_schema'] == schema_config['task_info_schema']
        assert updated_project.info['task_answer_schema'] == schema_config['task_answer_schema']
        assert updated_project.info['strict_validation'] == schema_config['strict_validation']

    @with_context
    def test_post_empty_schemas(self):
        """Test POST request with empty schemas sets empty dicts"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        schema_config = {
            'task_info_schema': {},
            'task_answer_schema': {},
            'strict_validation': False
        }

        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(schema_config),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'Configuration updated successfully'

        # Verify the project was updated
        updated_project = project_repo.get(project.id)
        assert updated_project.info['task_info_schema'] == {}
        assert updated_project.info['task_answer_schema'] == {}
        assert updated_project.info['strict_validation'] == False

    @with_context
    def test_post_invalid_json(self):
        """Test POST request with invalid JSON returns error"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        res = self.app.post(url, content_type='application/json',
                            data='invalid json',
                            headers={'X-CSRFToken': csrf})
        assert res.status_code == 400

    @with_context
    def test_post_empty_data(self):
        """Test POST request with empty data returns error"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        res = self.app.post(url, content_type='application/json',
                            data='',
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'An error occurred.'
        assert data['status'] == 'error'

    @with_context
    @patch('pybossa.view.projects.auditlogger.log_event')
    def test_post_creates_audit_logs(self, mock_log_event):
        """Test POST request creates appropriate audit log entries"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        schema_config = {
            'task_info_schema': {'type': 'object'},
            'task_answer_schema': {'type': 'object'},
            'strict_validation': True
        }

        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(schema_config),
                            headers={'X-CSRFToken': csrf})

        # Should have 3 audit log calls - one for each schema field
        assert mock_log_event.call_count == 3

        # Check the audit log calls
        calls = mock_log_event.call_args_list
        log_keys = [call[0][3] for call in calls]

        assert 'project.task_info_schema' in log_keys
        assert 'project.task_answer_schema' in log_keys
        assert 'project.strict_validation' in log_keys

    @with_context
    def test_update_existing_schemas(self):
        """Test updating existing schemas replaces old values"""
        old_info = {
            'task_info_schema': {'type': 'string'},
            'task_answer_schema': {'type': 'number'},
            'strict_validation': False
        }
        project = ProjectFactory.create(published=True, info=old_info)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        new_schema_config = {
            'task_info_schema': {
                'type': 'object',
                'properties': {'new_field': {'type': 'string'}}
            },
            'task_answer_schema': {
                'type': 'array',
                'items': {'type': 'string'}
            },
            'strict_validation': True
        }

        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(new_schema_config),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'Configuration updated successfully'

        # Verify the project was updated with new values
        updated_project = project_repo.get(project.id)
        assert updated_project.info['task_info_schema'] == new_schema_config['task_info_schema']
        assert updated_project.info['task_answer_schema'] == new_schema_config['task_answer_schema']
        assert updated_project.info['strict_validation'] == new_schema_config['strict_validation']

    @with_context
    def test_get_config_returns_correct_template(self):
        """Test GET request uses correct template"""
        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        assert data['template'] == '/projects/schemaconfig.html'

    @with_context
    def test_authorization_required(self):
        """Test that proper authorization is required to access schema config"""
        project = ProjectFactory.create(published=True)
        # Create another user who is not the owner
        other_user = UserRepository(db).get_by(id=2)
        if other_user is None:
            from test.factories import UserFactory
            other_user = UserFactory.create()

        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, other_user.api_key)
        res = self.app.get(url)
        assert res.status_code == 403  # Forbidden

    @with_context
    def test_nonexistent_project_returns_404(self):
        """Test accessing schema config for nonexistent project returns 404"""
        project = ProjectFactory.create(published=True)
        url = '/project/nonexistent/schema-config?api_key=%s' % project.owner.api_key
        res = self.app.get(url)
        assert res.status_code == 404

    @with_context
    @patch('pybossa.view.projects.project_repo.save')
    def test_post_exception_handling(self, mock_save):
        """Test POST request handles exceptions properly"""
        # Make save method raise an exception
        mock_save.side_effect = Exception("Database error")

        project = ProjectFactory.create(published=True)
        url = '/project/%s/schema-config?api_key=%s' % (project.short_name, project.owner.api_key)
        res = self.app_get_json(url)
        data = json.loads(res.data)
        csrf = data['csrf']

        schema_config = {
            'task_info_schema': {'type': 'object'}
        }

        res = self.app.post(url, content_type='application/json',
                            data=json.dumps(schema_config),
                            headers={'X-CSRFToken': csrf})
        data = json.loads(res.data)
        assert data['flash'] == 'An error occurred.'
        assert data['status'] == 'error'

