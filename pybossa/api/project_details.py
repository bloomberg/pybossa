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
from pybossa.cache import memoize
from pybossa.core import project_repo, timeouts
from pybossa.error import ErrorStatus
from pybossa.api.api_base import APIBase
from pybossa.model.project import Project
from pybossa.model import DomainObject
from pybossa.auth import ensure_authorized_to
from pybossa.util import fuzzyboolean

class ProjectDetailsAPI(APIBase):

    __class__ = Project

    def _filter_query(self, repo_info, limit, offset, orderby):
        if 'info' not in request.args.keys():
            raise BadRequest("info required")
        if len(request.args['info']) == 0:
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
            # This is for n_favs orderby case
            if not isinstance(result, DomainObject):
                if 'n_favs' in result.keys():
                    result = result[0]
            try:
                if (result.__class__ != self.__class__):
                    (item, headline, rank) = result
                else:
                    item = result
                    headline = None
                    rank = None
                if not self._verify_auth(item):
                    continue
                datum = self._create_dict_from_model(item)
                if headline:
                    datum['headline'] = headline
                if rank:
                    datum['rank'] = rank
                items.append(datum)
            except (Forbidden, Unauthorized):
                # pass as it is 401 or 403
                pass
            except Exception:  # pragma: no cover
                raise
        if oid is not None:
            if not items:
                raise Forbidden('Forbidden')
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
