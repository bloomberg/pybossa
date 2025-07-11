import io
import os
import re
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
import boto
from flask import current_app as app
from werkzeug.utils import secure_filename
import magic
from werkzeug.exceptions import BadRequest
from pybossa.cloud_store_api.connection import create_connection
from pybossa.encryption import AESWithGCM
import json
from time import perf_counter
import time
from datetime import datetime, timedelta


allowed_mime_types = ['application/pdf',
                      'text/csv',
                      'text/richtext',
                      'text/tab-separated-values',
                      'text/xml',
                      'text/plain',
                      'application/oda',
                      'text/html',
                      'application/xml',
                      'image/jpeg',
                      'image/png',
                      'image/bmp',
                      'image/x-ms-bmp',
                      'image/gif',
                      'application/zip',
                      'application/vnd.ms-excel',
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                      'audio/mpeg',
                      'audio/wav',
                      'application/json',
                      'application/csv']


DEFAULT_CONN = 'S3_DEFAULT'


def check_type(filename):
    mime_type = magic.from_file(filename, mime=True)
    if mime_type not in allowed_mime_types:
        raise BadRequest('File type not supported for {}: {}'.format(filename, mime_type))


def validate_directory(directory_name):
    invalid_chars = '[^\w\/]'
    if re.search(invalid_chars, directory_name):
        raise RuntimeError('Invalid character in directory name')


def tmp_file_from_string(string):
    """
    Create a temporary file with the given content
    """
    tmp_file = NamedTemporaryFile(delete=False)
    try:
        with io.open(tmp_file.name, 'w', encoding='utf8') as fp:
            fp.write(string)
    except Exception as e:
        os.unlink(tmp_file.name)
        raise e
    return tmp_file


def s3_upload_from_string(s3_bucket, string, filename, headers=None,
                          directory='', file_type_check=True,
                          return_key_only=False, conn_name=DEFAULT_CONN,
                          with_encryption=False, upload_root_dir=None):
    """
    Upload a string to s3
    """
    tmp_file = tmp_file_from_string(string)
    headers = headers or {}
    return s3_upload_tmp_file(
            s3_bucket, tmp_file, filename, headers, directory, file_type_check,
            return_key_only, conn_name, with_encryption, upload_root_dir)


def s3_upload_file_storage(s3_bucket, source_file, headers=None, directory='',
                           file_type_check=True, return_key_only=False,
                           conn_name=DEFAULT_CONN, with_encryption=False):
    """
    Upload a werzkeug FileStorage content to s3
    The FileStorage content can only be BytesIO
    """
    filename = source_file.filename
    headers = headers or {}
    headers['Content-Type'] = source_file.content_type

    tmp_file = NamedTemporaryFile(delete=False)

    # When using the file name (tmp_file.name), save method in the FileStorage
    # class can only open the file in binary mode
    source_file.save(tmp_file.name)
    tmp_file.flush()

    upload_root_dir = app.config.get('S3_UPLOAD_DIRECTORY')
    return s3_upload_tmp_file(
            s3_bucket, tmp_file, filename, headers, directory, file_type_check,
            return_key_only, conn_name, with_encryption, upload_root_dir)


def s3_upload_tmp_file(s3_bucket, tmp_file, filename,
                       headers, directory='', file_type_check=True,
                       return_key_only=False, conn_name=DEFAULT_CONN,
                       with_encryption=False,
                       upload_root_dir=None):
    """
    Upload the content of a temporary file to s3 and delete the file
    """
    try:
        if file_type_check:
            check_type(tmp_file.name)
        content = tmp_file.read()
        if with_encryption:
            secret = app.config.get('FILE_ENCRYPTION_KEY')
            cipher = AESWithGCM(secret)
            content = cipher.encrypt(content)

        # make sure content is a bytes string
        if type(content) == str:
            content = content.encode()
        fp = io.BytesIO(content)  # BytesIO accepts bytes string
        url = s3_upload_file(s3_bucket, fp, filename, headers, upload_root_dir,
                             directory, return_key_only, conn_name)
        bcosv2_prod_util_url = app.config.get('BCOSV2_PROD_UTIL_URL')

        # generate url path to be stored as metadata
        # which can be different from actual uploaded url
        # and is based upon the type of uploaded url path
        meta_url = url
        if bcosv2_prod_util_url and url.startswith(bcosv2_prod_util_url):
            meta_url = url.replace("-util", "")
            app.logger.info("bcosv2 url paths. uploaded path %s, metadata path %s", url, meta_url)

    finally:
        os.unlink(tmp_file.name)
    return meta_url


def form_upload_directory(directory, filename, upload_root_dir):
    validate_directory(directory)
    parts = [upload_root_dir, directory, filename]
    return "/".join(part for part in parts if part)


def s3_upload_file(s3_bucket, source_file, target_file_name,
                   headers, upload_root_dir, directory="",
                   return_key_only=False, conn_name=DEFAULT_CONN):
    """
    Upload a file-type object to S3
    :param s3_bucket: AWS S3 bucket name
    :param source_file_name: name in local file system of the file to upload
    :param target_file_name: file name as should appear in S3
    :param headers: a dictionary of headers to set on the S3 object
    :param directory: path in S3 where the object needs to be stored
    :param return_key_only: return key name instead of full url
    """
    filename = secure_filename(target_file_name)
    upload_key = form_upload_directory(directory, filename, upload_root_dir)
    conn_kwargs = app.config.get(conn_name, {})
    conn = create_connection(**conn_kwargs)
    bucket = conn.get_bucket(s3_bucket, validate=False)

    assert(len(upload_key) < 256)
    key = bucket.new_key(upload_key)

    key.set_contents_from_file(
        source_file, headers=headers,
        policy='bucket-owner-full-control')

    if return_key_only:
        return key.name
    url = key.generate_url(0, query_auth=False)
    return url.split('?')[0]


