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

from collections import defaultdict
from flask import current_app
from flask_babel import gettext
from .csv import BulkTaskCSVImport, BulkTaskGDImport, BulkTaskLocalCSVImport
from .dropbox import BulkTaskDropboxImport
from .flickr import BulkTaskFlickrImport
from .twitterapi import BulkTaskTwitterImport
from .youtubeapi import BulkTaskYoutubeImport
from .epicollect import BulkTaskEpiCollectPlusImport
from .iiif import BulkTaskIIIFImporter
from .s3 import BulkTaskS3Import
from .base import BulkImportException
from .usercsv import BulkUserCSVImport
from pybossa.util import (check_password_strength, valid_or_no_s3_bucket)
from flask_login import current_user
from werkzeug.datastructures import MultiDict
import copy
import json
from pybossa.util import delete_import_csv_file
from pybossa.cloud_store_api.s3 import upload_json_data
import hashlib
from flask import url_for
from pybossa.task_creator_helper import set_gold_answers, upload_files_priv, get_task_expiration
from pybossa.data_access import data_access_levels
from pybossa.model import make_timestamp
from pybossa.task_creator_helper import generate_checksum


def validate_s3_bucket(task, *args):
    valid = valid_or_no_s3_bucket(task.info)
    if not valid:
        current_app.logger.error('Invalid S3 bucket. project id: {}, task info: {}'.format(task.project_id, task.info))
    return valid


def validate_priority(task, *args):
    if task.priority_0 is None:
        return True
    try:
        float(task.priority_0)
        return True
    except Exception:
        return False


def validate_n_answers(task, *args):
    try:
        int(task.n_answers)
        return True
    except Exception:
        return False

def validate_state(task, *args):
    return task.state in ['enrich', 'ongoing', None]

def validate_can_enrich(task, enrichment_output_fields, *args):
    return task.state != 'enrich' or enrichment_output_fields

def validate_no_enrichment_output_field(task, enrichment_output_fields, *args):
    # If not enriching then they are allowed to import the enrichment output.
    if task.state != 'enrich':
        return True

    return not any(enrichment_output in task.info for enrichment_output in enrichment_output_fields)

def get_enrichment_output_fields(project):
    enrichments = project.info.get('enrichments', [])
    return {enrichment.get('out_field_name') for enrichment in enrichments}

class TaskImportValidator(object):

    validations = {
        'invalid priority': validate_priority,
        'invalid s3 bucket': validate_s3_bucket,
        'invalid n_answers': validate_n_answers,
        'invalid state': validate_state,
        'no enrichment config': validate_can_enrich,
        'ernichment output in import': validate_no_enrichment_output_field
    }

    def __init__(self, enrichment_output_fields):
        self.errors = defaultdict(int)
        self._enrichment_output_fields = enrichment_output_fields

    def validate(self, task):
        for error, validator in self.validations.items():
            if not validator(task, self._enrichment_output_fields):
                self.errors[error] += 1
                current_app.logger.info(f"importing task validation: {error}")
                return False
        return True

    def add_error(self, key):
        self.errors[key] = self.errors.get(key, 0) + 1

    def __str__(self):
        msg = '{} task import failed due to {}.'
        return '\n'.join(msg.format(n, error) for error, n in self.errors.items())


