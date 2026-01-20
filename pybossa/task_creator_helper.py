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
import os
from flask import current_app
import hashlib
import copy
from flask import url_for
import json
import time
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
    Given current task expiration, compute new expiration based on:
    1. task creation date
    2. default task expiration (if no expiration is provided)
    3. max allowed task expiration (cannot be exceeded)

    Returns the minimum of requested expiration and max allowed expiration.
    If no expiration is provided, uses the default expiration.
    """
    default_expiration_days = current_app.config.get('TASK_EXPIRATION', 60)
    max_expiration_days = current_app.config.get('TASK_MAX_EXPIRATION', 365)

    default_expiration = get_time_plus_delta_ts(create_time, days=default_expiration_days)
    max_expiration = get_time_plus_delta_ts(create_time, days=max_expiration_days)

    if expiration and isinstance(expiration, string_types):
        default_expiration = default_expiration.isoformat()
        max_expiration = max_expiration.isoformat()

    expiration = expiration or default_expiration
    return min(expiration, max_expiration)


def set_gold_answers(task, gold_answers):
    if not gold_answers:
        return

    current_app.logger.info("Setting gold answers for project id %d, task.info: %s, gold_answers: %s",
                            task.project_id, str(task.info), str(gold_answers))
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

    hash_contents = {
        "project_id": project_id,
        "task_info": task.info if hasattr(task, "info") else {},
        "data": data, # could be gold answers / private_fields
        "creation_timestamp": int(time.time() * 1000000)  # microseconds # ensure uniqueness for new tasks
    }
    # Create deterministic hash
    content_str = json.dumps(hash_contents, sort_keys=True, ensure_ascii=False)
    task_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()

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


def get_secret_from_env(project_encryption):
    config = current_app.config['SECRET_CONFIG_ENV']
    if not isinstance(config, dict) or "secret_id_prefix" not in config:
        raise RuntimeError("Env secret configuration is not valid")

    secret_id = config.get("secret_id_prefix")
    proj_secret_id = project_encryption.get(secret_id)
    env_secret_id = f"{secret_id}_{proj_secret_id}"
    current_app.logger.info("get_secret_from_env env_secret_id %s", env_secret_id)
    try:
        return os.environ[env_secret_id]
    except Exception:
        raise RuntimeError(f"Unable to fetch project encryption key from {env_secret_id}")


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
    if not project_encryption:
        return

    secret_from_env = current_app.config.get("SECRET_CONFIG_ENV", False)
    if not secret_from_env:
        current_app.logger.exception('Missing env config SECRET_CONFIG_ENV. Cannot process encryption for Project id %d', project.id)
        raise InternalServerError(f"Unable to fetch encryption key for project id {project.id}")
    return get_secret_from_env(project_encryption)


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


def generate_checksum(project_id, task):
    from pybossa.cache.projects import get_project_data

    if not (task and isinstance(task, dict) and "info" in task):
        return

    project = get_project_data(project_id)
    if not project:
        current_app.logger.info("Duplicate task checksum not generated. Incorrect project id %s", str(project_id))
        return

    # with task payload not proper dict, dup checksum cannot be computed and will be set to null
    if not isinstance(task["info"], dict):
        current_app.logger.info("Duplicate task checksum not generated for project %s. Task.info type is %s, expected dict",
                                str(project_id), str(type(task["info"])))
        return

    # drop reserved columns that are always going to have unique values in
    # certain scenarios as this could miss duplicate task check correctly on
    # remaining fields when all fields are included for duplicate check
    task_reserved_cols = current_app.config.get("TASK_RESERVED_COLS", [])
    task_info = {k:v for k, v in task["info"].items() if k not in task_reserved_cols}

    # include all task_info fields with no field configured under duplicate_fields
    dup_task_config = project.info.get("duplicate_task_check", {})
    dup_fields_configured = dup_task_config.get("duplicate_fields", [])

    task_contents = {}
    if current_app.config.get("PRIVATE_INSTANCE") and dup_task_config:
        task_contents = extract_task_contents_from_files(
            project_id, project, task, task_info
        )
    else:
        # with duplicate check not configured, consider all task fields
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
        current_app.logger.info("error generating duplicate checksum for project id %s, error %s, task payload %s", str(project_id), str(e), json.dumps(task_payload))
        raise Exception(f"Error generating duplicate checksum due to missing checksum configured fields {checksum_fields}")


def extract_task_contents_from_files(project_id, project, task, task_info):
    """
    Extract task contents from files for tasks containing encrypted file references.

    This function processes task info fields and extracts actual content from:
    - Private fields stored separately
    - Encrypted files referenced via __upload_url fields
    - Encrypted payloads in private_json__encrypted_payload

    Args:
        project_id: The project ID
        project: The project data dictionary
        task: The task dictionary containing 'info' and optionally 'private_fields'
        task_info: The filtered task info dictionary (reserved columns removed)

    Returns:
        dict: Task contents with file contents extracted and decrypted
    """
    from pybossa.core import private_required_fields

    task_contents = {}

    # csv import under private instance, may contain private data under _priv cols
    # prior to this call, such _priv columns are combined together into task.private_fields
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
            current_app.logger.info("extract_task_contents_from_files file payload name %s, path %s", field, value)
            tokens = value.split("/")
            count_slash = value.count("/")
            if count_slash >= 6 and tokens[1] == "fileproxy" and tokens[2] == "encrypted":
                store = tokens[3]
                bucket = tokens[4]
                project_id_from_url = int(tokens[5])
                current_app.logger.info("extract_task_contents_from_files file tokens %s", str(tokens))
                if int(project_id) != project_id_from_url:
                    current_app.logger.info("error extracting task contents. incorrect project id in url path. project id expected %s vs actual %s, url %s",
                                            str(project_id), str(project_id_from_url), str(value))
                    continue

                path = "/".join((tokens[5:]))
                try:
                    current_app.logger.info("extract_task_contents_from_files parsed file info. store %s, bucket %s, path %s", store, bucket, path)
                    content, _ = read_encrypted_file(store, project, bucket, path)
                    content = json.loads(content)
                    task_contents.update(content)
                except Exception as e:
                    current_app.logger.info("error extracting task contents with url contents for project %s, %s, %s %s",
                                            str(project_id), field, str(value), str(e))
                    raise Exception(f"Error extracting task contents with url contents. url {field}, {value}")
            else:
                current_app.logger.info("error parsing task data url to extract task contents %s, %s", field, str(value))
        elif field == "private_json__encrypted_payload":
            try:
                secret = get_encryption_key(project)
                cipher = AESWithGCM(secret) if secret else None
                encrypted_content = task_info.get("private_json__encrypted_payload")
                content = cipher.decrypt(encrypted_content) if cipher else encrypted_content
                content = json.loads(content)
                task_contents.update(content)
            except Exception as e:
                current_app.logger.info("error extracting task contents with encrypted payload for project %s, %s, %s %s",
                                        str(project_id), field, str(value), str(e))
                raise Exception(f"Error extracting task contents with encrypted payload. {field}, {value}")
        else:
            task_contents[field] = value

    return task_contents
