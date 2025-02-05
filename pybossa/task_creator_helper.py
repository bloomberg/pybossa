# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2019 Scifabric LTD.
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
"""Module with PyBossa create task helper."""
from flask import current_app
import hashlib
import copy
from flask import url_for
import json
import requests
from six import string_types
from boto.exception import S3ResponseError
from werkzeug.exceptions import InternalServerError, NotFound
from pybossa.util import get_time_plus_delta_ts
from pybossa.cloud_store_api.s3 import upload_json_data, get_content_from_s3
from pybossa.cloud_store_api.s3 import get_content_and_key_from_s3
from pybossa.encryption import AESWithGCM


TASK_PRIVATE_GOLD_ANSWER_FILE_NAME = 'task_private_gold_answer.json'
TASK_GOLD_ANSWER_URL_KEY = 'gold_ans__upload_url'


def encrypted():
    return current_app.config.get('ENABLE_ENCRYPTION')


def bucket_name():
    return current_app.config.get("S3_REQUEST_BUCKET_V2") or current_app.config.get("S3_REQUEST_BUCKET")


def s3_conn_type():
    return current_app.config.get('S3_CONN_TYPE_V2') or current_app.config.get('S3_CONN_TYPE')


def get_task_expiration(expiration, create_time):
    """
    Given current task expiration, compute new expiration based on
    1. task creation date and 2. max allowed task expiration
    do that task expiration cannot be set beyond max task expiration
    from task creation date
    """
    max_expiration_days = current_app.config.get('TASK_EXPIRATION', 60)
    max_expiration = get_time_plus_delta_ts(create_time, days=max_expiration_days)

    if expiration and isinstance(expiration, string_types):
        max_expiration = max_expiration.isoformat()

    expiration = expiration or max_expiration
    return min(expiration, max_expiration)


def set_gold_answers(task, gold_answers):
    if not gold_answers:
        return
    if encrypted():
        url = upload_files_priv(task, task.project_id, gold_answers, TASK_PRIVATE_GOLD_ANSWER_FILE_NAME)['externalUrl']
        gold_answers = dict([(TASK_GOLD_ANSWER_URL_KEY, url)])

    task.gold_answers = gold_answers
    task.calibration = 1
    task.exported = True
    if task.state == 'completed':
        task.state = 'ongoing'


def upload_files_priv(task, project_id, data, file_name):
    bucket = bucket_name()

    # hashlib.md5() accepts bytes only
    task_hash = hashlib.md5(str(task).encode()).hexdigest()

    path = "{}/{}".format(project_id, task_hash)
    store = s3_conn_type()
    values = dict(
        store=store,
        bucket=bucket,
        project_id=project_id,
        path='{}/{}'.format(task_hash, file_name)
    )
    file_url = url_for('fileproxy.encrypted_file', **values)
    conn_name = "S3_TASK_REQUEST_V2" if store == current_app.config.get("S3_CONN_TYPE_V2") else "S3_TASK_REQUEST"
    internal_url = upload_json_data(
        bucket=bucket,
        json_data=data,
        upload_path=path,
        file_name=file_name,
        encryption=True,
        conn_name=conn_name
    )
    return {'externalUrl': file_url, 'internalUrl': internal_url}


def get_gold_answers(task):
    gold_answers = task.gold_answers

    if not encrypted() or gold_answers is None:
        return gold_answers

    url = gold_answers.get(TASK_GOLD_ANSWER_URL_KEY)
    if not url:
        raise Exception('Cannot retrieve Private Gigwork gold answers for task id {}. URL is missing.'.format(task.id))

    # The task instance here is not the same as the one that was used to generate the hash
    # in the upload url. So we can't regenerate that hash here, and instead we have to parse it
    # from the url.

    parts = url.split('/')
    store = parts[3] if len(parts) > 3 and parts[1] == "fileproxy" and parts[2] == "encrypted" else None
    conn_name = "S3_TASK_REQUEST_V2" if store == current_app.config.get("S3_CONN_TYPE_V2") else "S3_TASK_REQUEST"
    key_name = '/{}/{}/{}'.format(*parts[-3:])
    current_app.logger.info("gold_answers url %s, store %s, conn_name %s, key %s", url, store, conn_name, key_name)
    decrypted = get_content_from_s3(s3_bucket=parts[-4], path=key_name, conn_name=conn_name, decrypt=True)
    return json.loads(decrypted)


def get_path(dict_, path):
    if not path:
        return dict_
    return get_path(dict_[path[0]], path[1:])


def get_secret_from_vault(project_encryption):
    config = current_app.config['VAULT_CONFIG']
    res = requests.get(config['url'].format(**project_encryption), **config['request'])
    res.raise_for_status()
    data = res.json()
    try:
        return get_path(data, config['response'])
    except Exception:
        raise RuntimeError(get_path(data, config['error']))