class Importer(object):

    """Class to import data."""

    def __init__(self):
        """Init method."""
        self._importers = dict(csv=BulkTaskCSVImport,
                               gdocs=BulkTaskGDImport,
                               epicollect=BulkTaskEpiCollectPlusImport,
                               s3=BulkTaskS3Import,
                               localCSV=BulkTaskLocalCSVImport,
                               iiif=BulkTaskIIIFImporter)
        self._importer_constructor_params = dict()

    def register_flickr_importer(self, flickr_params):
        """Register Flickr importer."""
        self._importers['flickr'] = BulkTaskFlickrImport
        self._importer_constructor_params['flickr'] = flickr_params

    def register_dropbox_importer(self):
        """Register Dropbox importer."""
        self._importers['dropbox'] = BulkTaskDropboxImport

    def register_twitter_importer(self, twitter_params):
        self._importers['twitter'] = BulkTaskTwitterImport
        self._importer_constructor_params['twitter'] = twitter_params

    def register_youtube_importer(self, youtube_params):
        self._importers['youtube'] = BulkTaskYoutubeImport
        self._importer_constructor_params['youtube'] = youtube_params

    def upload_private_data(self, task, project_id):
        private_fields = task.pop('private_fields', None)
        if not private_fields:
            return
        file_name = 'task_private_data.json'
        urls = upload_files_priv(task, project_id, private_fields, file_name)
        use_file_url = (task.get('state') == 'enrich')
        task['info']['private_json__upload_url'] = urls if use_file_url else urls['externalUrl']

    def _validate_headers(self, importer, project, **form_data):
        validate_against_task_presenter = form_data.pop('validate_tp', True)
        import_fields = importer.fields()

        def get_error_message():
            if not validate_against_task_presenter:
                return ""
            if not import_fields:
                return ""
            if not project:
                return gettext('Could not load project info')

            task_presenter_fields = project.get_presenter_field_set()
            # Check that all task fields used in task presenter are also in import.
            # We exclude enrichment output from the check since we expect those fields to be generated
            # by enrichment instead of import.
            fields_not_in_import = task_presenter_fields - import_fields - get_enrichment_output_fields(project)

            if not fields_not_in_import:
                return ""

            msg = 'Task presenter code uses fields not in import. '
            additional_msg = 'Fields missing from import: {}'.format((', '.join(fields_not_in_import))[:80])
            current_app.logger.error(msg)
            current_app.logger.error(', '.join(fields_not_in_import))
            return msg + additional_msg

        reserved_cols = []
        task_reserved_cols = current_app.config.get("TASK_RESERVED_COLS", [])
        if hasattr(import_fields, "__iter__"):
            reserved_cols += [k for k in import_fields if k in task_reserved_cols]

        msg = ""
        if reserved_cols:
            reserved_cols_in_csv = ", ".join(reserved_cols)
            msg += f"Reserved columns {reserved_cols_in_csv} not allowed. "

        msg += get_error_message()

        if msg:
            # Failed validation
            current_app.logger.error(msg)
            return ImportReport(message=msg, metadata=None, total=0)

    def create_tasks(self, task_repo, project, importer=None, **form_data):
        """Create tasks."""
        from pybossa.model.task import Task
        from pybossa.cache import projects as cached_projects

        """Create tasks from a remote source using an importer object and
        avoiding the creation of repeated tasks"""
        num = 0
        importer = importer or self._create_importer_for(**form_data)
        tasks = importer.tasks()
        total_tasks_count = len(tasks) if isinstance(tasks, list) else 0
        header_report = self._validate_headers(importer, project, **form_data)
        if header_report:
            return header_report
        msg = ''
        validator = TaskImportValidator(get_enrichment_output_fields(project))
        n_answers = project.get_default_n_answers()
        completed_tasks = project.info.get("duplicate_task_check", {}).get("completed_tasks", False)
        try:
            for task_data in tasks:
                # As tasks are getting created, pass current date as create_date
                create_date = make_timestamp()
                task_data['expiration'] = get_task_expiration(task_data.get('expiration'), create_date)

                dup_checksum = generate_checksum(project_id=project.id, task=task_data)
                self.upload_private_data(task_data, project.id)
                task = Task(project_id=project.id, n_answers=n_answers, dup_checksum=dup_checksum)
                [setattr(task, k, v) for k, v in task_data.items()]

                gold_answers = task_data.pop('gold_answers', None)
                set_gold_answers(task, gold_answers)

                found = task_repo.find_duplicate(project_id=project.id,
                    info=task.info,
                    dup_checksum=task.dup_checksum,
                    completed_tasks=completed_tasks
                )
                if found is not None:
                    current_app.logger.info("Project %d, task checksum %s. Duplicate task found with task id %d", project.id, task.dup_checksum, found)
                    continue
                if not validator.validate(task):
                    continue
                try:
                    num += 1
                    task_repo.save(task, clean_project=False)
                except Exception as e:
                    current_app.logger.exception(msg)
                    validator.add_error(str(e))
        finally:
            cached_projects.clean_project(project.id)

        if form_data.get('type') == 'localCSV':
            csv_filename = form_data.get('csv_filename')
            delete_import_csv_file(csv_filename)

        metadata = importer.import_metadata()
        if num == 0:
            msg = gettext('It looks like there were no new records to import. ')
        elif num == 1:
            msg = str(num) + " " + gettext('new task was imported successfully. ')
        else:
            msg = str(num) + " " + gettext('new tasks were imported successfully. ')
        if num > 0 and num < total_tasks_count:
            msg += str(total_tasks_count - num) + " " + gettext('tasks not imported. ')
        msg += str(validator)
        if data_access_levels and 'data_access' in importer.headers():
            msg += gettext('Task data_access column will not impact data classification. This is done at project level only.')
        return ImportReport(message=msg, metadata=metadata, total=num)

    def count_tasks_to_import(self, **form_data):
        """Count tasks to import."""
        return self._create_importer_for(**form_data).count_tasks()

    def _create_importer_for(self, **form_data):
        """Create importer."""
        importer_id = form_data.get('type')
        params = self._importer_constructor_params.get(importer_id) or {}
        params.update(form_data)
        del params['type']
        return self._importers[importer_id](**params)

    def get_all_importer_names(self):
        """Get all importer names."""
        return list(self._importers.keys())

    def get_autoimporter_names(self):
        """Get autoimporter names."""
        no_autoimporters = ('dropbox', 's3')
        return [name for name in self._importers.keys() if name not in no_autoimporters]

    def set_importers(self, importers):
        self._importers = \
            {key: val for key, val in self._importers.items()
             if key in importers}


