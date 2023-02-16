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
from werkzeug.exceptions import BadRequest, Unauthorized, Forbidden
from pybossa.api.api_base import APIBase
from pybossa.model.project import Project
from pybossa.model import DomainObject

class ProjectDetailsAPI(APIBase):
    """
    Class for retreiving details about projects.

    """
    __class__ = Project

    def _filter_query(self, repo_info, limit, offset, orderby):
        if len(request.args.keys()) == 0 or (len(request.args.keys()) == 1 and "api_key" in request.args.keys()):
            return []
        if (not current_user.is_authenticated or
             (not current_user.admin and not current_user.subadmin)):
            raise Unauthorized("User not authorized for request")

        return APIBase._filter_query(self, repo_info, limit, offset, orderby)

    def _create_json_response(self, query_result, oid):
        if len(query_result) == 1 and query_result[0] is None:
            raise abort(404)
        items = []
        for result in query_result:
            try:
                item = result
                datum = self._create_dict_from_model(item)
                items.append(datum)
            except Exception:  # pragma: no cover
                raise
        if oid is not None:
            self._sign_item(items[0])
            items = items[0]
        return json.dumps(items)


    def _select_attributes(self, data):
        tmp = {}
        tmp['id'] = data['id']
        tmp['short_name'] = data['short_name']
        tmp['product'] = data['info']['product']
        tmp['subproduct'] = data['info']['subproduct']
        tmp['created'] = data['created']

        return tmp
