# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2015 Scifabric LTD.
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

from test import Test, assert_not_raises, with_context
from pybossa.auth import ensure_authorized_to
from nose.tools import assert_raises
from werkzeug.exceptions import Forbidden, Unauthorized
from unittest.mock import patch
from test.test_authorization import mock_current_user
from test.factories import ProjectFactory, UserFactory, WebhookFactory
from pybossa.model.webhook import Webhook


class TestWebhookAuthorization(Test):

    mock_anonymous = mock_current_user()
    mock_authenticated = mock_current_user(anonymous=False, admin=False, id=2)
    mock_admin = mock_current_user(anonymous=False, admin=True, id=1)



    @with_context
    @patch('pybossa.auth.current_user', new=mock_anonymous)
    def test_anonymous_user_cannot_read_webhook(self):
        """Test anonymous users cannot read a webhook"""

        project = ProjectFactory.create()
        webhook = WebhookFactory.create(project_id=project.id)

        assert_raises(Unauthorized, ensure_authorized_to, 'read', webhook)


    @with_context
    @patch('pybossa.auth.current_user', new=mock_anonymous)
    def test_anonymous_user_cannot_read_project_webhooks(self):
        """Test anonymous users cannot read webhooks of a specific project"""

        project = ProjectFactory.create()

        assert_raises(Unauthorized, ensure_authorized_to, 'read', Webhook, project_id=project.id)


    @with_context
    @patch('pybossa.auth.current_user', new=mock_authenticated)
    def test_owner_user_cannot_read_webhook(self):
        """Test owner users can read a webhook"""

        owner = UserFactory.create_batch(2)[1]
        project = ProjectFactory.create(owner=owner)
        webhook = WebhookFactory.create(project_id=project.id)

        assert self.mock_authenticated.id == project.owner_id

        assert_not_raises(Exception, ensure_authorized_to, 'read', webhook)


    @with_context
    @patch('pybossa.auth.current_user', new=mock_authenticated)
    def test_owner_user_cannot_read_project_webhooks(self):
        """Test owner users can read webhooks of a specific project"""

        owner = UserFactory.create_batch(2)[1]
        project = ProjectFactory.create(owner=owner)

        assert_not_raises(Exception, ensure_authorized_to, 'read', Webhook, project_id=project.id)


    @with_context
    @patch('pybossa.auth.current_user', new=mock_admin)
    def test_admin_user_can_read_webhook(self):
        """Test admin users can read a webhook"""

        owner = UserFactory.create_batch(2)[1]
        project = ProjectFactory.create(owner=owner)
        webhook = WebhookFactory.create(project_id=project.id)

        assert self.mock_admin.id != project.owner_id
        assert_not_raises(Exception, ensure_authorized_to, 'read', webhook)


    @with_context
    @patch('pybossa.auth.current_user', new=mock_admin)
    def test_admin_user_can_read_project_webhooks(self):
        """Test admin users can read webhooks from a project"""

        owner = UserFactory.create_batch(2)[1]
        project = ProjectFactory.create(owner=owner)

        assert self.mock_admin.id != project.owner_id
        assert_not_raises(Exception, ensure_authorized_to, 'read', Webhook, project_id=project.id)


    @with_context
    @patch('pybossa.auth.current_user', new=mock_anonymous)
    def test_anonymous_user_cannot_crud_webhook(self):
        """Test anonymous users cannot crud webhooks"""

        webhook = Webhook()

        assert_raises(Unauthorized, ensure_authorized_to, 'create', webhook)
        assert_raises(Unauthorized, ensure_authorized_to, 'update', webhook)
        assert_raises(Unauthorized, ensure_authorized_to, 'delete', webhook)


    @with_context
    @patch('pybossa.auth.current_user', new=mock_authenticated)
    def test_authenticated_user_cannot_crud_webhook(self):
        """Test authenticated users cannot crud webhooks"""

        webhook = Webhook()

        assert_raises(Forbidden, ensure_authorized_to, 'create', webhook)
        assert_raises(Forbidden, ensure_authorized_to, 'update', webhook)
        assert_raises(Forbidden, ensure_authorized_to, 'delete', webhook)


    @with_context
    @patch('pybossa.auth.current_user', new=mock_admin)
    def test_admin_user_cannot_crud_webhook(self):
        """Test admin users cannot crud webhooks"""

        webhook = Webhook()

        assert_raises(Forbidden, ensure_authorized_to, 'create', webhook)
        assert_raises(Forbidden, ensure_authorized_to, 'update', webhook)
        assert_raises(Forbidden, ensure_authorized_to, 'delete', webhook)