class ImportReport(object):

    def __init__(self, message, metadata, total):
        self._message = message
        self._metadata = metadata
        self._total = total

    @property
    def message(self):
        return self._message

    @property
    def metadata(self):
        return self._metadata

    @property
    def total(self):
        return self._total


class UserImporter(object):

    """Class to import data."""

    def __init__(self):
        """Init method."""
        self._importers = dict(usercsvimport=BulkUserCSVImport)
        self._importer_constructor_params = dict()

    def count_users_to_import(self, **form_data):
        """Count number of users to import."""
        return self._create_importer_for(**form_data).count_users()

    def _create_importer_for(self, **form_data):
        """Create importer."""
        importer_id = form_data.get('type')
        params = self._importer_constructor_params.get(importer_id) or {}
        params.update(form_data)
        del params['type']
        return self._importers[importer_id](**params)

    def delete_file(self, **form_data):
        self._create_importer_for(**form_data)._delete_file()

    def get_all_importer_names(self):
        """Get all importer names."""
        return list(self._importers.keys())

    def _create_user_form(self, user_data):
        from pybossa.view.account import get_project_choices
        from pybossa.forms.forms import RegisterFormWithUserPrefMetadata

        form_data = copy.deepcopy(user_data)
        upref = form_data.pop('user_pref', {})
        mdata = form_data.pop('metadata', {})

        if not isinstance(upref, dict):
            err = dict(user_pref='incorrect value')
            return False, err
        if not isinstance(mdata, dict) or \
            'user_type' not in mdata:
            err = dict(metadata='missing or incorrect user_type value')
            return False, err

        form_data['languages'] = upref.get('languages', [])
        form_data['locations'] = upref.get('locations', [])
        form_data['user_type'] = mdata.get('user_type')
        form_data.pop('info', None)
        form_data['confirm'] = user_data.get('password')
        form_data['project_slug'] = form_data.pop('project_slugs', [])

        form = RegisterFormWithUserPrefMetadata(MultiDict(form_data))
        form.generate_password()
        form.set_upref_mdata_choices()
        form.project_slug.choices = get_project_choices()
        return form

    def create_users(self, user_repo, **form_data):
        """Create users from a remote source using an importer object and
        avoiding the creation of repeated users"""

        from pybossa.view.account import create_account

        new_users = 0
        enabled_users = 0
        failed_users = 0
        invalid_values = set()
        importer = self._create_importer_for(**form_data)
        for user_data in importer.users():
            found = user_repo.search_by_email(email_addr=user_data['email_addr'].lower())
            if not found:
                full_name = user_data['fullname']
                project_slugs = user_data.get('project_slugs')
                form = self._create_user_form(user_data)
                if not form.validate():
                    failed_users += 1
                    current_app.logger.error('Failed to import user {}, {}'
                        .format(full_name, form.errors))
                    invalid_values.update(list(form.errors.keys()))
                    continue
                user_data['metadata']['admin'] = current_user.name
                user_data['password'] = form.password.data
                create_account(user_data, project_slugs=project_slugs)
                new_users += 1
            else:
                if not found.enabled:
                    found.enabled = True
                    user_repo.update(found)
                    enabled_users += 1
        if new_users or enabled_users:
            msg = ''
            if new_users:
                msg = str(new_users) + " " + gettext('new users were imported successfully. ')
            if enabled_users:
                msg += str(enabled_users) + " " + gettext('users were re-enabled.')
        else:
            msg = gettext('It looks like there were no new users created. ')

        if failed_users:
            msg += str(failed_users) + gettext(' user import failed for incorrect values of ') + ', '.join(invalid_values) + '.'
        return msg
