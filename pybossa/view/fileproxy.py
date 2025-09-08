# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2018 Scifabric LTD.
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
from functools import wraps
from urllib.parse import parse_qs, urlparse

import requests
import six
from boto.exception import S3ResponseError
from flask import Blueprint, Response, current_app, request
from flask_login import current_user, login_required
from werkzeug.exceptions import (BadRequest, Forbidden, InternalServerError,
                                 NotFound)

from pybossa.cache.projects import get_project_data
from pybossa.contributions_guard import ContributionsGuard
from pybossa.core import signer, task_repo
from pybossa.encryption import AESWithGCM
# from pybossa.pybhdfs.client import HDFSKerberos
from pybossa.sched import has_lock
from pybossa.task_creator_helper import get_encryption_key, read_encrypted_file

blueprint = Blueprint('fileproxy', __name__)

TASK_SIGNATURE_MAX_SIZE = 128

def no_cache(view_func):
    @wraps(view_func)
    def decorated(*args, **kwargs):
        response = view_func(*args, **kwargs)
        response.headers.add('Cache-Control', 'no-store')
        response.headers.add('Pragma', 'no-cache')
        return response
    return decorated


def check_allowed(user_id, task_id, project, is_valid_url):
    task = task_repo.get_task(task_id)

    if not task or task.project_id != project['id']:
        raise BadRequest('Task does not exist')

    if not any(is_valid_url(v) for v in task.info.values()):
        raise Forbidden('Invalid task content')

    if current_user.admin:
        return True

    if has_lock(task_id, user_id,
                project['info'].get('timeout', ContributionsGuard.STAMP_TTL)):
        return True

    if user_id in project['owners_ids']:
        return True

    raise Forbidden('FORBIDDEN')

def get_read_encrypted_file_with_signature_response(store, project_id, bucket, key_name, signature):
    decrypted, key = read_encrypted_file_with_signature(store, project_id, bucket, key_name, signature)

    response = Response(decrypted, content_type=key.content_type)
    if hasattr(key, "content_encoding") and key.content_encoding:
        response.headers.add('Content-Encoding', key.content_encoding)
    if hasattr(key, "content_disposition") and key.content_disposition:
        response.headers.add('Content-Disposition', key.content_disposition)
    return response


def read_encrypted_file_with_signature(store, project_id, bucket, key_name, signature):
    if not signature:
        current_app.logger.exception('Project id {} no signature {}'.format(project_id, key_name))
        raise Forbidden('No signature')
    size_signature = len(signature)
    if size_signature > TASK_SIGNATURE_MAX_SIZE:
        current_app.logger.exception(
            'Project id {}, path {} invalid task signature. Signature length {} exceeds max allowed length {}.' \
                .format(project_id, key_name, size_signature, TASK_SIGNATURE_MAX_SIZE))
        raise Forbidden('Invalid signature')

    project = get_project_data(project_id)
    timeout = project['info'].get('timeout', ContributionsGuard.STAMP_TTL)

    payload = signer.loads(signature, max_age=timeout)
    task_id = payload['task_id']

    check_allowed(current_user.id, task_id, project, lambda v: v == request.path)

    return read_encrypted_file(store, project, bucket, key_name)


@blueprint.route('/encrypted/<string:store>/<string:bucket>/workflow_request/<string:workflow_uid>/<int:project_id>/<path:path>')
@no_cache
@login_required
def encrypted_workflow_file(store, bucket, workflow_uid, project_id, path):
    """Proxy encrypted task file in a cloud storage for workflow"""
    key_name = '/workflow_request/{}/{}/{}'.format(workflow_uid, project_id, path)
    signature = request.args.get('task-signature')
    current_app.logger.info('Project id {} decrypt workflow file. {}'.format(project_id, path))
    return get_read_encrypted_file_with_signature_response(store, project_id, bucket, key_name, signature)


@blueprint.route('/encrypted/<string:store>/<string:bucket>/<int:project_id>/<path:path>')
@no_cache
@login_required
def encrypted_file(store, bucket, project_id, path):
    """Proxy encrypted task file in a cloud storage"""
    key_name = '/{}/{}'.format(project_id, path)
    signature = request.args.get('task-signature')
    current_app.logger.info('Project id {} decrypt file. {}'.format(project_id, path))
    current_app.logger.info("store %s, bucket %s, project_id %s, path %s", store, bucket, str(project_id), path)
    return get_read_encrypted_file_with_signature_response(store, project_id, bucket, key_name, signature)


def encrypt_task_response_data(task_id, project_id, data):
    content = None
    task = task_repo.get_task(task_id)
    if not (task and isinstance(task.info, dict) and 'private_json__encrypted_payload' in task.info):
        return content

    project = get_project_data(project_id)
    secret = get_encryption_key(project)
    cipher = AESWithGCM(secret)
    content = json.dumps(data)
    content = cipher.encrypt(content.encode('utf8'))
    return content


@blueprint.route('/hdfs/<string:cluster>/<int:project_id>/<path:path>')
@no_cache
@login_required
def hdfs_file(project_id, cluster, path):
    raise BadRequest("Invalid task. HDFS is not supported")


def validate_task(project, task_id, user_id):
    """Confirm task payload is valid and user is authorized to access task."""
    task = task_repo.get_task(task_id)

    if not task or task.project_id != project['id']:
        raise BadRequest('Task does not exist')

    if current_user.admin:
        return True

    if has_lock(task_id, user_id,
                project['info'].get('timeout', ContributionsGuard.STAMP_TTL)):
        return True

    if user_id in project['owners_ids']:
        return True

    raise Forbidden('FORBIDDEN')


@blueprint.route('/encrypted/taskpayload/<int:project_id>/<int:task_id>')
@no_cache
@login_required
def encrypted_task_payload(project_id, task_id):
    """Proxy to decrypt encrypted task payload"""
    current_app.logger.info('Project id {}, task id {}, decrypt task payload.'.format(project_id, task_id))
    signature = request.args.get('task-signature')
    if not signature:
        current_app.logger.exception('Project id {}, task id {} has no signature.'.format(project_id, task_id))
        raise Forbidden('No signature')

    size_signature = len(signature)
    if size_signature > TASK_SIGNATURE_MAX_SIZE:
        current_app.logger.exception(
            'Project id {}, task id {} invalid task signature. Signature length {} exceeds max allowed length {}.' \
                .format(project_id, task_id, size_signature, TASK_SIGNATURE_MAX_SIZE))
        raise Forbidden('Invalid signature')

    project = get_project_data(project_id)
    if not project:
        current_app.logger.exception('Invalid project id {}.'.format(project_id, task_id))
        raise BadRequest('Invalid Project')

    timeout = project['info'].get('timeout', ContributionsGuard.STAMP_TTL)

    payload = signer.loads(signature, max_age=timeout)
    task_id = payload.get('task_id', 0)

    validate_task(project, task_id, current_user.id)

    ## decrypt encrypted task data under private_json__encrypted_payload
    try:
        secret = get_encryption_key(project)
        task = task_repo.get_task(task_id)
        content = task.info.get('private_json__encrypted_payload')
        if content:
            cipher = AESWithGCM(secret)
            content = cipher.decrypt(content)
        else:
            content = ''
    except Exception as e:
        current_app.logger.exception('Project id {} task {} decrypt encrypted data {}'.format(project_id, task_id, e))
        raise InternalServerError('An Error Occurred')

    response = Response(content, content_type='application/json')
    return response
