from unittest.mock import patch

from test import db, with_context
from test.factories import ProjectFactory, UserFactory
from test.helper import web
from pybossa.repositories import ProjectRepository, UserRepository

project_repo = ProjectRepository(db)
user_repo = UserRepository(db)


class TestProjectExtConfig(web.Helper):
    external_config_patch = {
        "EXTERNAL_CONFIGURATIONS": {
            "authorized_services": {
                "display": "Authorized Services",
                "fields": {
                    "service_key": [
                        "SelectMultipleField",
                        "Authorized Services",
                        None,
                        {
                            "choices": [
                                ("test-service-1", "test-service-1"),
                                ("test-service-2", "test-service-2"),
                            ],
                        },
                    ]
                },
            }
        }
    }

    @with_context
    def setUp(self):
        super(TestProjectExtConfig, self).setUp()
        self.owner = UserFactory.create(email_addr='a@a.com')
        self.owner.set_password('1234')
        user_repo.save(self.owner)
        project = ProjectFactory.create(owner=self.owner, published=False)
        self.project_id = project.id
        self.signin(email='a@a.com', password='1234')

    @with_context
    def test_no_config(self):
        project = project_repo.get(self.project_id)
        res = self.app.get('/project/%s/ext-config' % project.short_name)

        assert 'No external services have been configured' in str(res.data)

    @with_context
    def test_form_display_authorized_services_admin(self):
        with patch.dict(self.flask_app.config, self.external_config_patch):
            project = project_repo.get(self.project_id)
            res = self.app.get("/project/%s/ext-config" % project.short_name)
            # Only admins can see 'Authorized Services' form
            assert "Authorized Services" in str(res.data)

    @with_context
    def test_form_display_authorized_services_non_admin(self):
        with patch.dict(self.flask_app.config, self.external_config_patch):
            non_admin = UserFactory.create(email_addr="b@b.com", admin=False)
            non_admin.set_password("1234")
            user_repo.save(non_admin)
            project = ProjectFactory.create(owner=non_admin)
            self.signin(email="b@b.com", password="1234")
            res = self.app.get("/project/%s/ext-config" % project.short_name)
            # Non-admins cannot see 'Authorized Services' form
            assert "Authorized Services" not in str(res.data)

    @with_context
    def test_form_display(self):
        ext_config = {
            'ml_service': {
                'display': 'Active Learning Config',
                'fields': {
                    'model': ('TextField', 'Model', None)
                }
            }
        }
        with patch.dict(self.flask_app.config, {'EXTERNAL_CONFIGURATIONS': ext_config}):
            project = project_repo.get(self.project_id)
            res = self.app.get('/project/%s/ext-config' % project.short_name)

        assert 'Active Learning Config' in str(res.data)
        assert 'Model' in str(res.data)

    @with_context
    def test_add_config(self):
        ext_config = {
            'ml_service': {
                'display': 'Active Learning Config',
                'fields': {
                    'model': ('TextField', 'Model', None)
                }
            }
        }
        with patch.dict(self.flask_app.config, {'EXTERNAL_CONFIGURATIONS': ext_config}):
            project = project_repo.get(self.project_id)
            data = {
                'ml_service': True,
                'model': 'random_forest'
            }
            self.app.post('/project/%s/ext-config' % project.short_name, data=data)

        project = project_repo.get(self.project_id)
        assert project.info['ext_config']['ml_service']['model'] == 'random_forest'

    @with_context
    def test_update_config(self):
        ext_config = {
                'ml_service': {
                    'display': 'Active Learning Config',
                    'fields': {
                        'model': ('TextField', '', None)
                    }
                }
            }

        with patch.dict(self.flask_app.config,
                        {'EXTERNAL_CONFIGURATIONS': ext_config}):
            project = project_repo.get(self.project_id)
            self.app.post('/project/%s/ext-config' % project.short_name)

        project = project_repo.get(self.project_id)
        print(project)
        assert 'ext_config' not in project.info.keys()

    @with_context
    def test_update_path_for_responses(self):
        config = {
            "PROJECT_INFO_FIELDS_TO_VALIDATE": [{
                "path": "ext_config::service::file_path",
                "regex": [r"[\\\{\}\`\[\]\"\'\^\%\*\>\<\~\#\|\s]", r'[\x00-\x1f]', r'[\x80-\xff]', '\x7f'],
                "error_msg": "File path contains invalid characters."
            }],
            "EXTERNAL_CONFIGURATIONS": {
                "service": {
                    'display': 'Response File Location',
                    'fields': {
                        'file_path': ('TextField', 'Path for responses', None)
                    }
                }
            }
        }

        with patch.dict(self.flask_app.config, config):
            project = project_repo.get(self.project_id)
            project.info['ext_config'] = {
                "service": {
                    "file_path": "",
                }
            }
            project_repo.save(project)
            data = {
                "service": True,
                "file_path": "abc/ def",
            }
            res = self.app.post('/project/%s/ext-config' % project.short_name, data=data)
            project = project_repo.get(self.project_id)

            # file_path contains a space
            assert "400 Bad Request: File path contains invalid characters" in str(res.data)
