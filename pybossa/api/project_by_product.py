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

import json
from flask import request, abort
from flask_login import current_user
from werkzeug.exceptions import BadRequest
from pybossa.cache import memoize
from pybossa.core import project_repo, timeouts
from pybossa.error import ErrorStatus
from pybossa.api.api_base import APIBase
from pybossa.model.project import Project
from pybossa.model import DomainObject
from pybossa.auth import ensure_authorized_to
from pybossa.util import fuzzyboolean

class ProjectByProductAPI(APIBase):

    __class__ = Project

    def _filter_query(self, repo_info, limit, offset, orderby):
        if 'info' not in request.args.keys():
            raise BadRequest("info required")
        if len(request.args['info']) == 0:
            return []
        filters = {'info':request.args['info']}

        repo = repo_info['repo']
        filters = self.api_context(all_arg=request.args.get('all'), **filters)
        query_func = repo_info['filter']
        filters = self._custom_filter(filters)
        last_id = request.args.get('last_id')
        desc = request.args.get('desc') if request.args.get('desc') else False
        desc = fuzzyboolean(desc)

        if last_id:
            results = getattr(repo, query_func)(limit=limit, last_id=last_id,
                                                desc=False,
                                                orderby=orderby,
                                                **filters)
        else:
            results = getattr(repo, query_func)(limit=limit, offset=offset,
                                                desc=desc,
                                                orderby=orderby,
                                                **filters)
        return results

    def _select_attributes(self, data):
        if (current_user.is_authenticated and
            (current_user.admin or current_user.subadmin)):
            return self._get_project_metadata(data)
        else:
            return []

    def _get_project_metadata(self, data):
        tmp = {}
        tmp['product'] = data['info']['product']
        tmp['subproduct'] = data['info']['subproduct']
        tmp['id'] = data['id']
        return tmp
