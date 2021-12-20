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

import json
from test import Test, with_context, FakeResponse
from test.factories import UserFactory
from pybossa.jobs import delete_account
from pybossa.core import user_repo
from unittest.mock import patch
from flask import current_app

@patch('pybossa.jobs.mail')
@patch('pybossa.jobs.Message')
class TestDeleteAccount(Test):

    @with_context
    @patch('requests.delete')
    def test_send_mail_creates_message_mailchimp_error(self, mailchimp, Message, mail):
        with patch.dict(self.flask_app.config, {'MAILCHIMP_API_KEY': 'k-3',
                                                'MAILCHIMP_LIST_ID': 1}):
            user = UserFactory.create()
            user_id = user.id
            brand = 'PYBOSSA'
            subject = '[%s]: Your account has been deleted' % brand
            body = """Hi,\n Your account and personal data has been deleted from %s.""" % brand
            body += '\nWe could not delete your Mailchimp account, please contact us to fix this issue.'

            admin_addr = 'admin@pybossa.com'
            recipients = [user.email_addr] + current_app.config.get('ADMINS', [])
            mail_dict = dict(recipients=recipients,
                             subject=subject,
                             body=body,
                             bcc=[admin_addr])

            user_old = user.dictize()
            delete_account(user.id, 'admin@pybossa.com')
            Message.assert_called_once_with(**mail_dict)
            mail.send.assert_called_once_with(Message())
            user_new = user_repo.get(user_id)
            assert user_new.name != user_old['name']
            assert user_new.fullname != user_old['fullname']
            assert user_new.email_addr != user_old['email_addr']
            assert not user_new.info
            assert not user_new.user_pref

    @with_context
    @patch('requests.delete')
    def test_send_mail_creates_message_mailchimp_ok(self, mailchimp, Message, mail):
        with patch.dict(self.flask_app.config, {'MAILCHIMP_API_KEY': 'k-3',
                                                'MAILCHIMP_LIST_ID': 1}):
            user = UserFactory.create()
            user_id = user.id
            brand = 'PYBOSSA'
            subject = '[%s]: Your account has been deleted' % brand
            body = """Hi,\n Your account and personal data has been deleted from %s.""" % brand

            admin_addr = 'admin@pybossa.com'
            recipients = [user.email_addr] + current_app.config.get('ADMINS', [])
            mail_dict = dict(recipients=recipients,
                             subject=subject,
                             body=body,
                             bcc=[admin_addr])

            user_old = user.dictize()
            mailchimp.side_effect = [FakeResponse(text=json.dumps(dict(status=204)),
                                                 json=lambda : '',
                                               status_code=204)]
            delete_account(user.id, admin_addr)
            Message.assert_called_once_with(**mail_dict)
            mail.send.assert_called_once_with(Message())
            user_new = user_repo.get(user_id)
            assert user_new.name != user_old['name']
            assert user_new.fullname != user_old['fullname']
            assert user_new.email_addr != user_old['email_addr']
            assert not user_new.info
            assert not user_new.user_pref

    @with_context
    @patch('requests.delete')
    def test_send_mail_creates_message_mailchimp_disquss(self, mailchimp, Message, mail):
        with patch.dict(self.flask_app.config, {'MAILCHIMP_API_KEY': 'k-3',
                                                'MAILCHIMP_LIST_ID': 1,
                                                'DISQUS_SECRET_KEY': 'key'}):
            user = UserFactory.create()
            user_id = user.id
            brand = 'PYBOSSA'
            subject = '[%s]: Your account has been deleted' % brand
            body = """Hi,\n Your account and personal data has been deleted from %s.""" % brand
            body += '\nDisqus does not provide an API method to delete your account. You will have to do it by hand yourself in the disqus.com site.'

            admin_addr = 'admin@pybossa.com'
            recipients = [user.email_addr] + current_app.config.get('ADMINS', [])
            mail_dict = dict(recipients=recipients,
                             subject=subject,
                             body=body,
                             bcc=[admin_addr])

            user_old = user.dictize()
            mailchimp.side_effect = [FakeResponse(text=json.dumps(dict(status=204)),
                                                 json=lambda : '',
                                               status_code=204)]
            delete_account(user.id, admin_addr)
            Message.assert_called_once_with(**mail_dict)
            mail.send.assert_called_once_with(Message())
            user_new = user_repo.get(user_id)
            assert user_new.name != user_old['name']
            assert user_new.fullname != user_old['fullname']
            assert user_new.email_addr != user_old['email_addr']
            assert not user_new.info
            assert not user_new.user_pref
