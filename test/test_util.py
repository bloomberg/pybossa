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
import base64
import calendar
import csv
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from flask_wtf import FlaskForm as Form
from nose.tools import nottest, assert_raises

import pybossa.util as util
from pybossa.importers import BulkImportException
from pybossa.importers.csv import BulkTaskCSVImport
from test import with_context, Test, with_request_context
from test.factories import UserFactory
from pybossa.model.user import User
from pybossa.model.project import Project
from unittest.mock import Mock
from werkzeug.exceptions import Forbidden
from pybossa.util import admin_or_project_owner


def myjsonify(data):
    return data


def myrender(template, **data):
    return template, data


class TestPybossaUtil(Test):

    # TODO: test this decorator in a more unitary way. The following tests have
    # been moved to test_api_common.py
    # def test_jsonpify(self):
    #     """Test jsonpify decorator works."""
    #     res = self.app.get('/api/app/1?callback=mycallback')
    #     err_msg = "mycallback should be included in the response"
    #     assert "mycallback" in res.data, err_msg
    #     err_msg = "Status code should be 200"
    #     assert res.status_code == 200, err_msg

    @with_context
    @patch('pybossa.util.hmac.HMAC')
    @patch('pybossa.util.base64.b64encode')
    def test_disqus_sso_payload_auth_user(self, mock_b64encode, mock_hmac):
        """Test Disqus SSO payload auth works."""
        user = UserFactory.create()

        DISQUS_PUBLIC_KEY = 'public'
        DISQUS_SECRET_KEY = 'secret'
        patch_dict = {'DISQUS_PUBLIC_KEY': DISQUS_PUBLIC_KEY,
                      'DISQUS_SECRET_KEY': DISQUS_SECRET_KEY}
        data = json.dumps({'id': user.id,
                           'username': user.name,
                           'email': user.email_addr})

        mock_b64encode.return_value = data

        with patch.dict(self.flask_app.config, patch_dict):
            message, timestamp, sig, pub_key = util.get_disqus_sso_payload(user)
            mock_b64encode.assert_called_with(data.encode())
            tmp = '{} {}'.format(data, timestamp)
            mock_hmac.assert_called_with(DISQUS_SECRET_KEY.encode(), tmp.encode(),
                                         hashlib.sha1)
            assert timestamp
            assert sig
            assert pub_key == DISQUS_PUBLIC_KEY

    @with_context
    @patch('pybossa.util.hmac.HMAC')
    @patch('pybossa.util.base64.b64encode')
    def test_disqus_sso_payload_auth_user_no_keys(self, mock_b64encode, mock_hmac):
        """Test Disqus SSO without keys works."""
        user = UserFactory.create()
        message, timestamp, sig, pub_key = util.get_disqus_sso_payload(user)
        assert message is None
        assert timestamp is None
        assert sig is None
        assert pub_key is None


    @with_context
    @patch('pybossa.util.hmac.HMAC')
    @patch('pybossa.util.base64.b64encode')
    def test_disqus_sso_payload_anon_user(self, mock_b64encode, mock_hmac):
        """Test Disqus SSO payload anon works."""

        DISQUS_PUBLIC_KEY = 'public'
        DISQUS_SECRET_KEY = 'secret'
        patch_dict = {'DISQUS_PUBLIC_KEY': DISQUS_PUBLIC_KEY,
                      'DISQUS_SECRET_KEY': DISQUS_SECRET_KEY}

        data = json.dumps({})

        mock_b64encode.return_value = data

        with patch.dict(self.flask_app.config, patch_dict):
            message, timestamp, sig, pub_key = util.get_disqus_sso_payload(None)
            mock_b64encode.assert_called_with(data.encode())
            tmp = '{} {}'.format(data, timestamp)
            mock_hmac.assert_called_with(DISQUS_SECRET_KEY.encode(), tmp.encode(),
                                         hashlib.sha1)
            assert timestamp
            assert sig
            assert pub_key == DISQUS_PUBLIC_KEY


    @with_context
    def test_disqus_sso_payload_anon_user_no_keys(self):
        """Test Disqus SSO without keys anon works."""
        message, timestamp, sig, pub_key = util.get_disqus_sso_payload(None)
        assert message is None
        assert timestamp is None
        assert sig is None
        assert pub_key is None


    @patch('pybossa.util.get_flashed_messages')
    def test_last_flashed_messages(self, mockflash):
        """Test last_flashed_message returns the last one."""
        messages = ['foo', 'bar']
        mockflash.return_value = messages
        msg = util.last_flashed_message()
        err_msg = "It should be the last message"
        assert msg == messages[-1], err_msg

    @patch('pybossa.util.get_flashed_messages')
    def test_last_flashed_messages_none(self, mockflash):
        """Test last_flashed_message returns the none."""
        messages = []
        mockflash.return_value = messages
        msg = util.last_flashed_message()
        err_msg = "It should be None"
        assert msg is None, err_msg

    @with_request_context
    @patch('pybossa.util.request')
    @patch('pybossa.util.render_template')
    @patch('pybossa.util.jsonify')
    @patch('pybossa.util.last_flashed_message')
    def test_handle_content_type_json(self, mocklast, mockjsonify,
                                      mockrender, mockrequest):
        fake_d = {'Content-Type': 'application/json'}

        # mockrequest is AsyncMock; to avoid request.headers.get('Content-Type')
        # to have "AsyncMockMixin._execute_mock_call' was never awaited"
        # exception, just using the following line
        mockrequest.headers = fake_d

        mockjsonify.side_effect = myjsonify
        res = util.handle_content_type(dict(template='example.html'))
        err_msg = "template key should exist"
        assert res.get('template') == 'example.html', err_msg
        err_msg = "jsonify should be called"
        assert mockjsonify.called, err_msg

    @with_request_context
    @patch('pybossa.util.request')
    @patch('pybossa.util.render_template')
    @patch('pybossa.util.jsonify')
    @patch('pybossa.util.last_flashed_message')
    def test_handle_content_type_json_error(self, mocklast, mockjsonify,
                                            mockrender, mockrequest):
        fake_d = {'Content-Type': 'application/json'}
        mockrequest.headers = fake_d
        mockjsonify.side_effect = myjsonify
        res, code = util.handle_content_type(
                                             dict(
                                                 template='example.html',
                                                 code=404,
                                                 description="Not found"))
        err_msg = "template key should exist"
        assert res.get('template') == 'example.html', err_msg
        err_msg = "jsonify should be called"
        assert mockjsonify.called, err_msg
        err_msg = "Error code should exist"
        assert res.get('code') == 404, err_msg
        assert code == 404, err_msg
        err_msg = "Error description should exist"
        assert res.get('description') is not None, err_msg

    @with_request_context
    @patch('pybossa.util.request')
    @patch('pybossa.util.render_template')
    @patch('pybossa.util.jsonify')
    @patch('pybossa.util.generate_csrf')
    @patch('pybossa.util.last_flashed_message')
    def test_handle_content_type_json_form(self, mocklast, mockcsrf,
                                           mockjsonify, mockrender,
                                           mockrequest):
        fake_d = {'Content-Type': 'application/json'}
        mockrequest.headers = fake_d
        mockjsonify.side_effect = myjsonify
        mockcsrf.return_value = "yourcsrf"
        form = MagicMock(spec=Form, data=dict(foo=1), errors=None)
        res = util.handle_content_type(dict(template='example.html',
                                            form=form))
        err_msg = "template key should exist"
        assert res.get('template') == 'example.html', err_msg
        err_msg = "jsonify should be called"
        assert mockjsonify.called, err_msg
        err_msg = "Form should exist"
        assert res.get('form'), err_msg
        err_msg = "Form should have a csrf key/value"
        assert res.get('form').get('csrf') == 'yourcsrf', err_msg
        err_msg = "There should be the keys of the form"
        keys = ['foo', 'errors', 'csrf']
        assert list(res.get('form').keys()).sort() == keys.sort(), err_msg

    @with_request_context
    @patch('pybossa.util.request')
    @patch('pybossa.util.render_template')
    @patch('pybossa.util.jsonify')
    @patch('pybossa.util.last_flashed_message')
    def test_handle_content_type_json_pagination(self, mocklast, mockjsonify,
                                                 mockrender, mockrequest):
        fake_d = {'Content-Type': 'application/json'}
        mockrequest.headers = fake_d
        mockjsonify.side_effect = myjsonify
        pagination = util.Pagination(page=1, per_page=5, total_count=10)
        res = util.handle_content_type(dict(template='example.html',
                                            pagination=pagination))
        err_msg = "template key should exist"
        assert res.get('template') == 'example.html', err_msg
        err_msg = "jsonify should be called"
        assert mockjsonify.called, err_msg
        err_msg = "Pagination should exist"
        assert res.get('pagination') is not None, err_msg
        assert res.get('pagination') == pagination.to_json(), err_msg

    @with_request_context
    @patch('pybossa.util.request')
    @patch('pybossa.util.render_template')
    @patch('pybossa.util.jsonify')
    def test_handle_content_type_html(self, mockjsonify,
                                      mockrender, mockrequest):
        fake_d = {'Content-Type': 'text/html'}
        mockrequest.headers = fake_d
        mockjsonify.side_effect = myjsonify
        mockrender.side_effect = myrender
        pagination = util.Pagination(page=1, per_page=5, total_count=10)
        template, data = util.handle_content_type(dict(template='example.html',
                                                       pagination=pagination))
        err_msg = "Template should be rendered"
        assert template == 'example.html', err_msg
        err_msg = "Template key should not exist"
        assert data.get('template') is None, err_msg
        err_msg = "jsonify should not be called"
        assert mockjsonify.called is False, err_msg
        err_msg = "render_template should be called"
        assert mockrender.called is True, err_msg

    @with_request_context
    @patch('pybossa.util.request')
    @patch('pybossa.util.render_template')
    @patch('pybossa.util.jsonify')
    def test_handle_content_type_html_error(self, mockjsonify,
                                            mockrender, mockrequest):
        fake_d = {'Content-Type': 'text/html'}
        mockrequest.headers = fake_d
        mockjsonify.side_effect = myjsonify
        mockrender.side_effect = myrender
        template, code = util.handle_content_type(dict(template='example.html',
                                                       code=404))
        data = template[1]
        template = template[0]
        err_msg = "Template should be rendered"
        assert template == 'example.html', err_msg
        err_msg = "Template key should not exist"
        assert data.get('template') is None, err_msg
        err_msg = "jsonify should not be called"
        assert mockjsonify.called is False, err_msg
        err_msg = "render_template should be called"
        assert mockrender.called is True, err_msg
        err_msg = "There should be an error"
        assert code == 404, err_msg
        err_msg = "There should not be code key"
        assert data.get('code') is None, err_msg

    @with_context
    def test_is_own_url(self):
        assert util.is_own_url('/home')
        assert util.is_own_url('{}/home'.format(self.flask_app.config.get('SERVER_NAME')))
        assert util.is_own_url('https://{}/home'.format(self.flask_app.config.get('SERVER_NAME')))
        assert util.is_own_url(util.url_for('home.home'))
        url = util.url_for('home.home', _external=True)
        assert util.is_own_url(url), url
        assert not util.is_own_url('https://google.com')
        assert util.is_own_url(None)
        assert util.is_own_url('')

    @with_request_context
    @patch('pybossa.util.request')
    @patch('pybossa.util.render_template')
    @patch('pybossa.util.jsonify')
    @patch('pybossa.util.last_flashed_message')
    def test_redirect_content_type_json(
        self,
        mocklast,
        mockjsonify,
        mockrender,
     mockrequest):
        fake_d = {'Content-Type': 'application/json'}
        mockrequest.headers = fake_d
        mockjsonify.side_effect = myjsonify
        res = util.redirect_content_type('http://next.uri')
        err_msg = "next URI is wrong in redirection"
        assert res.get('next') == 'http://next.uri', err_msg
        err_msg = "jsonify should be called"
        assert mockjsonify.called, err_msg

    @with_request_context
    @patch('pybossa.util.request')
    @patch('pybossa.util.render_template')
    @patch('pybossa.util.jsonify')
    @patch('pybossa.util.last_flashed_message')
    def test_redirect_content_type_json_message(
            self, mocklast, mockjsonify, mockrender, mockrequest):
        mocklast.return_value = None
        fake_d = {'Content-Type': 'application/json'}
        mockrequest.headers = fake_d
        mockjsonify.side_effect = myjsonify
        res = util.redirect_content_type('http://next.uri', status='hallo123')
        err_msg = "next URI is wrong in redirction"
        assert res.get('next') == 'http://next.uri', err_msg
        err_msg = "jsonify should be called"
        assert mockjsonify.called, err_msg
        err_msg = "status should exist"
        assert res.get('status') == 'hallo123', err_msg

    @with_request_context
    @patch('pybossa.util.request')
    @patch('pybossa.util.render_template')
    @patch('pybossa.util.jsonify')
    def test_redirect_content_type_json_html(
            self, mockjsonify, mockrender, mockrequest):
        fake_d = {'Content-Type': 'text/html'}
        mockrequest.headers = fake_d
        mockjsonify.side_effect = myjsonify
        res = util.redirect_content_type('/')
        err_msg = "redirect 302 should be the response"
        assert res.status_code == 302, err_msg
        err_msg = "redirect to / should be done"
        assert res.location == "/", err_msg
        err_msg = "jsonify should not be called"
        assert mockjsonify.called is False, err_msg

    @with_context
    @patch('pybossa.util.url_for')
    def test_url_for_app_type_spa(self, mock_url_for):
        """Test that the correct SPA URL is returned"""
        spa_name = 'http://local.com'
        fake_endpoint = '/example'
        mock_url_for.return_value = fake_endpoint
        with patch.dict(self.flask_app.config, {'SPA_SERVER_NAME': spa_name}):
            spa_url = util.url_for_app_type('home.home')
            expected = spa_name + fake_endpoint
            assert spa_url == expected, spa_url

    @with_context
    @patch('pybossa.util.url_for')
    @patch('pybossa.util.hash_last_flash_message')
    def test_url_for_app_type_spa_with_hashed_flash(self, mock_hash_last_flash, mock_url_for):
        """Test that the hashed flash is returned with the SPA URL"""
        flash = 'foo'
        endpoint = 'bar'
        mock_hash_last_flash.return_value = flash
        with patch.dict(self.flask_app.config, {'SPA_SERVER_NAME': 'example.com'}):
            util.url_for_app_type(endpoint, _hash_last_flash=True)
            err = "Hashed flash should be included"
            mock_url_for.assert_called_with(endpoint, flash=flash), err

    @with_context
    @patch('pybossa.util.url_for')
    def test_url_for_app_type_mvc(self, mock_url_for):
        """Test that the correct MVC URL is returned"""
        fake_endpoint = '/example'
        mock_url_for.return_value = fake_endpoint
        spa_url = util.url_for_app_type('home.home')
        assert spa_url == fake_endpoint, spa_url

    @with_context
    @patch('pybossa.util.url_for')
    @patch('pybossa.util.hash_last_flash_message')
    def test_url_for_app_type_mvc_with_hashed_flash(self, mock_hash_last_flash, mock_url_for):
        """Test that the hashed flash is not returned with the MVC URL"""
        endpoint = 'bar'
        util.url_for_app_type(endpoint, _hash_last_flash=True)
        mock_url_for.assert_called_with(endpoint)
        err = "Hashed flash should not be called"
        assert not mock_hash_last_flash.called, err

    @patch('pybossa.util.last_flashed_message')
    def test_last_flashed_message_hashed(self, last_flash):
        """Test the last flash message is hashed."""
        message_and_status = [ 'foo', 'bar' ]
        last_flash.return_value = message_and_status
        tmp = json.dumps({
            'flash': message_and_status[1],
            'status': message_and_status[0]
        })
        expected = base64.b64encode(tmp.encode())
        hashed_flash = util.hash_last_flash_message()
        assert hashed_flash == expected

    def test_parse_date_string(self):
        """Test parse_date_string works. """
        source = "not a date"
        assert util.parse_date_string(source) == source

    def test_fuzzyboolean(self):
        """Test fuzzyboolean works. """
        value = None
        assert_raises(ValueError, util.fuzzyboolean, value)

        value = '6'
        assert_raises(ValueError, util.fuzzyboolean, value)

    def test_pretty_date(self):
        """Test pretty_date works."""
        now = datetime.now()
        pd = util.pretty_date()
        assert pd == "just now", pd

        pd = util.pretty_date(now.isoformat())
        assert pd == "just now", pd

        pd = util.pretty_date(calendar.timegm(time.gmtime()))
        assert pd == "just now", pd

        d = now + timedelta(days=10)
        pd = util.pretty_date(d.isoformat())
        assert pd == '', pd

        d = now - timedelta(seconds=10)
        pd = util.pretty_date(d.isoformat())
        assert pd == '10 seconds ago', pd

        d = now - timedelta(minutes=1)
        pd = util.pretty_date(d.isoformat())
        assert pd == 'a minute ago', pd

        d = now - timedelta(minutes=2)
        pd = util.pretty_date(d.isoformat())
        assert pd == '2 minutes ago', pd

        d = now - timedelta(hours=1)
        pd = util.pretty_date(d.isoformat())
        assert pd == 'an hour ago', pd

        d = now - timedelta(hours=5)
        pd = util.pretty_date(d.isoformat())
        assert pd == '5 hours ago', pd

        d = now - timedelta(days=1)
        pd = util.pretty_date(d.isoformat())
        assert pd == 'Yesterday', pd

        d = now - timedelta(days=5)
        pd = util.pretty_date(d.isoformat())
        assert pd == '5 days ago', pd

        d = now - timedelta(weeks=1)
        pd = util.pretty_date(d.isoformat())
        assert pd == '1 weeks ago', pd

        d = now - timedelta(days=32)
        pd = util.pretty_date(d.isoformat())
        assert pd == '1 month ago', pd

        d = now - timedelta(days=62)
        pd = util.pretty_date(d.isoformat())
        assert pd == '2 months ago', pd

        d = now - timedelta(days=366)
        pd = util.pretty_date(d.isoformat())
        assert pd == '1 year ago', pd

        d = now - timedelta(days=766)
        pd = util.pretty_date(d.isoformat())
        assert pd == '2 years ago', pd

    def test_pagination(self):
        """Test Class Pagination works."""
        page = 1
        per_page = 5
        total_count = 10
        p = util.Pagination(page, per_page, total_count)
        assert p.page == page, p.page
        assert p.per_page == per_page, p.per_page
        assert p.total_count == total_count, p.total_count

        err_msg = "It should return two pages"
        assert p.pages == 2, err_msg
        p.total_count = 7
        assert p.pages == 2, err_msg
        p.page = 1
        assert p.curr_page_count == 5, "rows on curr page to be 5"
        p.page = 2
        assert p.curr_page_count == 2, "rows on curr page to be 2"
        p.page = 1000
        assert p.curr_page_count == 0, "rows on curr page to be 0"

        p.total_count = 10
        p.page = 2
        assert p.curr_page_count == 5, "rows on curr page to be 5"

        p.page = 1
        err_msg = "It should return False"
        assert p.has_prev is False, err_msg
        err_msg = "It should return True"
        assert p.has_next is True, err_msg
        p.page = 2
        assert p.has_prev is True, err_msg
        err_msg = "It should return False"
        assert p.has_next is False, err_msg

        for i in p.iter_pages():
            err_msg = "It should return the page: %s" % page
            assert i == page, err_msg
            page += 1

        err_msg = "It should return JSON"
        expected = dict(page=page-1,
                        per_page=per_page,
                        total=total_count,
                        next=False,
                        prev=True)
        assert expected == p.to_json(), err_msg

    def test_unicode_csv_reader(self):
        """Test unicode_csv_reader works."""
        fake_csv = ['one, two, three']
        err_msg = "Each cell should be encoded as Unicode"
        for row in util.unicode_csv_reader(fake_csv):
            for item in row:
                assert isinstance(item, str), err_msg

    @with_context
    def csv_validate_required_fields(self, config, callback):
        """Test validate_required_fields against csv data
        with data_access, data_source_id, data_owner."""
        with patch.dict(self.flask_app.config, config):
            fake_csv = ('line,data_access,data_source_id,data_owner\n'
                'test,"[""L4""]",123.0,456\n'
                'test,"[""L4""]",123.6,456\n'
                'test,"[""L4""]",abc,456\n'
                'test,"[""L4""]",,456\n'
                'test,"[""L4""]",123,456.0\n'
                'test,"[""L4""]",123,456.6\n'
                'test,"[""L4""]",123,abc\n'
                'test,"[""L4""]",123,\n'
                'test,,123,456\n'
                'test,"[""L4""]",123,456')
            csvreader = csv.reader(fake_csv.splitlines())
            csviterator = iter(csvreader)

            for index, row in enumerate(csviterator):
                if index == 0:
                    # Read csv header.
                    headers = row
                else:
                    # Read csv data and check required fields.
                    fvals = {headers[idx]: cell for idx, cell in enumerate(row)}
                    invalid_fields = util.validate_required_fields(fvals)

                    # Allow client to assert on result.
                    callback(index, invalid_fields)

    @with_request_context
    def csv_validate_required_fields_case_insensitive(self):
        """Test validate_required_fields against csv data
        with DATA_SOURCE_ID, DATA_OWNER in uppercase."""
        config = {'TASK_REQUIRED_FIELDS': {
            'data_access': {'val': None, 'check_val': False},
            'data_owner': {'val': None, 'check_val': False},
            'data_source_id': {'val': None, 'check_val': False}}}

        with patch.dict(self.flask_app.config, config):
            cs = BulkTaskCSVImport(None)

            # Check upper-case required fields.
            cs._headers = ['sentence', 'DATA_ACCESS', 'DATA_SOURCE_ID', 'DATA_OWNER']
            cs._check_required_headers()

            # Check lower-case required fields.
            cs._headers = ['sentence', 'data_access', 'data_source_id', 'data_owner']
            cs._check_required_headers()

            # Check mixed-case required fields.
            cs._headers = ['sentence', 'Data_Access', 'Data_Source_Id', 'Data_Owner']
            cs._check_required_headers()

            # Check missing required field DATA_SOURCE_ID. Verify exception is raised.
            cs._headers = ['sentence', 'data_access', 'Data_Owner']
            assert_raises(BulkImportException, cs._check_required_headers)

            # Check missing required field DATA_OWNER. Verify exception is raised.
            cs._headers = ['sentence', 'data_access', 'data_source_id']
            assert_raises(BulkImportException, cs._check_required_headers)

            # Check missing required field DATA_ACCESS. Verify exception is raised.
            cs._headers = ['sentence', 'data_owner', 'data_source_id']
            assert_raises(BulkImportException, cs._check_required_headers)

    @with_context
    def test_csv_validate_required_fields_accept_string(self):
        """Test validate_required_fields ignore integer validation."""
        config = {'TASK_REQUIRED_FIELDS': {
            'data_access': {'val': None, 'check_val': False},
            'data_owner': {'val': None, 'check_val': False},
            'data_source_id': {'val': None, 'check_val': False}}}

        def validate(index, invalid_fields):
            if index == 4:
                # data_source_id must have a value.
                assert len(invalid_fields) == 1
                assert 'data_source_id' in invalid_fields
            elif index == 8:
                # data_owner must have a value.
                assert len(invalid_fields) == 1
                assert 'data_owner' in invalid_fields
            elif index == 9:
                # data_access must have a value.
                assert len(invalid_fields) == 1
                assert 'data_access' in invalid_fields
            else:
                # data_source_id, data_owner, data_access are valid.
                assert len(invalid_fields) == 0

        # Validate csv data.
        self.csv_validate_required_fields(config, validate)

    @with_context
    def test_csv_validate_required_fields_accept_integer(self):
        """Test validate_required_fields include integer validation."""
        config = {'TASK_REQUIRED_FIELDS': {
            'data_access': {'val': None, 'check_val': False},
            'data_owner': {'val': None, 'check_val': False, 'require_int': True},
            'data_source_id': {'val': None, 'check_val': False, 'require_int': True}}}

        def validate(index, invalid_fields):
            if index < 5:
                # data_source_id must be an integer.
                assert len(invalid_fields) == 1
                assert 'data_source_id' in invalid_fields
            elif index < 9:
                # data_owner must be an integer.
                assert len(invalid_fields) == 1
                assert 'data_owner' in invalid_fields
            elif index == 9:
                # data_access must have a value.
                assert len(invalid_fields) == 1
                assert 'data_access' in invalid_fields
            else:
                # data_source_id, data_owner, data_access are valid.
                assert len(invalid_fields) == 0

        # Validate csv data.
        self.csv_validate_required_fields(config, validate)

    def test_is_int(self):
        """Test is_int method."""
        assert util.is_int(1) is True
        assert util.is_int('1') is True
        assert util.is_int(1.0) is True
        assert util.is_int('1.0') is True
        assert util.is_int(-2147483648) is True
        assert util.is_int(2147483647) is True
        assert util.is_int(1.1) is False
        assert util.is_int('1.1') is False
        assert util.is_int('a') is False
        assert util.is_int(None) is False
        assert util.is_int(True) is False
        assert util.is_int(-2147483649) is False
        assert util.is_int(2147483648) is False

    @with_context
    def test_integer_required_cast_string(self):
        """Test importing an integer (BBDS) with validate_required_fields."""
        config = {'TASK_REQUIRED_FIELDS': {
            'data_access': {'val': None, 'check_val': False},
            'data_owner': {'val': None, 'check_val': False, 'require_int': True},
            'data_source_id': {'val': None, 'check_val': False, 'require_int': True}}}

        # While csv imports as string values, we explicitly set an integer value.
        data = {'data_access': "1", 'data_owner': 5, 'data_source_id': '2'}

        with patch.dict(self.flask_app.config, config):
            invalid_fields = util.validate_required_fields(data)
            assert len(invalid_fields) == 0

    def test_publish_channel_private(self):
        """Test publish_channel private method works."""
        sentinel = MagicMock()
        master = MagicMock()
        sentinel.master = master

        data = dict(foo='bar')
        util.publish_channel(sentinel, 'project', data,
                             type='foobar', private=True)
        channel = 'channel_private_project'
        msg = dict(type='foobar', data=data)
        master.publish.assert_called_with(channel, json.dumps(msg))

    def test_publish_channel_public(self):
        """Test publish_channel public method works."""
        sentinel = MagicMock()
        master = MagicMock()
        sentinel.master = master

        data = dict(foo='bar')
        util.publish_channel(sentinel, 'project', data,
                             type='foobar', private=False)
        channel = 'channel_public_project'
        msg = dict(type='foobar', data=data)
        master.publish.assert_called_with(channel, json.dumps(msg))

    @with_context
    def test_mail_with_enabled_users_returns_false(self):
        message = {}
        response = util.mail_with_enabled_users(message)
        assert not response, "Empty recipient, bcc list. No user should be present."

        message = {"junk": "xyz"}
        response = util.mail_with_enabled_users(message)
        assert not response, "Message without recipients, bcc to not return user."

    @with_context
    def test_mail_with_enabled_users_returns_true(self):
        tyrion = UserFactory.create(email_addr='tyrion@got.com', enabled=True)
        theon = UserFactory.create(email_addr='reek@got.com', enabled=False)
        robb = UserFactory.create(email_addr='robb@got.com', enabled=True)
        ned = UserFactory.create(email_addr='ned@got.com', enabled=True)
        message = {
            "recipients": [tyrion.email_addr, theon.email_addr],
            "bcc": [ned.email_addr]
        }
        response = util.mail_with_enabled_users(message)
        assert response, "recipent & bcc enabled users list to return True."
        # theon being disabled should be dropped from recipients list
        assert theon.email_addr not in message["recipients"], "Disabled users should be removed from email list"
        assert ned.email_addr in message["bcc"] and robb.email_addr not in message["bcc"], "Filtered enabled users not to be part of email list"
        assert tyrion.email_addr in message["recipients"], "Enabled user to be part of recipients list"

    def test_check_annex_response(self):
        valid_value = {"oa": [{"body": [{"@type": "bb:Transparency.Text.Text", "transparency": [{"selector": {"end": 2142, "@type": "oa:DataPositionSelector", "start": 2136}}]}],
                               "target": [{"selector": {"id": "829dd359-d18c-fead-d4f500000000000b", "@type": "bb:OdfElementSelector"}}]},
                              {"body": [{"@type": "reportYear", "value": "2022"}], "target": [{}]}],
                       "odf": {"office:document": {"office:body": {"office:text": [{"text:p": {"xml:id": "829dd359-d18c-fead-d4f500000000000b", "office:string-value": "ANNUAL"}}]}, "office:meta": {}}},
                       "version": "1.0",
                       "source-uri": "https://s3.amazonaws.com/cf-s3uploads/tjb/comppres/0000764478-19-000009.html?task-signature=undefined"}
        response = util.check_annex_response(valid_value)
        assert response == valid_value

        valid_value = {"annex1":
                           {"annex2":
                                {"oa": [{"body": [{"@type": "bb:Transparency.Text.Text",
                                         "transparency": [{"selector": {
                                             "end": 2142,
                                             "@type": "oa:DataPositionSelector",
                                             "start": 2136}}]}],
                               "target": [{"selector": {
                                   "id": "829dd359-d18c-fead-d4f500000000000b",
                                   "@type": "bb:OdfElementSelector"}}]},
                              {"body": [
                                  {"@type": "reportYear", "value": "2022"}],
                               "target": [{}]}],
                       "odf": {"office:document": {"office:body": {
                           "office:text": [{"text:p": {
                               "xml:id": "829dd359-d18c-fead-d4f500000000000b",
                               "office:string-value": "ANNUAL"}}]},
                                                   "office:meta": {}}},
                       "version": "1.0",
                       "source-uri": "https://s3.amazonaws.com/cf-s3uploads/tjb/comppres/0000764478-19-000009.html?task-signature=undefined"}
                            }
                       }
        response = util.check_annex_response(valid_value)
        assert response == valid_value['annex1']['annex2']

        invalid_value = {"odf": {"office:document": {"office:body": {
                           "office:text": [{"text:p": {
                               "xml:id": "829dd359-d18c-fead-d4f500000000000b",
                               "office:string-value": "ANNUAL"}}]},
                                                   "office:meta": {}}},
                       "version": "1.0",
                       "source-uri": "https://s3.amazonaws.com/cf-s3uploads/tjb/comppres/0000764478-19-000009.html?task-signature=undefined"}
        response = util.check_annex_response(invalid_value)
        assert response is None

    def test_process_annex_load(self):
        annex_shell_tp_code = """function loadAnnex(task) {
            const shell = document.getElementById("shell-container");
            // this is the document field in your task.
            shell.setAttribute("gigwork:doc-url", task.info.document__upload_url);
            // this is the annotation field in your task
            //shell.setAttribute("gigwork:annotation-url", task.info.annotation__upload_url);
            // you need the task signature to load encrypted files
            shell.setAttribute("gigwork:task-sig", task.signature);
            // you should customize this for users.
            console.log('483902jg')
            console.log(task)
            shell.setAttribute("user", "skorala");
            // hash comes from gigwork task. for example, task.info.annex_hash.
            shell.setAttribute("hash", "8A0FAE8EC1D64DF7539210CF9658C1C3");
            shell.addEventListener("urn:bloomberg:annex:event:instance-ready", () => {
              console.log("ready to start");
              // add any code you need to run when Annex is ready.
            });
            shell.addEventListener("urn:bloomberg:annex:event:instance-error", () => {
              document.getElementById("skipButton").classList.toggle('invisible')
              document.getElementById("submitButton").classList.toggle('invisible')
              // add any code you need to run when Annex is ready.
            });
          }
        </script>"""
        odfoa_data = {"a": 1}
        tp_code = util.process_annex_load(annex_shell_tp_code, odfoa_data)
        assert "shell.addEventListener('urn:bloomberg:annex:event:instance-success', () => {" in tp_code
        assert f"shell.internalModel.activeTab().loadAnnotationFromJson('{json.dumps(odfoa_data)}')" in tp_code

        annex_js_tp_code = """async function doPybossa(pybossa, gigConfig) {
            document.getElementById('collapse-guidelines').classList.remove('show');

            const Annex = await window.loadDocx();
            const annex = window.loadeddocx = new Annex();
            document.getElementById('annex').appendChild(annex.getDom()[0]);

            // Annex supports multiple tabs with a document in each one.
            // However, for a single document you will not see the tab or its title.
            const annexTab = annex.addTab('tab title', gigConfig.annex);
            const {getAnswer, reset} = pointAndShoot(annexTab);
            const annexModel = annexTab._internal.model;
            annexModel.isAutoFormatRowColumnEnabled(false);
            annexModel.isFillTableContentEnabled(false);

            // 'LEFT', 'RIGHT', 'TOP', 'BOTTOM'
            annexModel.annotatorPosition('BOTTOM');
            annexModel.isThumbnailBarPinned(false);

            pybossa.beforeSubmit(beforePybossaSubmitTask);
            pybossa.beforePresent(beforePybossaPresentTask);
         //   pybossa.run(gigConfig.project.name);

            function beforePybossaSubmitTask(answer, task) {
                // Return the actual answer you want to submit.
                // We are ignoring the answer parameter provided by the framework
                // and handling the entire answer construction ourselves.
                return getAnswer(task);
            }

            function beforePybossaPresentTask(task) {
                reset();
                $('#field1').prop('disabled', false);
                console.log('beforePybossaPresentTask, task.info=', JSON.stringify(task.info));
                return annexTab.loadDocumentLite(
                  task.info.doc_url + '?t=' + Date.now(), {}
                );
            }
          }
        </script>"""
        tp_code = util.process_annex_load(annex_js_tp_code, odfoa_data)
        assert f".then(() => annexTab.loadAnnotationFromJson('{json.dumps(odfoa_data)}'))" in tp_code

        annex_js_tp_code = """pybossa.presentTask(function (task, deferred) {
        console.log('pybossa:presentTask', arguments);

        if (!$.isEmptyObject(task)) {
          //var docUrl = Object.values(task.info)[2];
          var docUrl = task.info.docUrl;
          console.log('docUrl', docUrl);

          // Load document into Annex tab
          const loadDocumentPromise = () => tab.loadDocumentLite(docUrl)
          const loadOdfoaPromise = () => $.ajax({
            url: odfUrl,
            dataType: 'text'
          });

          Promise.all([
            loadDocumentPromise(),
          ]).then(([_void]) => {
            console.log('doc loaded');
          }).catch((err) => {
            console.error(err);
          });
        }"""
        tp_code = util.process_annex_load(annex_js_tp_code, odfoa_data)
        assert f".then(() => tab.loadAnnotationFromJson('{json.dumps(odfoa_data)}'))" in tp_code

        annex_js_tp_code_multiple = """function beforePybossaPresentTask(task) {
        reset();
        $('#field-1').prop('disabled', false);
        $('#field-2').prop('disabled', false);
        console.log('beforePybossaPresentTask, task.info=', JSON.stringify(task.info));
        //old
          //return annexTab.loadDocumentLite(
            //      task.info.doc_url + '?t=' + Date.now(), {}
              //  );
                            var oldlink = JSON.stringify(task.info.doc_url)

                if (typeof oldlink == "undefined"){
                    console.log('using new link')
                    return annexTab.loadDocumentLite(
                        task.info.doc_url__upload_url + '&t=' + Date.now(), {}
                         );
             }
                else {
                    console.log('using old link')
                    return annexTab.loadDocumentLite(
                    task.info.doc_url + '?t=' + Date.now(), {}
                    );
             }
            }
          }
        </script>
        """
        tp_code = util.process_annex_load(annex_js_tp_code_multiple, odfoa_data)
        assert f".then(() => annexTab.loadAnnotationFromJson('{json.dumps(odfoa_data)}'))" in tp_code
        assert tp_code.count(f".then(() => annexTab.loadAnnotationFromJson('{json.dumps(odfoa_data)}'))") == 3

    @with_context
    def test_admin_or_project_owner_raises_forbidden(self):
        """Test admin or project owner check raises forbidden for unauthorized users"""
        user = Mock(spec=User)
        project = Mock(spec=Project)

        user.is_authenticated = False
        assert_raises(Forbidden, admin_or_project_owner, user, project)

        user.is_authenticated = True
        user.admin = False
        project.owners_ids = [999]
        assert_raises(Forbidden, admin_or_project_owner, user, project)

    def test_process_tp_components(self):
        tp_code = """  <task-presenter>
            <text-input id='_kp6zwx2rs' type='text' :validations='[]' pyb-answer='freeText' initial-value='nothing special'></text-input>
            
            <div class="row">
              <div class="col-sm-3">
                <div class="form-group">
                  <dropdown-input pyb-answer='isNewData'
                    :choices='{&quot;yes&quot;:&quot;Yes&quot;,&quot;no&quot;:&quot;No&quot;}' :validations='["required"]'
                    initial-value='no'>
                  </dropdown-input>
                </div>
              </div>
            </div>
        
            <radio-group-input pyb-answer='answer' name='userAnswer'
              :choices='{&quot;Chinese&quot;:&quot;Chinese&quot;,&quot;Korean&quot;:&quot;Korean&quot;,&quot;Japanese&quot;:&quot;Japanese&quot;}'
              initial-value='Chinese' :validations='["required"]'></radio-group-input>
        
            <div id="_e9pm92ges">
              <div class="checkbox">
                      <label for="_mg59znxa7">
                          <checkbox-input :initial-value="false" id="_mg59znxa7" pyb-answer="isRelevant"></checkbox-input> Is this document relevant?
                      </label>
                </div>
            </div>
        
            <multi-select-input
              pyb-answer='subjects'
              :choices='[&quot;Math&quot;,&quot;English&quot;,&quot;Social Study&quot;,&quot;Python&quot;]'
              :validations='["required"]'
              :initial-value='[&quot;Python&quot;,&quot;English&quot;]'
          ></multi-select-input>
        </task-presenter>
        """

        user_response = {'answer': 'Japanese', 'freeText': 'This is cool', 'subjects': ['Social Study', 'English', 'Math'], 'isNewData': 'yes', 'isRelevant': False}
        result = util.process_tp_components(tp_code, user_response)

        assert """<dropdown-input :choices='{"yes":"Yes","no":"No"}' :validations='["required"]' initial-value="yes" pyb-answer="isNewData">""" in result
        assert """<radio-group-input :choices='{"Chinese":"Chinese","Korean":"Korean","Japanese":"Japanese"}' :validations='["required"]' initial-value="Japanese" name="userAnswer" pyb-answer="answer">""" in result
        assert """<checkbox-input :initial-value="false" id="_mg59znxa7" pyb-answer="isRelevant">""" in result
        assert """<multi-select-input :choices='["Math","English","Social Study","Python"]' :initial-value='["Social Study","English","Math"]' :validations='["required"]' pyb-answer="subjects">""" in result

    def test_process_table_component(self):
        tp_code = """
            <h2>6) table element</h2>
            <table-element
          :key='task.id'
          name='all_info'
          :data='[{"name":"","position":"","phoneNumber":"","emailAddress":"","physicalLocation":"","linkedIn":"","zoomInfo":"","moreInfo":""}]'
          :columns='["name","position","phoneNumber","emailAddress","physicalLocation","linkedIn","zoomInfo","moreInfo"]'
          :options='{
            "headings": {
                "name": "Name",
                "position": "Position",
                "phoneNumber": "Phone Number",
                "emailAddress": "Email Address",
                "physicalLocation": "Physical Location",
                "linkedIn": "LinkedIn Account",
                "zoomInfo": "Zoom Info",
                "moreInfo": "Additional Contact Info"
            }
        }'
          column-id='__col_id'
          :row-object='{
            "name": "",
            "position": "",
            "phoneNumber": "",
            "emailAddress": "",
            "physicalLocation": "",
            "linkedIn": "",
            "zoomInfo": "",
            "moreInfo": ""
        }'
          :enable-add-rows='true'
          :add-button-after-table='true'
          :add-button-before-table='false'
          >
            <div slot="name" slot-scope="props">
                <text-input :row="props.row" :initial-value="props.row.name" :validations='["required"]' pyb-table-answer="name"></text-input>
            </div>
        
            <div slot="position" slot-scope="props">
                <text-input :row="props.row" :initial-value="props.row.position" :validations='["required"]' pyb-table-answer="position"></text-input>
            </div>
        
            <div slot="phoneNumber" slot-scope="props">
                <text-input :row="props.row" :initial-value="props.row.phoneNumber" :validations='["required"]' pyb-table-answer="phoneNumber"></text-input>
            </div>
        
            <div slot="emailAddress" slot-scope="props">
                <text-input :row="props.row" :initial-value="props.row.emailAddress" :validations='["required"]' pyb-table-answer="emailAddress"></text-input>
            </div>
        
            <div slot="physicalLocation" slot-scope="props">
                <text-input :row="props.row" :initial-value="props.row.physicalLocation" :validations='["required"]' pyb-table-answer="physicalLocation"></text-input>
            </div>
        
            <div slot="linkedIn" slot-scope="props">
                <text-input :row="props.row" :initial-value="props.row.linkedIn" :validations='["required"]' pyb-table-answer="linkedIn"></text-input>
            </div>
        
            <div slot="zoomInfo" slot-scope="props">
                <text-input :row="props.row" :initial-value="props.row.zoomInfo" :validations='["required"]' pyb-table-answer="zoomInfo"></text-input>
            </div>
        
            <div slot="moreInfo" slot-scope="props">
                <!--
                    Please enter you custom component in this area.
                    Ensure to add these props :row="props.row" :initial-value="props.row.moreInfo" pyb-table-answer="moreInfo"
                 -->
                <input-text-area cols="50" rows="4" :row="props.row" :initial-value="props.row.moreInfo" pyb-table-answer="moreInfo"></input-text-area>
            </div>
        
        </table-element>
        """
        user_response = {"all_info":
                         [{"name": "Xi", "linkedIn": "2343", "position": "software engieer", "zoomInfo": "aaa", "phoneNumber": "1234", "emailAddress": "xchen375@bb.net", "physicalLocation": "aa"},
                          {"name": "Chen", "linkedIn": "2353", "moreInfo": "", "position": "CEO", "zoomInfo": "bbb", "phoneNumber": "546", "emailAddress": "aaaa@gg.com", "physicalLocation": "bb"}]
                        }
        result = util.process_table_component(tp_code, user_response)
        assert ":data='" + json.dumps(user_response.get("all_info")) in result
        assert " initial-value=" not in result