def get_s3_bucket_key(s3_bucket, s3_url, conn_name=DEFAULT_CONN):
    conn_kwargs = app.config.get(conn_name, {})
    conn = create_connection(**conn_kwargs)
    bucket = conn.get_bucket(s3_bucket, validate=False)
    obj = urlparse(s3_url)
    path = obj.path
    key = bucket.get_key(path, validate=False)
    return bucket, key


def get_file_from_s3(s3_bucket, path, conn_name=DEFAULT_CONN, decrypt=False):
    content = get_content_from_s3(s3_bucket, path, conn_name, decrypt)
    temp_file = NamedTemporaryFile()
    if type(content) == str:
        content = content.encode()
    temp_file.write(content)
    temp_file.seek(0)
    return temp_file


def get_content_and_key_from_s3(s3_bucket, path, conn_name=DEFAULT_CONN,
        decrypt=False, secret=None):
    begin_time = perf_counter()
    _, key = get_s3_bucket_key(s3_bucket, path, conn_name)
    content = key.get_contents_as_string()
    duration = perf_counter() - begin_time
    file_path = f"{s3_bucket}/{path}"
    app.logger.info("get_content_and_key_from_s3. Load file contents %s duration %f seconds", file_path, duration)
    begin_time = perf_counter()
    if decrypt:
        if not secret:
            secret = app.config.get('FILE_ENCRYPTION_KEY')
        cipher = AESWithGCM(secret)
        content = cipher.decrypt(content)
        duration = perf_counter() - begin_time
        app.logger.info("get_content_and_key_from_s3. file %s decryption duration %f seconds", file_path, duration)
    else:
        app.logger.info("get_content_and_key_from_s3. file %s no decryption duration %f seconds", file_path, duration)
    try:
        if type(content) == bytes:
            content = content.decode()
            app.logger.info("get_content_and_key_from_s3. contents decoded")
    except (UnicodeDecodeError, AttributeError) as e:
        app.logger.info("get_content_and_key_from_s3. file %s exception %s", file_path, str(e))
        pass
    return content, key


def get_content_from_s3(s3_bucket, path, conn_name=DEFAULT_CONN, decrypt=False):
    return get_content_and_key_from_s3(s3_bucket, path, conn_name, decrypt)[0]


def delete_file_from_s3(s3_bucket, s3_url, conn_name=DEFAULT_CONN):
    headers = {}
    try:
        bucket, key = get_s3_bucket_key(s3_bucket, s3_url, conn_name)
        bucket.delete_key(key.name, version_id=key.version_id, headers=headers)
    except boto.exception.S3ResponseError:
        app.logger.exception('S3: unable to delete file {0}'.format(s3_url))


def upload_json_data(json_data, upload_path, file_name, encryption,
    conn_name, upload_root_dir=None, bucket=None):
    content = json.dumps(json_data, ensure_ascii=False)
    if not bucket:
        bucket = app.config.get("S3_BUCKET_V2") if app.config.get("S3_CONN_TYPE_V2") else app.config.get("S3_BUCKET")

    return s3_upload_from_string(bucket, content, file_name, file_type_check=False,
        directory=upload_path, conn_name=conn_name,
        with_encryption=encryption, upload_root_dir=upload_root_dir)


def upload_email_attachment(content, filename, user_email, project_id=None):
    """Upload file to storage location and generate url to download file later"""

    # generate signature for authorised access to the attachment
    from pybossa.core import signer
    payload = {"project_id": project_id} if project_id else {}
    payload["user_email"] = user_email
    signature = signer.dumps(payload)

    # upload contents to s3 storage
    bucket_name = app.config.get("S3_REQUEST_BUCKET_V2")
    conn_name = "S3_TASK_REQUEST_V2"
    if not bucket_name:
        raise RuntimeError("S3_REQUEST_BUCKET_V2 is not configured")

    conn_kwargs = app.config.get(conn_name, {})
    conn = create_connection(**conn_kwargs)
    bucket = conn.get_bucket(bucket_name, validate=False)

    # Generate a unique file path using UTC timestamp and secure filename
    timestamp = int(time.time())
    secure_file_name = secure_filename(filename)
    s3_path = f"attachments/{timestamp}-{secure_file_name}"
    app.logger.info("upload email attachment s3 path %s", s3_path)

    # Upload content to S3
    key = bucket.new_key(s3_path)
    key.set_contents_from_string(content)
    server_url = app.config.get('SERVER_URL')
    url = f"{server_url}/attachment/{signature}/{timestamp}-{secure_file_name}"
    app.logger.info("upload email attachment url %s", url)
    return url


def s3_get_email_attachment(path):
    """Download email attachment from storage location"""

    response = {
        "name": "",
        "type": "application/octet-stream",
        "content": b""
    }

    bucket = app.config.get("S3_REQUEST_BUCKET_V2")
    if not bucket:
        return response

    conn_name = "S3_TASK_REQUEST_V2"
    s3_path = f"attachments/{path}"
    content, key = get_content_and_key_from_s3(s3_bucket=bucket, path=s3_path, conn_name=conn_name)
    if content and key:
        app.logger.info("email attachment path %s, s3 file path %s, key name %s, key content_type %s",
                path, s3_path, key.name, key.content_type)
        response["name"] = key.name
        response["type"] = key.content_type
        response["content"] = content
    return response
