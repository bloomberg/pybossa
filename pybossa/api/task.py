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
"""
PYBOSSA api module for exposing domain object Task via an API.

This package adds GET, POST, PUT and DELETE methods for:
    * tasks

"""
from flask import abort, current_app
from flask_login import current_user
from werkzeug.exceptions import BadRequest, Conflict, NotFound
from pybossa.model.task import Task
from pybossa.model.project import Project
from pybossa.core import result_repo
from pybossa.util import sign_task
from .api_base import APIBase
from pybossa.api.pwd_manager import get_pwd_manager
from pybossa.util import get_user_id_or_ip, validate_required_fields
from pybossa.core import task_repo, project_repo
from pybossa.cache.projects import get_project_data
from pybossa.data_access import when_data_access
import hashlib
from flask import url_for
from pybossa.cloud_store_api.s3 import upload_json_data
from pybossa.auth.task import TaskAuth
from pybossa.cache import delete_memoized
from pybossa.cache.task_browse_helpers import get_searchable_columns
import json
import copy
from pybossa.task_creator_helper import get_task_expiration
from pybossa.model import make_timestamp
from pybossa.task_creator_helper import generate_checksum
from pybossa.cache.projects import get_project_data


class TaskAPI(APIBase):

    """Class for domain object Task."""

    __class__ = Task
    reserved_keys = set(['id', 'created', 'state', 'fav_user_ids',
        'calibration'])

    immutable_keys = set(['project_id'])

    def _forbidden_attributes(self, data):
        for key in data.keys():
            if key in self.reserved_keys:
                raise BadRequest("Reserved keys in payload")

    def _update_attribute(self, new, old):
        for key, value in old.info.items():
            new.info.setdefault(key, value)

        gold_task = bool(new.gold_answers)
        n_taskruns = len(new.task_runs)
        if new.state == 'completed':
            if gold_task or (old.n_answers < new.n_answers and
                n_taskruns < new.n_answers):
                new.state = 'ongoing'
        if new.state == 'ongoing':
            if not gold_task and (n_taskruns >= new.n_answers):
                new.state = 'completed'
        new.calibration = int(gold_task)
        if new.expiration is not None:
            new.expiration = get_task_expiration(new.expiration, old.created)

    def _preprocess_post_data(self, data):
        project_id = data["project_id"]
        project = project_repo.get(project_id)
        if not project:
            raise NotFound(f'Non existing project id {project_id}')

        info = data["info"]
        if isinstance(info, dict):
            hdfs_task = any([val.startswith("/fileproxy/hdfs/") for val in info.values() if isinstance(val, str)])
            if hdfs_task:
                raise BadRequest("Invalid task payload. HDFS is not supported")
        try:
            dup_checksum = generate_checksum(project_id=project_id, task=data)
        except Exception as e:
            current_app.logger.info("Project %d. Error generating duplicate task checksum %s", project_id, str(e))
            raise BadRequest(str(e))
        data["dup_checksum"] = dup_checksum
        completed_tasks = project.info.get("duplicate_task_check", {}).get("completed_tasks", False)
        duplicate_task = task_repo.find_duplicate(
            project_id=project_id,
            info=info,
            dup_checksum=dup_checksum,
            completed_tasks=completed_tasks
        )
        if duplicate_task:
            current_app.logger.info("Project %s, task checksum %s. Duplicate task found with task id %s. Ignoring task creation",
                                    str(project_id), str(dup_checksum), str(duplicate_task))
            message = {
                'reason': 'DUPLICATE_TASK',
                'task_id': duplicate_task
            }
            raise Conflict(json.dumps(message))


        if 'n_answers' not in data:
            data['n_answers'] = project.get_default_n_answers()
        user_pref = data.get('user_pref', {})
        if user_pref.get('languages'):
            user_pref['languages'] = [s.lower() for s in user_pref.get('languages', [])]
        if user_pref.get('locations'):
            user_pref['locations'] = [s.lower() for s in user_pref.get('locations', [])]
        if user_pref.get('assign_user'):
            user_pref['assign_user'] = [s.lower() for s in user_pref.get('assign_user', [])]
        invalid_fields = validate_required_fields(info)
        if invalid_fields:
            raise BadRequest('Missing or incorrect required fields: {}'
                            .format(','.join(invalid_fields)))
        if data.get('gold_answers'):
            try:
                gold_answers = data['gold_answers']
                if type(gold_answers) is dict:
                    data['calibration'] = 1
                    data['exported'] = True
            except Exception as e:
                raise BadRequest('Invalid gold_answers')
        create_time = data.get("created") or make_timestamp()
        data["expiration"] = get_task_expiration(data.get('expiration'), create_time)

    def _verify_auth(self, item):
        if not current_user.is_authenticated:
            return False
        if current_user.admin or current_user.subadmin:
            return True
        project = Project(**get_project_data(item.project_id))
        pwd_manager = get_pwd_manager(project)
        return not pwd_manager.password_needed(project, get_user_id_or_ip())

    def _sign_item(self, item):
        project_id = item['project_id']
        if current_user.admin or \
           current_user.id in get_project_data(project_id)['owners_ids']:
            sign_task(item)

    def _select_attributes(self, data):
        return TaskAuth.apply_access_control(data, user=current_user, project_data=get_project_data(data['project_id']))

    def put(self, oid):
        # reset cache / memoized
        delete_memoized(get_searchable_columns)
        return super(TaskAPI, self).put(oid)