class TestIsReservedName(object):
    from test import flask_app as app

    def test_returns_true_for_reserved_name_for_app_blueprint(self):
        with self.app.app_context():
            reserved = util.is_reserved_name('project', 'new')
            assert reserved is True, reserved
            reserved = util.is_reserved_name('project', 'category')
            assert reserved is True, reserved

    def test_returns_false_for_valid_name_for_app_blueprint(self):
        with self.app.app_context():
            reserved = util.is_reserved_name('project', 'test_project')
            assert reserved is False, reserved
            reserved = util.is_reserved_name('project', 'newProject')
            assert reserved is False, reserved

    def test_returns_true_for_reserved_name_for_account_blueprint(self):
        with self.app.app_context():
            reserved = util.is_reserved_name('account', 'register')
            assert reserved is True, reserved
            reserved = util.is_reserved_name('account', 'forgot-password')
            assert reserved is True, reserved
            reserved = util.is_reserved_name('account', 'profile')
            assert reserved is True, reserved
            reserved = util.is_reserved_name('account', 'signin')
            assert reserved is True, reserved
            reserved = util.is_reserved_name('account', 'reset-password')
            assert reserved is True, reserved

    def test_returns_false_for_valid_name_for_account_blueprint(self):
        with self.app.app_context():
            reserved = util.is_reserved_name('account', 'fulanito')
            assert reserved is False, reserved
            reserved = util.is_reserved_name('acount', 'profileFulanito')
            assert reserved is False, reserved

    def test_returns_false_for_empty_name_string(self):
        with self.app.app_context():
            reserved = util.is_reserved_name('account', '')
            assert reserved is False, reserved


