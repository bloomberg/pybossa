# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2017 Scifabric LTD.
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

import os
import base64
import uuid

from pybossa.core import sentinel
from otpauth import OtpAuth


conn = sentinel.master


OTP_SECRET_KEY_PREFIX = 'pybossa:otpsecret:user_email:{}'
OTP_URL_TOKEN_PREFIX = 'pybossa:otpurltoken:{}'
OTP_TTL = 60 * 5


def _create_otp_secret_key(user_email):
    return OTP_SECRET_KEY_PREFIX.format(user_email)


def _create_otp_secret():
    otp_secret = OtpAuth(base64.b32encode(os.urandom(10)).decode('utf-8'))
    return otp_secret.totp()


def generate_otp_secret(user_email):
    key = _create_otp_secret_key(user_email)
    otp_secret = _create_otp_secret()
    conn.setex(key, OTP_TTL, otp_secret)
    return otp_secret


def retrieve_user_otp_secret(user_email):
    key = _create_otp_secret_key(user_email)
    return conn.get(key)


def _create_url_token_key(token):
    return OTP_URL_TOKEN_PREFIX.format(token)


def generate_url_token(user_email):
    token = uuid.uuid4().hex  # hex for Python3
    key = _create_url_token_key(token)
    conn.delete(token)
    conn.setex(key, OTP_TTL, user_email)
    return token


def retrieve_email_for_token(token):
    key = _create_url_token_key(token)
    email = conn.get(key)
    if type(email) == bytes:
        email = email.decode()  # return unicode string
    return email


def expire_token(token):
    key = _create_url_token_key(token)
    conn.delete(key)

def is_enabled(user_email, config):
    # Allow bypassing two-factor-auth if the feature is disabled or if the user's email is included in the bypass list.
    bypass_list = config.get('BYPASS_TWO_FACTOR_AUTH') or []
    enable_two_factor_auth = config.get('ENABLE_TWO_FACTOR_AUTH') or False

    return enable_two_factor_auth and user_email not in bypass_list