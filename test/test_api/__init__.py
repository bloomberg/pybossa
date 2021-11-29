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
from datetime import datetime

from dateutil.parser import parse
from werkzeug.http import parse_cookie

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

