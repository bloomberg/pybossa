# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2018 Scifabric LTD.
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

from unittest.mock import patch

from flask import current_app, render_template, url_for

from pybossa.jobs import export_userdata
from test import Test, with_context
from test.factories import UserFactory, ProjectFactory, TaskRunFactory


#@patch('pybossa.jobs.uploader')
class TestExportAccount(Test):

    @with_context
    @patch('pybossa.exporter.json_export.scheduler')
    @patch('pybossa.exporter.json_export.uploader')
    @patch('uuid.uuid1', return_value='random')
    @patch('pybossa.jobs.Message')
    @patch('pybossa.jobs.send_mail')
    @patch('pybossa.jobs.Attachment')
    @patch('pybossa.jobs.open')
    # @patch('pybossa.jobs.JsonExporter')
    def test_export(self, op, att, m1, m2, m3, m4, m5):
        """Check email is sent to user."""
        user = UserFactory.create()
        project = ProjectFactory.create(owner=user)
        taskrun = TaskRunFactory.create(user=user)

        att.return_value = 'the_attachment_file'
        m4.delete_file.return_value = True

        admin_addr = 'admin@pybossa.com'
        export_userdata(user.id, admin_addr)

        upload_method = 'uploads.uploaded_file'

        personal_data_link = url_for(upload_method,
                                     filename="user_%s/%s_sec_personal_data.zip"
                                     % (user.id, 'random'),
                                     _external=True)
        personal_projects_link = url_for(upload_method,
                                         filename="user_%s/%s_sec_user_projects.zip"
                                         % (user.id, 'random'),
                                         _external=True)
        personal_contributions_link = url_for(upload_method,
                                              filename="user_%s/%s_sec_user_contributions.zip"
                                              % (user.id, 'random'),
                                              _external=True)


        body = render_template('/account/email/exportdata.md',
                           user=user.dictize(),
                           personal_data_link='',
                           config=current_app.config)

        html = render_template('/account/email/exportdata.html',
                           user=user.dictize(),
                           personal_data_link='',
                           config=current_app.config)
        subject = 'Your personal data'
        mail_dict = dict(recipients=[user.email_addr],
                     subject=subject,
                     body=body,
                     html=html,
                     bcc=[admin_addr],
                     attachments=['the_attachment_file'])
        m1.assert_called_with(mail_dict)
        assert 'http' in personal_contributions_link, personal_contributions_link

    @with_context
    @patch('pybossa.core.uploader.delete_file')
    def test_delete_file(self, m1):
        """Test delete file works."""
        from pybossa.jobs import delete_file
        delete_file('f', 'a')
        m1.assert_called_with('f', 'a')
