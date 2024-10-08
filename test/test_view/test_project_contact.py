# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2019 Scifabric LTD.
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
from test import with_context, with_request_context
from test.helper.web import Helper
from test.factories import ProjectFactory, UserFactory
from unittest.mock import patch
from nose.tools import assert_raises
from pybossa.view.projects import sanitize_project_owner

class TestProjectContact(Helper):

    @with_context
    @patch('pybossa.view.projects.mail_queue.enqueue')
    def test_project_contact_success(self, enqueue):
        """Test Project Contact Success."""
        message = 'hello'

        admin, owner, user = UserFactory.create_batch(3)

        # Create co-owners.
        coowner1 = UserFactory.create(name='My Co-Owner User 1', admin=True)
        coowner2 = UserFactory.create(name='My Co-Owner User 2', subadmin=True)

        # Create a project with a co-owner.
        project = ProjectFactory.create(owner=owner, short_name='test-app', name='My New Project', owners_ids=[coowner1.id, coowner2.id])

        # Obtain a CSRF key.
        csrf = self.get_csrf('/account/signin')

        # Make a request to the api.
        url = '/project/' + project.short_name + '/contact?api_key=' + user.api_key
        data = dict(message=message)
        res = self.app.post(url, headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(data))

        # Verify status code from response.
        assert res.status_code == 200

        # Verify call to mail_queue.enqueue for sending the email.
        assert len(enqueue.call_args_list) == 1

        # Get contents of email.
        str_message = str(enqueue.call_args_list[0])

        # Verify message content.
        assert str_message.find('body') > -1
        assert str_message.find('Project Name: ' + project.name) > -1
        assert str_message.find('Project Short Name: ' + project.short_name) > -1
        assert str_message.find('Message: ' + message) > -1

        # Verify recipient for project owner.
        recipients_index = str_message.find('recipients')
        assert recipients_index > -1
        assert str_message.find(owner.email_addr) > recipients_index

        # Verify recipients for project coowners.
        assert str_message.find(coowner1.email_addr) > recipients_index
        assert str_message.find(coowner2.email_addr) > recipients_index

        # Verify subject.
        subject_index = str_message.find('subject')
        assert subject_index > -1
        assert str_message.find(user.email_addr) > subject_index

        # Verify contents of response contains: { "success": True }
        data = json.loads(res.data)
        assert data.get('success') is True


    @with_context
    @patch('pybossa.view.projects.mail_queue.enqueue')
    def test_project_contact_no_disabled_owner(self, enqueue):
        """Test Project Contact not emailing a disabled co-owner."""
        message = 'hello'

        admin, owner, user = UserFactory.create_batch(3)

        # Create a disabled user as a co-owner.
        coowner = UserFactory.create(name='My Disabled Co-Owner User', enabled=False, subadmin=True)

        # Create a project with a disabled co-owner.
        project = ProjectFactory.create(owner=owner, short_name='test-app', name='My New Project', owners_ids=[coowner.id])

        # Obtain a CSRF key.
        csrf = self.get_csrf('/account/signin')

        # Make a request to the api.
        url = '/project/' + project.short_name + '/contact?api_key=' + user.api_key
        data = dict(message=message)
        res = self.app.post(url, headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(data))

        # Get contents of email.
        str_message = str(enqueue.call_args_list[0])

        # Verify recipient for project owner.
        recipients_index = str_message.find('recipients')
        assert recipients_index > -1
        assert str_message.find(owner.email_addr) > recipients_index

        # Verify no recipient for disabled co-owner.
        assert str_message.find(coowner.email_addr) == -1

    @with_context
    @patch('pybossa.view.projects.mail_queue.enqueue')
    def test_project_contact_no_non_admin_subadmin_owner(self, enqueue):
        """Test Project Contact not emailing a co-owner who is not an admin nor subadmin."""
        message = 'hello'

        admin, owner, user = UserFactory.create_batch(3)

        # Create a user as a co-owner that is not an admin nor subadmin.
        coowner = UserFactory.create(name='My Non-Admin-Subadmin User')

        # Create a project with a disabled co-owner.
        project = ProjectFactory.create(owner=owner, short_name='test-app', name='My New Project', owners_ids=[coowner.id])

        # Obtain a CSRF key.
        csrf = self.get_csrf('/account/signin')

        # Make a request to the api.
        url = '/project/' + project.short_name + '/contact?api_key=' + user.api_key
        data = dict(message=message)
        res = self.app.post(url, headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(data))

        # Get contents of email.
        str_message = str(enqueue.call_args_list[0])

        # Verify recipient for project owner.
        recipients_index = str_message.find('recipients')
        assert recipients_index > -1
        assert str_message.find(owner.email_addr) > recipients_index

        # Verify no recipient for co-owner that is not an admin nor subadmin.
        assert str_message.find(coowner.email_addr) == -1

    @with_context
    def test_project_contact_no_project(self):
        """Test Project Contact No Project."""
        admin, owner, user = UserFactory.create_batch(3)

        # Obtain a CSRF key.
        csrf = self.get_csrf('/account/signin')

        # Make a request to the api.
        url = '/project/invalid/contact?api_key=' + user.api_key
        data = dict(message='hello')
        res = self.app.post(url, headers={'X-CSRFToken': csrf}, content_type='application/json', data=json.dumps(data))

        # Verify status code from response.
        assert res.status_code == 404

    @with_context
    def test_project_contact_no_auth(self):
        """Test Project Contact No Auth."""
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner, short_name='test-app', name='My New Project')

        # Obtain a CSRF key.
        csrf = self.get_csrf('/account/signin')

        # Make a request to the api.
        url = '/project/' + project.short_name + '/contact?api_key=' + user.api_key
        res = self.app.get(url, headers={'X-CSRFToken': csrf})

        # Verify status code from response.
        assert res.status_code == 405

    @with_request_context
    @patch('pybossa.cache.users.public_get_user_summary')
    def test_project_sanitize_project_no_owner_not_project_owner(self, public_get_user_summary):
        """Test Project sanitize_project_owner when no owner returned and current user not owner."""
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner, short_name='test-app', name='My New Project')

        # Simulate no returned user.
        public_get_user_summary.return_value = None

        # Verify error is raised from owner_sanitized.pop().
        with assert_raises(AttributeError) as ex:
            sanitize_project_owner(project, owner, user)

    @with_request_context
    @patch('pybossa.cache.users.get_user_summary')
    def test_project_sanitize_project_no_owner_is_project_owner(self, get_user_summary):
        """Test Project sanitize_project_owner when no owner returned and current user is owner."""
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner, short_name='test-app', name='My New Project')

        get_user_summary.return_value = None

        # Verify error is raised from owner_sanitized.pop().
        with assert_raises(AttributeError) as ex:
            sanitize_project_owner(project, owner, owner)
