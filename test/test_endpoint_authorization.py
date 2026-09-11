# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2026 Scifabric LTD.
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
"""Behavioural checks for protected administrative and attachment routes.

The structural checks are covered by test_decorator_ordering.py,
which runs without a database. This file covers what structure cannot: that the
restored decorators actually deny, and that the attachment endpoint fails closed
on a signature payload carrying neither project_id nor user_email - which the
decorator reorder alone does NOT fix.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

from test import with_context
from test.helper.web import Helper
from test.factories import UserFactory
from pybossa.core import signer
from pybossa.signer import EMAIL_ATTACHMENT_SIGNATURE_SALT


class TestVerifyOperationsAuth(Helper):
    """/api/verify was admin-only in intent and anonymous in fact.

    @admin_required sat above @blueprint.route, so it never ran. Two operations
    were exposed: one mails any address, one exports a whole project by email.
    """

    @with_context
    def test_email_service_rejects_anonymous(self):
        res = self.app.post('/api/verify/email_service',
                            data=json.dumps({'email': 'someone@example.com'}),
                            content_type='application/json')
        assert res.status_code != 200, (
            "anonymous caller reached the mail path; admin_required is inert. "
            f"got {res.status_code}")
        assert res.status_code in (301, 302, 401, 403), res.status_code

    @with_context
    def test_export_tasks_rejects_anonymous(self):
        res = self.app.post('/api/verify/export_tasks',
                            data=json.dumps({'project_shortname': 'anything',
                                             'export_type': 'task',
                                             'filetype': 'csv'}),
                            content_type='application/json')
        assert res.status_code != 200, res.status_code
        assert res.status_code in (301, 302, 401, 403), res.status_code

    @with_context
    def test_export_tasks_rejects_non_admin(self):
        UserFactory.create()
        UserFactory.create(email_addr='worker@example.com', name='worker',
                           password='pw1234', admin=False)
        self.signin(email='worker@example.com', password='pw1234')
        res = self.app.post('/api/verify/export_tasks',
                            data=json.dumps({'project_shortname': 'anything',
                                             'export_type': 'task',
                                             'filetype': 'csv'}),
                            content_type='application/json')
        assert res.status_code in (401, 403), (
            f"non-admin reached the export path, got {res.status_code}")

    @with_context
    def test_export_tasks_unknown_project_is_404_not_500(self):
        """Previously export_tasks resolved the shortname itself with no check,
        and an unknown name produced an unhandled error rather than a 404."""
        UserFactory.create(email_addr='root@example.com', name='root',
                           password='pw1234', admin=True)
        self.signin(email='root@example.com', password='pw1234')
        res = self.app.post('/api/verify/export_tasks',
                            data=json.dumps({'project_shortname': 'no-such-project',
                                             'export_type': 'task',
                                             'filetype': 'csv'}),
                            content_type='application/json')
        assert res.status_code == 404, res.status_code


class TestAttachmentDownloadAuth(Helper):
    """GET /attachment/<signature>/<path> had no working authentication.

    @login_required sat above @blueprint.route. Both authorization blocks in the
    body are conditional on the signed payload, so a payload with neither
    project_id nor user_email skipped both and returned the file. The signer is
    shared and unsalted, so a task signature - handed to every contributor with
    every task - verifies here.
    """

    @with_context
    def test_rejects_anonymous(self):
        sig = signer.dumps(
            {'project_id': 1}, salt=EMAIL_ATTACHMENT_SIGNATURE_SALT)
        res = self.app.get(f'/attachment/{sig}/somefile.csv',
                           follow_redirects=False)
        assert res.status_code != 200, (
            f"anonymous download succeeded; login_required is inert. got {res.status_code}")
        assert res.status_code in (301, 302, 401, 403), res.status_code

    @with_context
    def test_task_shaped_signature_is_refused(self):
        """A {'task_id': N} payload has neither
        project_id nor user_email, so before the fix it bypassed both checks.
        Reordering the decorator alone does not close this - any logged-in
        contributor holds a task signature."""
        user = UserFactory.create(
            email_addr='worker@example.com', name='worker', admin=False)
        self.signin_user(user)
        sig = signer.dumps(
            {'task_id': 1}, salt=EMAIL_ATTACHMENT_SIGNATURE_SALT)
        res = self.app.get(f'/attachment/{sig}/somefile.csv')
        assert res.status_code == 403, (
            f"task-shaped signature was accepted, got {res.status_code}")

    @with_context
    def test_empty_payload_is_refused(self):
        user = UserFactory.create(
            email_addr='worker2@example.com', name='worker2', admin=False)
        self.signin_user(user)
        sig = signer.dumps({}, salt=EMAIL_ATTACHMENT_SIGNATURE_SALT)
        res = self.app.get(f'/attachment/{sig}/somefile.csv')
        assert res.status_code == 403, res.status_code

    @with_context
    def test_other_users_email_is_refused(self):
        """user_email in the payload must match the caller."""
        user = UserFactory.create(
            email_addr='worker3@example.com', name='worker3', admin=False)
        self.signin_user(user)
        sig = signer.dumps(
            {
                'user_email': 'someone.else@example.com',
                's3_key': 'attachments/somefile.csv',
            },
            salt=EMAIL_ATTACHMENT_SIGNATURE_SALT)
        active_user = SimpleNamespace(
            admin=False, email_addr='worker3@example.com')
        with patch('pybossa.view.attachment.current_user', active_user):
            res = self.app.get(f'/attachment/{sig}/somefile.csv')
        assert res.status_code == 403, res.status_code