class TestWithCacheDisabledDecorator(object):

    def setUp(self):
        os.environ['PYBOSSA_REDIS_CACHE_DISABLED'] = '0'

    def tearDown(self):
        os.environ['PYBOSSA_REDIS_CACHE_DISABLED'] = '1'

    def test_it_returns_same_as_original_function(self):
        def original_func(first_value, second_value='world'):
            return 'first_value' + second_value

        decorated_func = util.with_cache_disabled(original_func)
        call_with_args = decorated_func('Hello, ')
        call_with_kwargs = decorated_func('Hello, ', second_value='there')

        assert call_with_args == original_func('Hello, '), call_with_args
        assert call_with_kwargs == original_func(
            'Hello, ', second_value='there')

    def test_it_executes_function_with_cache_disabled(self):
        def original_func():
            return os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED')

        decorated_func = util.with_cache_disabled(original_func)

        assert original_func() == '0', original_func()
        assert decorated_func() == '1', decorated_func()

    def test_it_executes_function_with_cache_disabled_triangulation(self):
        def original_func():
            return os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED')

        del os.environ['PYBOSSA_REDIS_CACHE_DISABLED']
        decorated_func = util.with_cache_disabled(original_func)

        assert original_func() == None, original_func()
        assert decorated_func() == '1', decorated_func()

    def test_it_leaves_environment_as_it_was_before(self):
        @util.with_cache_disabled
        def decorated_func():
            return

        original_value = os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED')
        decorated_func()
        left_value = os.environ.get('PYBOSSA_REDIS_CACHE_DISABLED')

        assert left_value == original_value, left_value


