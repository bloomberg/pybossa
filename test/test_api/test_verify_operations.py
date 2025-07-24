# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2025 Scifabric LTD.
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
from flask import Response
from test import with_request_context
from test.factories import ProjectFactory, TaskFactory, TaskRunFactory, UserFactory
from test.test_api import TestAPI
from unittest.mock import patch
from pybossa.core import signer

class TestVerifyOpAPI(TestAPI):
    """
    Test suite for verifying the operations of the API.
    This class contains test cases to ensure that the API operations
    function as expected. It inherits from the `TestAPI` base class
    and utilizes a request context for testing.
    """

    @with_request_context
    def test_verify_operations_bad_request(self):
        """Test the /api/verify endpoint for a bad input."""

        owner = UserFactory.create(pro=False)
        owner.set_password("abc")
        project = ProjectFactory.create(owner=owner)

        resp = self.app.post('/api/verify/bad_request')
        assert resp.status_code == 400 and resp.data.decode() == "Bad Request"
        
        data = {
            "project_shortname": project.short_name,
            "export_type": "bad_type",
            "filetype": "csv"
        }
        resp = self.app.post(f"/api/verify/export_tasks", data=data)
        assert resp.status_code == 400 and resp.data.decode() == "Invalid export_type parameter"
        

    @with_request_context
    @patch('pybossa.cloud_store_api.s3.time')
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_verify_operations_export_tasks(self, create_conn, mock_time):
        """Test the /api/verify/export_tasks endpoint export tasks and 
        generates email with attachment."""

        conn = create_conn.return_value
        buck = conn.get_bucket.return_value
        key = buck.new_key.return_value
        key.set_contents_from_string.return_value = None
        current_time = "01012025"
        mock_time.time.return_value = current_time
        
        admin = UserFactory.create(admin=True)
        project = ProjectFactory.create(owner=admin, short_name="test_project")
    
        headers = {"Authorization": admin.api_key}
        data = {
            "project_shortname": project.short_name,
            "export_type": "task",
            "filetype": "csv"
        }
        payload = {"project_id": project.id}
        payload["user_email"] = admin.email_addr
        signature = "mocked_signature"

        with patch('pybossa.core.signer.dumps', return_value=signature), \
             patch('pybossa.jobs.email_service') as mock_emailsvc:
            mock_emailsvc.enabled = True
            with patch.dict(self.flask_app.config, {
                'EXPORT_MAX_EMAIL_SIZE': 0,
                'S3_REQUEST_BUCKET_V2': 'export-bucket',
                'SERVER_URL': "https://testserver.com"
            }):
                expected_contents = f'You can download your file <a href="https://testserver.com/attachment/{signature}/{int(current_time)}-{project.id}_{project.short_name}_task_csv.zip'
                resp = self.app.post("/api/verify/export_tasks", json=data, headers=headers)
                assert resp.status_code == 200 and resp.data.decode() == f"Task CSV file was successfully exported for: {project.name}"
                args, _ = mock_emailsvc.send.call_args
                message = args[0]
                print("*** Message body ****", message["body"])
                print("*** Expected contents ****", expected_contents)
                assert expected_contents in message["body"], message["body"]


    @with_request_context
    @patch('pybossa.cloud_store_api.s3.time')
    @patch('pybossa.cloud_store_api.s3.create_connection')
    def test_verify_operations_send_mail(self, create_conn, mock_time):
        """Test the /api/verify/email_service endpoint 
        generates email to be sent via email service."""
        
        admin = UserFactory.create(admin=True)
        headers = {"Authorization": admin.api_key}        

        # missing parmater
        resp = self.app.post("/api/verify/email_service", headers=headers)
        assert resp.data.decode() == "Missing email parameter"

        # successful email delivery
        with patch('pybossa.jobs.email_service') as mock_emailsvc:
            mock_emailsvc.enabled = True
            recipient = "abc@abc.com"
            data = {"email": recipient}
            resp = self.app.post(f"/api/verify/email_service?email={recipient}", json=data, headers=headers)
            assert resp.status_code == 200 and resp.data.decode() == "OK"
            args, _ = mock_emailsvc.send.call_args
            message = args[0]
            assert message["recipients"][0] == recipient and message["body"] == "Greetings. Email sent via /api/verify/email_service"