def get_project_encryption(project):
    encryption_jpath = current_app.config.get('ENCRYPTION_CONFIG_PATH')
    if not encryption_jpath:
        return None
    data = project['info']
    for segment in encryption_jpath:
        data = data.get(segment, {})
    return data


def get_encryption_key(project):
    project_encryption = get_project_encryption(project)
    if project_encryption:
        return get_secret_from_vault(project_encryption)


def read_encrypted_file(store, project, bucket, key_name):
    conn_name = "S3_TASK_REQUEST_V2" if store == current_app.config.get("S3_CONN_TYPE_V2") else "S3_TASK_REQUEST"
    ## download file
    if bucket not in [current_app.config.get("S3_REQUEST_BUCKET"), current_app.config.get("S3_REQUEST_BUCKET_V2")]:
        secret = get_encryption_key(project)
    else:
        secret = current_app.config.get('FILE_ENCRYPTION_KEY')

    try:
        decrypted, key = get_content_and_key_from_s3(
            bucket, key_name, conn_name, decrypt=secret, secret=secret)
    except S3ResponseError as e:
        current_app.logger.exception('Project id {} get task file {} {}'.format(project.id, key_name, e))
        if e.error_code == 'NoSuchKey':
            raise NotFound('File Does Not Exist')
        else:
            raise InternalServerError('An Error Occurred')
    return decrypted, key


def generate_checksum(project, task):
    from pybossa.cache.projects import get_project_data
    from pybossa.core import private_required_fields

    if not (task and isinstance(task, dict) and "info" in task):
        return

    if not project:
        return

    task_info = task["info"]
    dup_task_config = project.info.get("duplicate_task_check")
    if not dup_task_config:
        return

    dup_fields_configured = dup_task_config.get("duplicate_fields", [])
    # include all task_info fields with no field configured under duplicate_fields

    task_contents = {}
    if current_app.config.get("PRIVATE_INSTANCE"):
        # csv import under private instance, may contain private data under _priv cols
        # prior to this call, sucn _priv columns are combined together into task.private_fields
        # collect fieldname and value from private_fields that are not part of task.info
        private_fields = task.get('private_fields', None)
        if private_fields:
            for field, value in private_fields.items():
                task_contents[field] = value

        for field, value in task_info.items():
            # private required fields are excluded from building duplicate checksum
            if field in private_required_fields:
                continue

            if field.endswith("__upload_url"):
                tokens = value.split("/")
                count_slash = value.count("/")
                if count_slash >= 6 and tokens[1] == "fileproxy" and tokens[2] == "encrypted":
                    store = tokens[3]
                    bucket = tokens[4]
                    project_id = int(tokens[5])
                    if project_id != project.id:
                        current_app.logger.info("error computing duplicate checksum. incorrect project id in url path. expected project id %d, url %s", project.id, value)
                        continue

                    filename = "/".join((tokens[6:]))
                    path = f"{project_id}/{filename}"
                    content, _ = read_encrypted_file(store, project, bucket, path)
                    try:
                        content = json.loads(content)
                        task_contents.update(content)
                    except Exception as e:
                        current_app.logger.info("duplicate task checksum error parsing task payload for project %d, %s", project.id, str(e))
                else:
                    current_app.logger.info("error parsing task data url to compute duplicate checksum %s, %s", field, value)
            elif field == "private_json__encrypted_payload":
                secret = get_encryption_key(project)
                cipher = AESWithGCM(secret) if secret else None
                encrypted_content = task_info.get("private_json__encrypted_payload")
                content = cipher.decrypt(encrypted_content) if cipher else encrypted_content
                content = json.loads(content)
                task_contents.update(content)
            else:
                task_contents[field] = value
    else:
        # public instance has all task fields under task_info
        task_contents = task_info

    checksum_fields = task_contents.keys() if not dup_fields_configured else dup_fields_configured
    try:
        checksum_payload = {field:task_contents[field] for field in checksum_fields}
        checksum = hashlib.sha256()
        checksum.update(json.dumps(checksum_payload, sort_keys=True).encode("utf-8"))
        checksum_value = checksum.hexdigest()
        return checksum_value
    except KeyError as e:
        private_fields = task.get('private_fields', None)
        task_payload = copy.deepcopy(task_info)
        task_payload["private_fields_keys"] = list(private_fields.keys()) if private_fields else []
        current_app.logger.info("error computing duplicate checksum. project id %d, error %s, task payload", project.id, str(e), json.dumps(task_payload))
        raise Exception(f"Error generating duplicate checksum due to missing checksum configured fields {checksum_fields}")