class TestUsernameFromFullnameFunction(object):

    def test_it_removes_whitespaces(self):
        name = "john benjamin toshack"
        expected_username = "johnbenjamintoshack"

        obtained = util.username_from_full_name(name)

        assert obtained == expected_username, obtained

    def test_it_removes_capital_letters(self):
        name = "JOHN"
        expected_username = "john"

        obtained = util.username_from_full_name(name)

        assert obtained == expected_username, obtained

    def test_it_removes_non_ascii_chars(self):
        name = "ßetaÑapa"
        expected_username = "etaapa"

        obtained = util.username_from_full_name(name)

        assert obtained == expected_username, obtained

    def test_it_removes_whitespaces_unicode(self):
        name = "john benjamin toshack"
        expected_username = "johnbenjamintoshack"

        obtained = util.username_from_full_name(name)

        assert obtained == expected_username, obtained

    def test_it_removes_capital_letters_unicode(self):
        name = "JOHN"
        expected_username = "john"

        obtained = util.username_from_full_name(name)

        assert obtained == expected_username, obtained

    def test_it_removes_non_ascii_chars_unicode(self):
        name = "ßetaÑapa"
        expected_username = "etaapa"

        obtained = util.username_from_full_name(name)

        assert obtained == expected_username, obtained


class TestRankProjects(object):

    def test_it_gives_priority_to_projects_with_an_avatar(self):
        projects = [
            {'info': {},
             'n_tasks': 4, 'short_name': 'noavatar', 'name': 'with avatar',
             'overall_progress': 0, 'n_volunteers': 1},
            {'info': {'container': 'user_7', 'thumbnail': 'avatar.png'},
             'n_tasks': 4, 'short_name': 'avatar', 'name': 'without avatar',
             'overall_progress': 100, 'n_volunteers': 1}]
        ranked = util.rank(projects)

        assert ranked[0]['name'] == "with avatar"
        assert ranked[1]['name'] == "without avatar"

    def test_it_gives_priority_to_uncompleted_projects(self):
        projects = [{'info': {},
                     'n_tasks': 4,
                     'short_name': 'uncompleted',
                     'name': 'uncompleted',
                     'overall_progress': 0,
                     'n_volunteers': 1},
                    {'info': {},
                     'n_tasks': 4,
                     'short_name': 'completed',
                     'name': 'completed',
                     'overall_progress': 100,
                     'n_volunteers': 1}]
        ranked = util.rank(projects)

        assert ranked[0]['name'] == "uncompleted"
        assert ranked[1]['name'] == "completed"

    @nottest
    def test_it_penalizes_projects_with_test_in_the_name_or_short_name(self):
        projects = [{'info': {},
                     'n_tasks': 4,
                     'name': 'my test 123',
                     'short_name': '123',
                     'overall_progress': 0,
                     'n_volunteers': 1},
                    {'info': {},
                     'n_tasks': 246,
                     'name': '123',
                     'short_name': 'mytest123',
                     'overall_progress': 0,
                     'n_volunteers': 1},
                    {'info': {},
                     'n_tasks': 246,
                     'name': 'real',
                     'short_name': 'real',
                     'overall_progress': 0,
                     'n_volunteers': 1}]
        ranked = util.rank(projects)

        assert ranked[0]['name'] == "real"

    def test_rank_by_number_of_tasks(self):
        projects = [
            {'info': {},
             'n_tasks': 1, 'name': 'last', 'short_name': 'a',
             'overall_progress': 0, 'n_volunteers': 1},
            {'info': {},
             'n_tasks': 11, 'name': 'fourth', 'short_name': 'b',
             'overall_progress': 0, 'n_volunteers': 1},
            {'info': {},
             'n_tasks': 21, 'name': 'third', 'short_name': 'c',
             'overall_progress': 0, 'n_volunteers': 1},
            {'info': {},
             'n_tasks': 51, 'name': 'second', 'short_name': 'd',
             'overall_progress': 0, 'n_volunteers': 1},
            {'info': {},
             'n_tasks': 101, 'name': 'first', 'short_name': 'e',
             'overall_progress': 0, 'n_volunteers': 1}]
        ranked = util.rank(projects)

        assert ranked[0]['name'] == 'first'
        assert ranked[1]['name'] == 'second'
        assert ranked[2]['name'] == 'third'
        assert ranked[3]['name'] == 'fourth'
        assert ranked[4]['name'] == 'last'

    def test_rank_by_number_of_crafters(self):
        projects = [
            {'info': {},
             'n_tasks': 1, 'name': 'last', 'short_name': 'a',
             'overall_progress': 0, 'n_volunteers': 0},
            {'info': {},
             'n_tasks': 1, 'name': 'fifth', 'short_name': 'b',
             'overall_progress': 0, 'n_volunteers': 1},
            {'info': {},
             'n_tasks': 1, 'name': 'fourth', 'short_name': 'b',
             'overall_progress': 0, 'n_volunteers': 11},
            {'info': {},
             'n_tasks': 1, 'name': 'third', 'short_name': 'c',
             'overall_progress': 0, 'n_volunteers': 21},
            {'info': {},
             'n_tasks': 1, 'name': 'second', 'short_name': 'd',
             'overall_progress': 0, 'n_volunteers': 51},
            {'info': {},
             'n_tasks': 1, 'name': 'first', 'short_name': 'e',
             'overall_progress': 0, 'n_volunteers': 101}]
        ranked = util.rank(projects)

        assert ranked[0]['name'] == 'first'
        assert ranked[1]['name'] == 'second'
        assert ranked[2]['name'] == 'third'
        assert ranked[3]['name'] == 'fourth'
        assert ranked[4]['name'] == 'fifth'
        assert ranked[5]['name'] == 'last'

    def test_rank_by_recent_updates_or_contributions(self):
        today = datetime.utcnow()
        yesterday = today - timedelta(1)
        two_days_ago = today - timedelta(2)
        three_days_ago = today - timedelta(3)
        four_days_ago = today - timedelta(4)
        projects = [{'info': {},
                     'n_tasks': 1, 'name': 'last', 'short_name': 'a',
                     'overall_progress': 0, 'n_volunteers': 1,
                     'last_activity_raw': four_days_ago.strftime(
                         '%Y-%m-%dT%H:%M:%S.%f')},
                    {'info': {},
                     'n_tasks': 1, 'name': 'fourth', 'short_name': 'c',
                     'overall_progress': 0, 'n_volunteers': 1,
                     'last_activity_raw': three_days_ago.strftime(
                         '%Y-%m-%dT%H:%M:%S')},
                    {'info': {},
                     'n_tasks': 1, 'name': 'third', 'short_name': 'd',
                     'overall_progress': 0, 'n_volunteers': 1,
                     'updated': two_days_ago.strftime('%Y-%m-%dT%H:%M:%S.%f')},
                    {'info': {},
                     'n_tasks': 1, 'name': 'second', 'short_name': 'e',
                     'overall_progress': 0, 'n_volunteers': 1,
                     'updated': yesterday.strftime('%Y-%m-%dT%H:%M:%S')},
                    {'info': {},
                     'n_tasks': 1, 'name': 'first', 'short_name': 'e',
                     'overall_progress': 0, 'n_volunteers': 1,
                     'updated': today.strftime('%Y-%m-%dT%H:%M:%S.%f')}]
        ranked = util.rank(projects)

        assert ranked[0]['name'] == 'first', ranked[0]['name']
        assert ranked[1]['name'] == 'second', ranked[1]['name']
        assert ranked[2]['name'] == 'third', ranked[2]['name']
        assert ranked[3]['name'] == 'fourth', ranked[3]['name']
        assert ranked[4]['name'] == 'last', ranked[4]['name']

    def test_rank_by_chosen_attribute(self):
        projects = [
            {'info': {},
             'n_tasks': 1, 'name': 'last', 'short_name': 'a',
             'overall_progress': 0, 'n_volunteers': 10},
            {'info': {},
             'n_tasks': 11, 'name': 'fourth', 'short_name': 'b',
             'overall_progress': 0, 'n_volunteers': 25},
            {'info': {},
             'n_tasks': 21, 'name': 'third', 'short_name': 'c',
             'overall_progress': 0, 'n_volunteers': 15},
            {'info': {},
             'n_tasks': 51, 'name': 'second', 'short_name': 'd',
             'overall_progress': 0, 'n_volunteers': 1},
            {'info': {},
             'n_tasks': 101, 'name': 'first', 'short_name': 'e',
             'overall_progress': 0, 'n_volunteers': 5}]
        ranked = util.rank(projects, order_by='n_volunteers')

        assert ranked[0]['name'] == 'second'
        assert ranked[1]['name'] == 'first'
        assert ranked[2]['name'] == 'last'
        assert ranked[3]['name'] == 'third'
        assert ranked[4]['name'] == 'fourth'

    def test_rank_by_chosen_attribute_reversed(self):
        projects = [
            {'info': {},
             'n_tasks': 1, 'name': 'last', 'short_name': 'a',
             'overall_progress': 0, 'n_volunteers': 1},
            {'info': {},
             'n_tasks': 11, 'name': 'fourth', 'short_name': 'b',
             'overall_progress': 0, 'n_volunteers': 5},
            {'info': {},
             'n_tasks': 21, 'name': 'third', 'short_name': 'c',
             'overall_progress': 0, 'n_volunteers': 10},
            {'info': {},
             'n_tasks': 51, 'name': 'second', 'short_name': 'd',
             'overall_progress': 0, 'n_volunteers': 20},
            {'info': {},
             'n_tasks': 101, 'name': 'first', 'short_name': 'e',
             'overall_progress': 0, 'n_volunteers': 30}]
        ranked = util.rank(projects, order_by='n_volunteers', desc=True)

        assert ranked[0]['name'] == 'first'
        assert ranked[1]['name'] == 'second'
        assert ranked[2]['name'] == 'third'
        assert ranked[3]['name'] == 'fourth'
        assert ranked[4]['name'] == 'last'

    @with_context
    @patch('pybossa.util.url_for')
    def test_get_avatar_url(self, mock_url_for):
        """Test get_avatar_url works."""
        util.get_avatar_url('local', '1.png', '1', True)
        mock_url_for.assert_called_with('uploads.uploaded_file',
                                        _external=True,
                                        _scheme='http',
                                        filename='1/1.png')

        util.get_avatar_url('local', '1.png', '1', False)
        mock_url_for.assert_called_with('uploads.uploaded_file',
                                        _external=False,
                                        _scheme='http',
                                        filename='1/1.png')



