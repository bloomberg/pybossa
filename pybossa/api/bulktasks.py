# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2022 Scifabric LTD.
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
"""
PYBOSSA api module for exposing domain object BulkTaskUpdate via an API.
"""
from flask import request, Response
from flask import current_app
from flask_login import current_user
from werkzeug.exceptions import NotFound, BadRequest
from werkzeug.exceptions import MethodNotAllowed, Unauthorized
from pybossa.core import project_repo, task_repo
from pybossa.error import ErrorStatus
from pybossa.api.task import TaskAPI
from pybossa.model.task import Task
from pybossa.util import jsonpify, crossdomain
from pybossa.core import ratelimits
from pybossa.ratelimit import ratelimit


cors_headers = ["Content-Type", "Authorization"]
allowed_attributes = ["id", "priority_0"]
error = ErrorStatus()

class BulkTasksAPI(TaskAPI):

    """Class for domain object Task."""

    __class__ = Task

    def get(self, oid=None):
        raise MethodNotAllowed

    def post(self):
        raise MethodNotAllowed

    def delete(self, oid=None):
        raise MethodNotAllowed

    @jsonpify
    @crossdomain(origin="*", headers=cors_headers)
    @ratelimit(limit=ratelimits.get("LIMIT"), per=ratelimits.get("PER"))
    def put(self, oid):
        """Update task attributes in bulk. Need atleast subadmin access"""
        if current_user.is_anonymous or not(current_user.admin or current_user.subadmin):
            raise Unauthorized("Insufficient privilege to the request")

        project = project_repo.get(oid)
        update_info = request.json
        if not (project and update_info):
            raise BadRequest

        all_owners = project.owners_ids + ([project.owner_id] if project.owner_id not in project.owners_ids else [])
        if not (current_user.admin or current_user.id in all_owners):
            raise Unauthorized("Insufficient privilege to the request")

        try:
            update_payload, dropped_payload = [], []
            for data in update_info:
                task = task_repo.get_task(data.get("id"))
                if not (task and task.project_id == project.id):
                    dropped_payload.append(data)
                elif [k for k in data.keys() if k not in allowed_attributes]:
                    dropped_payload.append(data)
                else:
                    update_payload.append(data)

            current_app.logger.info(f"Project {project.id}, input for bulk update {str(update_info)}, dropped payload {dropped_payload}")
            current_app.logger.info(f"Calling bulk update for project {project.id} with payload {str(update_payload)}")
            task_repo.bulk_update(update_payload)
            json_response = {}
            return Response(json_response, mimetype="application/json")
        except Exception as e:
            current_app.logger.exception(f"Error in bulktasks PUT request, {str(e)}")
            return error.format_exception(
                e,
                target=self.__class__.__name__.lower(),
            action="PUT")

