# -*- coding: utf8 -*-
"""Regression tests for webhook request handling.

Two holes are covered here:

1. The result-webhook delivery job stored the response body returned by an
   owner-chosen URL. The stored value is rendered on the webhook status page
   and mailed to ADMINS, which turned a server-side POST into a full read of
   whatever the target returned (CWE-918).

2. 'webhook' is in neither ProjectAPI.reserved_keys nor APIBase.immutable_keys,
   so PUT/POST /api/project set the field with no validation at all, bypassing
   the form validator that guards the same field in the web UI.
"""
import socket
from unittest.mock import patch, MagicMock

import pytest
from werkzeug.exceptions import BadRequest

from test import with_context, with_context_settings
from pybossa.jobs import summarize_webhook_response
from pybossa.api.project import ProjectAPI


def _response(text, status_code=200):
    """A stand-in for a requests.Response from the webhook target."""
    response = MagicMock()
    response.text = text
    response.status_code = status_code
    return response


# A marker long enough to survive readability's article extractor, which is
# what the previous implementation ran the body through.
LEAKED = 'INTERNAL_RESPONSE_MARKER'
INTERNAL_BODY = (
    '<html><body><article><p>' + (LEAKED + ' ') * 40 + '</p></article></body></html>'
)


class TestSummarizeWebhookResponse:

    @with_context
    def test_response_body_is_not_persisted(self):
        """The core regression: no part of the target's body is stored.

        The previous code stored Document(response.text).summary(), which
        retains the body text, so this assertion fails against it.
        """
        stored = summarize_webhook_response(_response(INTERNAL_BODY))
        assert LEAKED not in stored

    @with_context
    def test_status_code_is_still_recorded(self):
        assert summarize_webhook_response(_response('irrelevant', 503)) == 'HTTP 503'

    @with_context
    def test_plain_text_body_not_persisted(self):
        """Non-HTML bodies leak too -- most internal endpoints return JSON."""
        stored = summarize_webhook_response(
            _response('{"token": "' + LEAKED + '"}'))
        assert LEAKED not in stored

    @with_context
    def test_empty_body_does_not_raise(self):
        assert summarize_webhook_response(_response('')) == 'HTTP 200'
        assert summarize_webhook_response(_response(None)) == 'HTTP 200'

    @with_context_settings(WEBHOOK_STORE_RESPONSE_BODY=True,
                           WEBHOOK_RESPONSE_MAX_LENGTH=16)
    def test_body_is_truncated_when_storage_is_opted_into(self):
        stored = summarize_webhook_response(_response('A' * 500))
        assert stored == 'HTTP 200: ' + 'A' * 16

    @with_context_settings(WEBHOOK_STORE_RESPONSE_BODY=True,
                           WEBHOOK_RESPONSE_MAX_LENGTH=16)
    def test_opt_in_storage_is_plain_text_not_html(self):
        """Even opted in, the value is not markup: it is mailed to ADMINS."""
        stored = summarize_webhook_response(_response('<script>x</script>'))
        assert stored.startswith('HTTP 200: ')
        assert '<html' not in stored
        assert '<body' not in stored


class TestProjectApiWebhookValidation:
    """The API write path must apply the same guard as the delivery job."""

    @with_context
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_link_local_webhook_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('169.254.169.254', 443))
        ]
        with pytest.raises(BadRequest):
            ProjectAPI._validate_webhook_url('https://metadata.example.com/latest')

    @with_context
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_private_webhook_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.5', 443))
        ]
        with pytest.raises(BadRequest):
            ProjectAPI._validate_webhook_url('https://internal.example.com/hook')

    @with_context
    def test_non_https_webhook_rejected(self):
        with pytest.raises(BadRequest):
            ProjectAPI._validate_webhook_url('http://hooks.example.com/hook')

    @with_context
    def test_non_http_scheme_rejected(self):
        with pytest.raises(BadRequest):
            ProjectAPI._validate_webhook_url('file:///etc/passwd')

    @with_context
    @patch('pybossa.ssrf_guard.socket.getaddrinfo')
    def test_public_webhook_accepted(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))
        ]
        ProjectAPI._validate_webhook_url('https://hooks.example.com/hook')

    @with_context
    def test_empty_webhook_is_ignored(self):
        """Clearing the field must stay possible."""
        ProjectAPI._validate_webhook_url(None)
        ProjectAPI._validate_webhook_url('')
