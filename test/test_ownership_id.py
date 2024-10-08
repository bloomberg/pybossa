import json
from unittest.mock import patch
from test.helper import web
from test import with_context
from test import db, Fixtures
from test.factories import ProjectFactory, UserFactory
from pybossa.core import user_repo
from pybossa.repositories import ProjectRepository


class TestOwnershipId(web.Helper):

    def setup(self):
        super(TestOwnershipId, self).setUp()
        self.project_repo = ProjectRepository(db)

    @with_context
    def test_00_access_ownership_id(self):
        """Test admin and owner can access coowners page"""
        self.register()
        self.signin()
        self.new_project()

        res = self.app.get('/project/sampleapp/ownership_id', content_type='application/json', follow_redirects=True)
        assert "ownership_id" in str(res.data), res.data

        self.signout()
        self.signin()


    @with_context
    def test_01_edit_ownership_id(self):
        """Test admin and owner can edit ownership id"""
        self.register()
        csrf = self.get_csrf('/account/signin')
        self.signin()
        self.new_project()

        # test add id
        payload = {'ownership_id': '12345'}
        res = self.app.put('/project/sampleapp/ownership_id', headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(payload))
        assert "12345" in str(res.data), res.data
        # test same id as saved
        payload = {'ownership_id': '12345'}
        res = self.app.put('/project/sampleapp/ownership_id', headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(payload))
        assert "12345" in str(res.data), res.data
        # test remove id
        payload = {'ownership_id': ''}
        res = self.app.put('/project/sampleapp/ownership_id', headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(payload))
        assert "12345" not in str(res.data), res.data

        self.signout()
        self.signin()


    @with_context
    def test_02_invalid_ownership_ids(self):
        """Test ownership id validation"""
        self.register()
        csrf = self.get_csrf('/account/signin')
        self.signin()
        self.new_project()

        payload = {'ownership_id': 'abcd123'}
        res = self.app.put('/project/sampleapp/ownership_id', headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(payload))
        assert "Ownership ID must be numeric and less than 20 characters!" in str(res.data), res.data

        payload = {'ownership_id': '123!!!abc'}
        res = self.app.put('/project/sampleapp/ownership_id', headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(payload))
        assert "Ownership ID must be numeric and less than 20 characters!" in str(res.data), res.data

        payload = {'ownership_id': '1111111111111111111111'}
        res = self.app.put('/project/sampleapp/ownership_id', headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(payload))
        assert "Ownership ID must be numeric and less than 20 characters!" in str(res.data), res.data

        self.signout()
        self.signin()