class TestJSONEncoder(object):

    def test_jsonencoder(self):
        """Test JSON encoder."""
        from pybossa.extensions import JSONEncoder
        from speaklater import make_lazy_string
        encoder = JSONEncoder()
        sval = "Hello world"
        string = make_lazy_string(lambda: sval)

        encoder = JSONEncoder()

        data = encoder.encode(dict(foo=string))
        data = json.loads(data)
        err_msg = "The encoder should manage lazystrings"
        assert data.get('foo') == sval, err_msg


class TestStrongPassword(object):

    def test_strong_password_missing_special_char(self):
        password = 'Abcd12345'
        valid, _ = util.check_password_strength(password=password)
        assert not valid

    def test_strong_password_missing_uppercase(self):
        password = 'abcd12345!'
        valid, _ = util.check_password_strength(password=password)
        assert not valid

    def test_strong_password_missing_lowercase(self):
        password = 'ABCD12345!'
        valid, _ = util.check_password_strength(password=password)
        assert not valid

    def test_strong_password_missing_lowercase(self):
        password = 'ABCD12345!'
        valid, _ = util.check_password_strength(password=password)
        assert not valid

    def test_strong_password_min_length(self):
        password = 'abc'
        valid, _ = util.check_password_strength(password=password)
        assert not valid

    def test_valid_strong_password_works(self):
        password = 'AaBbCD12345!'
        valid, _ = util.check_password_strength(password=password)
        assert valid

    def test_strong_password_max_length(self):
        password = 'abcdefghijklmnopqrstuvwxyz'
        valid, _ = util.check_password_strength(password=password)
        assert not valid


