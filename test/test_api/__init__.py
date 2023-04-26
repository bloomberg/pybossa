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
import json
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

from dateutil.parser import parse
from werkzeug.http import parse_cookie

from pybossa.api import large_language_model
from pybossa.core import create_app
from test import Test


def get_pwd_cookie(short_name, res):
    cookie = (None, None, None)
    raw_cookie = None
    cookies = res.headers.get_all('Set-Cookie')
    for c in cookies:
        for k, v in parse_cookie(c).items():
            if k == '%spswd' % short_name:
                cookie = k, v
                raw_cookie = c
    params = (v.strip().split('=') for v in raw_cookie.split(';'))
    expires = dict(params)['Expires']

    # parse() function can parse different formats, including
    # '%d-%b-%Y %H:%M:%S GMT' and '%d %b %Y %H:%M:%S GMT'.
    # Using datetime.strptime() limits a single format
    expires = parse(expires)

    return cookie[0], cookie[1], expires


class TestAPI(Test):

    endpoints = ['project', 'task', 'taskrun', 'user']

class TestLargeLanguageModel(unittest.TestCase):
    def setUp(self):
        self.app = create_app(run_as_server=False)
        self.app.config['LLM_ENDPOINTS'] = {
            'flan-ul2': 'http://localhost:5000/llm'
        }
        self.client = self.app.test_client()

    @patch('requests.post')
    def test_valid_request(self, mock_post):
        response_data = {
            "predictions": [{
                "output": "Microsoft"
            }]
        }
        mock_post.return_value = MagicMock(status_code=200, text=json.dumps(response_data))
        with self.app.test_request_context('/', json={
            "prompts": "Identify the company name: Microsoft will release Windows 20 next year."
        }):
            response = large_language_model('flan-ul2')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Model: ', response.json)
            self.assertIn('predictions: ', response.json)

    @patch('requests.post')
    def test_valid_request_with_list_of_prompts(self, mock_post):
        response_data = {
            "predictions": [{
                "output": "Microsoft"
            }]
        }
        mock_post.return_value = MagicMock(status_code=200,
                                           text=json.dumps(response_data))
        with self.app.test_request_context('/', json={
            "prompts": ["Identify the company name: Microsoft will release Windows 20 next year.", "test"]
        }):
            response = large_language_model('flan-ul2')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Model: ', response.json)
            self.assertIn('predictions: ', response.json)

    @patch('requests.post')
    def test_valid_request_with_instances_key_in_json(self, mock_post):
        response_data = {
            "predictions": [{
                "output": "Microsoft"
            }]
        }
        mock_post.return_value = MagicMock(status_code=200,
                                           text=json.dumps(response_data))
        with self.app.test_request_context('/', json={
            "instances": [
                {
                    "context": "Identify the company name: Microsoft will release Windows 20 next year.",
                    "temperature": 1.0,
                    "seed": 12345,
                    "repetition_penalty": 1.05,
                    "num_beams": 1,
                }
            ]
        }):
            response = large_language_model('flan-ul2')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Model: ', response.json)
            self.assertIn('predictions: ', response.json)

    @patch('requests.post')
    def test_invalid_model_name(self, mock_post):
        mock_post.return_value = MagicMock(status_code=403, text='{"error": "Model not found"}')
        with self.app.test_request_context('/', json={
            "prompts": "Identify the company name: Microsoft will release Windows 20 next year."
        }):
            response = large_language_model('invalid-model')
            self.assertEqual(response.status_code, 400)
            self.assertIn('LLM is unsupported', response.json.get('exception_msg'))

    @patch('requests.post')
    def test_invalid_json(self, mock_post):
        with self.app.test_request_context('/', data='invalid-json', content_type='application/json'):
            response = large_language_model('flan-ul2')
            self.assertEqual(response.status_code, 400)
            self.assertIn('Invalid JSON', response.json.get('exception_msg'))

    @patch('requests.post')
    def test_invalid_post_data(self, mock_post):
        response_data = {
            "predictions": [{
                "output": "Microsoft"
            }]
        }
        mock_post.return_value = MagicMock(status_code=200,
                                           text=json.dumps(response_data))
        with self.app.test_request_context('/', json={
            "invalid": [
                {
                    "context": "Identify the company name: Microsoft will release Windows 20 next year.",
                    "temperature": 1.0,
                    "seed": 12345,
                    "repetition_penalty": 1.05,
                    "num_beams": 1,
                }
            ]
        }):
            response = large_language_model('flan-ul2')
            self.assertEqual(response.status_code, 400)
            self.assertIn('The JSON should have', response.json.get('exception_msg'))

    @patch('requests.post')
    def test_empty_prompts(self, mock_post):
        with self.app.test_request_context('/', json={
            "prompts": ""
        }):
            response = large_language_model('flan-ul2')
            self.assertEqual(response.status_code, 400)
            self.assertIn('prompts should not be empty', response.json.get('exception_msg'))

    @patch('requests.post')
    def test_invalid_prompts_type(self, mock_post):
        with self.app.test_request_context('/', json={
            "prompts": 123
        }):
            response = large_language_model('flan-ul2')
            self.assertEqual(response.status_code, 400)
            self.assertIn('prompts should be a string', response.json.get('exception_msg'))
