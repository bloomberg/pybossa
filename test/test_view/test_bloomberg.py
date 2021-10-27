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
from unittest.mock import MagicMock, patch

from pybossa.view.account import generate_bsso_account_notification
from test import Test, with_context
from test.factories import UserFactory

from pybossa.util import get_s3_bucket_name

class TestBloomberg(Test):
    def setUp(self):
        super(TestBloomberg, self).setUp()

    @with_context
    def test_login_get(self):
        res = self.app.get('/bloomberg/login')
        redirect_url = self.flask_app.config['BSSO_SETTINGS']['idp']['singleSignOnService']['url']
        assert res.status_code == 302, res.status_code
        assert res.headers['Location'].startswith(redirect_url), res.headers

    @with_context
    @patch('pybossa.view.bloomberg.OneLogin_Saml2_Auth', autospec=True)
    def test_login_post_errors(self, mock):
        mock_auth = MagicMock()
        mock_auth.get_errors.return_value = True
        mock.return_value = mock_auth
        res = self.app.post('/bloomberg/login')
        assert res.status_code == 302, res.status_code

    @with_context
    @patch('pybossa.view.bloomberg.OneLogin_Saml2_Auth', autospec=True)
    def test_login_post_success(self, mock_one_login):
        user = UserFactory.create()
        redirect_url = 'http://localhost'
        mock_auth = MagicMock()
        mock_auth.get_errors.return_value = False
        mock_auth.is_authenticated.return_value = True
        mock_auth.get_attributes.return_value = {'emailAddress': [user.email_addr]}
        mock_one_login.return_value = mock_auth
        res = self.app.post('/bloomberg/login', content_type='multipart/form-data', data={'RelayState': redirect_url})
        assert res.status_code == 302, res.status_code
        assert res.headers['Location'] == redirect_url, res.headers

    @with_context
    @patch('pybossa.view.bloomberg.OneLogin_Saml2_Auth', autospec=True)
    def test_login_post_not_authenticated(self, mock_one_login):
        mock_auth = MagicMock()
        mock_auth.get_errors.return_value = False
        mock_auth.is_authenticated.return_value = False
        mock_one_login.return_value = mock_auth
        res = self.app.post('/bloomberg/login')
        assert res.status_code == 302, res.status_code

    @with_context
    @patch('pybossa.view.bloomberg.create_account', autospec=True)
    @patch('pybossa.view.bloomberg.OneLogin_Saml2_Auth', autospec=True)
    def test_login_create_account_fail(self, mock_one_login, mock_create_account):
        redirect_url = 'http://localhost'
        mock_auth = MagicMock()
        mock_auth.get_errors.return_value = False
        mock_auth.process_response.return_value = None
        mock_auth.is_authenticated = False
        mock_one_login.return_value = mock_auth
        mock_auth.get_attributes.return_value = {'firstName': ['test'], 'emailAddress': ['test@test.com'], 'lastName': ['test'], 'username': ['test'], 'firmId': ['1234567']}
        res = self.app.post('/bloomberg/login', method='POST', content_type='multipart/form-data', data={'RelayState': redirect_url})
        assert mock_create_account.called == False
        assert res.status_code == 302, res.status_code

    @with_context
    @patch('pybossa.view.bloomberg.create_account', autospec=True)
    @patch('pybossa.view.bloomberg.OneLogin_Saml2_Auth', autospec=True)
    def test_login_create_private_account_success(self, mock_one_login, mock_create_account):
        redirect_url = 'http://localhost'
        mock_auth = MagicMock()
        mock_app = MagicMock()
        mock_app.config.get('PRIVATE_INSTANCE').return_value = True
        mock_auth.get_errors.return_value = False
        mock_auth.process_response.return_value = None
        mock_auth.is_authenticated = True 
        mock_one_login.return_value = mock_auth
        mock_auth.get_attributes.return_value = {'firstName': ['test'], 'lastName': ['test'], 'emailAddress': ['test@bloomberg.net'], 'username': ['test'], 'firmId': ['1234567']}
        res = self.app.post('/bloomberg/login', method='POST', content_type='multipart/form-data', data={'RelayState': redirect_url})
        assert mock_create_account.called
        assert res.status_code == 302, res.status_code

    @with_context
    @patch('pybossa.view.bloomberg.create_account', autospec=True)
    @patch('pybossa.view.bloomberg.OneLogin_Saml2_Auth', autospec=True)
    def test_login_create_public_account_success(self, mock_one_login, mock_create_account):
        redirect_url = 'http://localhost'
        mock_auth = MagicMock()
        mock_app = MagicMock()
        mock_app.config.get('PRIVATE_INSTANCE').return_value = False
        mock_auth.get_errors.return_value = False
        mock_auth.process_response.return_value = None
        mock_auth.is_authenticated = True 
        mock_one_login.return_value = mock_auth
        mock_auth.get_attributes.return_value = {'firstName': ['test'], 'lastName': ['test'], 'emailAddress': ['test@bloomberg.net'], 'username': ['test'], 'firmId': ['1234567']}
        res = self.app.post('/bloomberg/login', method='POST', content_type='multipart/form-data', data={'RelayState': redirect_url})
        assert mock_create_account.called
        assert res.status_code == 302, res.status_code
    
    @with_context
    @patch('pybossa.view.bloomberg.create_account', autospec=True)
    @patch('pybossa.view.bloomberg._sign_in_user', autospec=True)    
    @patch('pybossa.view.bloomberg.OneLogin_Saml2_Auth', autospec=True)
    def test_login_create_account_error(self, mock_one_login, mock_sign_in, mock_create_account):
        redirect_url = 'http://localhost'
        mock_auth = MagicMock()
        mock_auth.get_errors.return_value = False
        mock_auth.process_response.return_value = None
        mock_auth.is_authenticated = True
        mock_one_login.return_value = mock_auth
        mock_sign_in.side_effect = Exception()
        mock_auth.get_attributes.return_value = {'firstName': ['test'], 'emailAddress': ['test@test.com'], 'lastName': ['test'], 'PVFLevels': ['PVF_GUTS_3'], 'username': ['test'], 'firmId': ['1234567']}
        res = self.app.post('/bloomberg/login', method='POST', content_type='multipart/form-data', data={'RelayState': redirect_url})
        assert mock_create_account.called 
        assert res.status_code == 302, res.status_code

    @with_context
    @patch('pybossa.view.bloomberg.OneLogin_Saml2_Auth', autospec=True)
    def test_bsso_auto_account_alert(self, mock_one_login):
        redirect_url = 'http://localhost'
        mock_auth = MagicMock()
        mock_auth.get_errors.return_value = False
        mock_auth.process_response.return_value = None
        mock_auth.is_authenticated = True 
        mock_one_login.return_value = mock_auth
        user = {'firstName': ['test1'], 'emailAddress': ['test1@test.com'], 'lastName': ['test1'], 'PVFLevels': ['PVF_GUTS_3'], 'username': ['test1'], 'firmId': ['905877'], 'metadata': {'user_type': "Test firm id 3"}}
        mock_auth.get_attributes.return_value = user
        res = self.app.post('/bloomberg/login', method='POST', content_type='multipart/form-data', data={'RelayState': redirect_url})
        msg = generate_bsso_account_notification(user)
        # Verify successful result: An account for user has been auto-generated using information from BSSO. Please check their user type. (adminbssonotification.html)
        assert "check" in msg['body']
        assert res.status_code == 302, res.status_code
    
    @with_context
    @patch('pybossa.view.bloomberg.OneLogin_Saml2_Auth', autospec=True)
    def test_bsso_auto_account_warning(self, mock_two_login):
        redirect_url = 'http://localhost'
        mock_auth = MagicMock()
        mock_auth.get_errors.return_value = False
        mock_auth.process_response.return_value = None
        mock_auth.is_authenticated = True 
        mock_two_login.return_value = mock_auth
        user = {'firstName': ['test2'], 'emailAddress': ['test2@test.com'], 'lastName': ['test2'], 'username': ['test2'], 'firmId': ['0000000']}
        mock_auth.get_attributes.return_value = user
        res = self.app.post('/bloomberg/login', method='POST', content_type='multipart/form-data', data={'RelayState': redirect_url})
        msg = generate_bsso_account_notification(user)
        # Verify successfuly result with a warning: This firm id is not on the list of recognized firms. Please ensure this is a valid user of brand. (adminbssowarning.html)
        assert "valid" in msg['body']
        assert res.status_code == 302, res.status_code

    @with_context
    @patch('pybossa.view.account.generate_bsso_account_notification', autospec=True)
    def test_bsso_msg_generation(self, mock_bsso_alert):
        mock_alert = MagicMock() 
        mock_alert.body = None
        mock_alert.html = None
        mock_bsso_alert = mock_alert
        user = {'firstName': ['test2'], 'emailAddress': ['test2@test.com'], 'lastName': ['test2'], 'PVFLevels': ['PVF_GUTS_3'], 'username': ['test2'], 'firmId': ['000000'] }
        assert generate_bsso_account_notification(user) != None

    @with_context
    def test_get_s3_bucket_name_found(self):
        result1 = get_s3_bucket_name('https://www.s3.amazonaws.com/test')
        result2 = get_s3_bucket_name('https://s3.amazonaws.com/test')
        result3 = get_s3_bucket_name('https://none.com/test')

        assert result1 != None
        assert len(result1) > 0

        assert result2 != None
        assert len(result2) > 0

        assert result3 == None