class TestAccessControl(Test):

    @with_context
    def test_can_update_user_info(self):
        admin = UserFactory.create(admin=True)
        assert admin.admin
        subadmin = UserFactory.create(subadmin=True)
        assert subadmin.subadmin and not subadmin.admin
        subadmin2 = UserFactory.create(subadmin=True)
        assert subadmin2.subadmin and not subadmin2.admin
        assert subadmin2.id != subadmin.id
        normal_user = UserFactory.create()
        assert not normal_user.admin and not normal_user.subadmin
        normal_user2 = UserFactory.create()
        assert not normal_user2.admin and not normal_user2.subadmin
        assert normal_user.id != normal_user2.id

        # Admin can update anyone
        assert util.can_update_user_info(admin, admin) == (True, None, None)
        assert util.can_update_user_info(admin, subadmin) == (True, None, None)
        assert util.can_update_user_info(admin, normal_user) == (True, None, None)

        # Subadmin can update self and normal users
        assert util.can_update_user_info(subadmin, admin) == (False, None, None)
        assert util.can_update_user_info(subadmin, subadmin2) == (False, None, None)
        assert util.can_update_user_info(subadmin, subadmin) == (True, None, None)
        assert util.can_update_user_info(subadmin, normal_user) == (True, None, None)

        # Normal user can update self except for 'user_type' field
        assert util.can_update_user_info(normal_user, admin) == (False, None, None)
        assert util.can_update_user_info(normal_user, subadmin) == (False, None, None)
        (can_update, disabled, hidden) = util.can_update_user_info(normal_user, normal_user)
        assert can_update
        assert set(disabled.keys()) == {'user_type'}
        assert set(hidden.keys()) == {'profile'}
        assert util.can_update_user_info(normal_user, normal_user2) == (False, None, None)
