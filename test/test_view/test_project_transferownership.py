# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2017 Scifabric
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
from test import db, with_context
from test.factories import ProjectFactory, UserFactory
from test.helper import web
from pybossa.repositories import UserRepository, ProjectRepository
import json
from test.helper.gig_helper import make_subadmin

project_repo = ProjectRepository(db)
user_repo = UserRepository(db)


class TestProjectTransferOwnership(web.Helper):

    @with_context
    def test_transfer_anon_get(self):
        """Test transfer ownership page is not shown to anon."""
        project = ProjectFactory.create()
        url = '/project/%s/transferownership' % project.short_name
        res = self.app_get_json(url, follow_redirects=True)
        assert 'signin' in str(res.data), res.data

    @with_context
    def test_transfer_auth_not_owner_get(self):
        """Test transfer ownership page is forbidden for not owner."""
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        url = '/project/%s/transferownership?api_key=%s' % (project.short_name,
                                                            user.api_key)
        res = self.app_get_json(url, follow_redirects=True)
        data = json.loads(res.data)
        assert data['code'] == 403, data

    @with_context
    def test_transfer_auth_owner_get(self):
        """Test transfer ownership page is ok for owner."""
        admin, owner, user = UserFactory.create_batch(3)
        make_subadmin(owner)
        project = ProjectFactory.create(owner=owner)
        url = '/project/%s/transferownership?api_key=%s' % (project.short_name,
                                                            owner.api_key)
        res = self.app_get_json(url, follow_redirects=True)
        data = json.loads(res.data)
        assert data['form'], data
        assert data['form']['errors'] == {}, data
        assert not data['form']['email_addr'], data
        assert data['form']['csrf'] is not None, data

    @with_context
    def test_transfer_auth_admin_get(self):
        """Test transfer ownership page is ok for admin."""
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        url = '/project/%s/transferownership?api_key=%s' % (project.short_name,
                                                            admin.api_key)
        res = self.app_get_json(url, follow_redirects=True)
        data = json.loads(res.data)
        assert data['form'], data
        assert data['form']['errors'] == {}, data
        assert not data['form']['email_addr'], data
        assert data['form']['csrf'] is not None, data

    @with_context
    def test_transfer_auth_owner_post(self):
        """Test transfer ownership page post is ok for owner."""
        admin, owner, user = UserFactory.create_batch(3)
        make_subadmin(owner)
        project = ProjectFactory.create(owner=owner)
        url = '/project/%s/transferownership?api_key=%s' % (project.short_name,
                                                            owner.api_key)

        assert project.owner_id == owner.id
        payload = dict(email_addr=user.email_addr)
        res = self.app_post_json(url, data=payload,
                                 follow_redirects=True)
        data = json.loads(res.data)
        assert data['next'] is not None, data

        err_msg = "The project owner id should be different"
        assert project.owner_id == user.id, err_msg

    @with_context
    def test_transfer_auth_owner_post_wrong_email(self):
        """Test transfer ownership page post is ok for wrong email."""
        admin, owner, user = UserFactory.create_batch(3)
        make_subadmin(owner)
        project = ProjectFactory.create(owner=owner)
        url = '/project/%s/transferownership?api_key=%s' % (project.short_name,
                                                            owner.api_key)

        assert project.owner_id == owner.id
        payload = dict(email_addr="wrong@email.com")
        res = self.app_post_json(url, data=payload,
                                 follow_redirects=True)
        data = json.loads(res.data)
        assert data['next'] is not None, data
        assert "project owner not found" in data['flash'], data
        err_msg = "The project owner id should be the same"
        assert project.owner_id == owner.id, err_msg

    @with_context
    def test_transfer_auth_admin_post(self):
        """Test transfer ownership page post is ok for admin."""
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        url = '/project/%s/transferownership?api_key=%s' % (project.short_name,
                                                            admin.api_key)

        assert project.owner_id == owner.id
        payload = dict(email_addr=user.email_addr)
        res = self.app_post_json(url, data=payload,
                                 follow_redirects=True)
        data = json.loads(res.data)
        assert data['next'] is not None, data

        err_msg = "The project owner id should be different"
        assert project.owner_id == user.id, err_msg

    @with_context
    def test_transfer_auth_user_post(self):
        """Test transfer ownership page post is forbidden for not owner."""
        admin, owner, user = UserFactory.create_batch(3)
        project = ProjectFactory.create(owner=owner)
        url = '/project/%s/transferownership?api_key=%s' % (project.short_name,
                                                            user.api_key)

        assert project.owner_id == owner.id
        payload = dict(email_addr=user.email_addr)
        res = self.app_post_json(url, data=payload,
                                 follow_redirects=True)
        data = json.loads(res.data)
        assert data['code'] == 403, data

    @with_context
    def test_transfer_retain_coowners(self):
        """Test transfer ownership retains existing coowners after transfer to new owner."""
        admin, owner, user1, user2 = UserFactory.create_batch(4)
        coowners = [owner.id, user2.id]
        project = ProjectFactory.create(owner=owner, owners_ids=coowners)
        url = '/project/%s/transferownership?api_key=%s' % (project.short_name,
                                                            admin.api_key)

        # Sanity check that the correct owner and coowners have been set on the project.
        assert project.owner_id == owner.id
        assert owner.id in project.owners_ids
        assert user2.id in project.owners_ids

        csrf = self.get_csrf(url)
        headers = {'X-CSRFToken': csrf}

        # Transfer the project from owner to user1.
        payload = dict(email_addr=user1.email_addr)
        res = self.app_post_json(url, data=payload, headers=headers, follow_redirects=True)
        data = json.loads(res.data)
        assert data['next'] is not None, data

        # Confirm the new owner id.
        err_msg = "The project owner id should be different"
        assert project.owner_id == user1.id, err_msg

        # Confirm the existing coowners are retained.
        err_msg = "Co-owner should still exist on project after transfer"
        assert user2.id in project.owners_ids, err_msg

        # Confirm the new project owner is included in the coowners.
        err_msg = "New owner should exist in coowners after transfer"
        assert user1.id in project.owners_ids, err_msg

        # Confirm the old project owner is no longer included in the coowners.
        err_msg = "Old owner should not exist in coowners after transfer"
        assert owner.id not in project.owners_ids, err_msg

    @with_context
    def test_transfer_retain_coowners_multi(self):
        """Test transfer ownership retains existing coowners (multiple) after transfer to new owner."""
        admin, owner, user1, user2, user3 = UserFactory.create_batch(5)
        coowners = [owner.id, user2.id, user3.id]
        project = ProjectFactory.create(owner=owner, owners_ids=coowners)
        url = '/project/%s/transferownership?api_key=%s' % (project.short_name,
                                                            admin.api_key)

        # Sanity check that the correct owner and coowners have been set on the project.
        assert project.owner_id == owner.id
        assert len(project.owners_ids) == 3
        assert owner.id in project.owners_ids
        assert user2.id in project.owners_ids
        assert user3.id in project.owners_ids

        csrf = self.get_csrf(url)
        headers = {'X-CSRFToken': csrf}

        # Transfer the project from owner to user1.
        payload = dict(email_addr=user1.email_addr)
        res = self.app_post_json(url, data=payload, headers=headers, follow_redirects=True)
        data = json.loads(res.data)
        assert data['next'] is not None, data

        # Confirm the new owner id.
        err_msg = "The project owner id should be different"
        assert project.owner_id == user1.id, err_msg

        # Confirm the existing coowners are retained.
        err_msg = "Co-owner should still exist on project after transfer"
        assert len(project.owners_ids) == 3
        assert user2.id in project.owners_ids, err_msg
        assert user3.id in project.owners_ids, err_msg

        # Confirm the new project owner is included in the coowners.
        err_msg = "New owner should exist in coowners after transfer"
        assert user1.id in project.owners_ids, err_msg

        # Confirm the old project owner is no longer included in the coowners.
        err_msg = "Old owner should not exist in coowners after transfer"
        assert owner.id not in project.owners_ids, err_msg
