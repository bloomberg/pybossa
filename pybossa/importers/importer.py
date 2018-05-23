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

from flask import current_app
from flask.ext.babel import gettext
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
from flask import current_app
from pybossa.util import check_password_strength, valid_or_no_s3_bucket
from flask.ext.login import current_user
from werkzeug.datastructures import MultiDict
import copy
import json
from pybossa.util import delete_import_csv_file

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

    def create_tasks(self, task_repo, project, **form_data):
        """Create tasks."""
        from pybossa.model.task import Task
        """Create tasks from a remote source using an importer object and
        avoiding the creation of repeated tasks"""
        empty = True
        n = 0
        importer = self._create_importer_for(**form_data)
        tasks = importer.tasks()
        import_headers = importer.headers()
        mismatch_headers = []

        if import_headers:
            msg = None
            if not project:
                msg = gettext('Could not load project info')
            else:
                task_presenter_headers = project.get_presenter_headers()
                mismatch_headers = [header for header in task_presenter_headers
                                    if header not in import_headers]

            if mismatch_headers:
                msg = 'Imported columns do not match task presenter code. '
                additional_msg = 'Mismatched columns: {}'.format((', '.join(mismatch_headers))[:80])
                current_app.logger.error(msg)
                current_app.logger.error(', '.join(mismatch_headers))
                msg += additional_msg

            if msg:
                # Failed validation
                current_app.logger.error(msg)
                return ImportReport(message=msg, metadata=None, total=0)

        s3_bucket_failures = 0
        n_answers = project.get_default_n_answers()
        for task_data in tasks:
            task = Task(project_id=project.id, n_answers=n_answers)
            [setattr(task, k, v) for k, v in task_data.iteritems()]
            found = task_repo.find_duplicate(project_id=project.id,
                                             info=task.info)
            if found is None:
                if valid_or_no_s3_bucket(task.info):
                    task_repo.save(task)
                    n += 1
                    empty = False
                else:
                    s3_bucket_failures += 1
                    current_app.logger.error('Invalid S3 bucket. project id: {}, task info: {}'.format(project.id, task.info))

        additional_msg = ' {} task import failed due to invalid S3 bucket.'\
                            .format(s3_bucket_failures) if s3_bucket_failures else ''
        if form_data.get('type') == 'localCSV':
            csv_filename = form_data.get('csv_filename')
            delete_import_csv_file(csv_filename)

        if empty:
            msg = gettext('It looks like there were no new records to import.')
            msg += additional_msg
            return ImportReport(message=msg, metadata=None, total=n)
        metadata = importer.import_metadata()
        msg = str(n) + " " + gettext('new tasks were imported successfully ')
        if n == 1:
            msg = str(n) + " " + gettext('new task was imported successfully ')
        msg += additional_msg

        report = ImportReport(message=msg, metadata=metadata, total=n)
        return report

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
        return self._importers.keys()

    def get_autoimporter_names(self):
        """Get autoimporter names."""
        no_autoimporters = ('dropbox', 's3')
        return [name for name in self._importers.keys() if name not in no_autoimporters]

    def set_importers(self, importers):
        self._importers = \
            {key: val for key, val in self._importers.iteritems()
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

    def get_all_importer_names(self):
        """Get all importer names."""
        return self._importers.keys()

    def _valid_user_data(self, user_data):
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
        form_data['confirm'] = user_data['password']
        form_data['project_slug'] = form_data.pop('project_slugs', [])

        form = RegisterFormWithUserPrefMetadata(MultiDict(form_data))
        form.set_upref_mdata_choices()
        form.project_slug.choices = get_project_choices()
        return form.validate(), form.errors

    def create_users(self, user_repo, **form_data):
        """Create users from a remote source using an importer object and
        avoiding the creation of repeated users"""

        from pybossa.view.account import create_account

        n = 0
        failed_users = 0
        invalid_values = set()
        importer = self._create_importer_for(**form_data)
        for user_data in importer.users():
            found = user_repo.search_by_email(email_addr=user_data['email_addr'].lower())
            if not found:
                full_name = user_data['fullname']
                project_slugs = user_data.get('project_slugs')
                valid, errors = self._valid_user_data(user_data)
                if not valid:
                    failed_users += 1
                    current_app.logger.error(u'Failed to import user {}, {}'
                        .format(full_name, errors))
                    try:
                        for k in errors.keys():
                            invalid_values.add(k)
                    except AttributeError as e:
                        pass
                    continue
                user_data['metadata']['admin'] = current_user.name
                create_account(user_data, project_slugs=project_slugs)
                n += 1
        if n > 0:
            msg = str(n) + " " + gettext('new users were imported successfully. ')
        else:
            msg = gettext('It looks like there were no new users created. ')

        if failed_users:
            msg += str(failed_users) + gettext(' user import failed for incorrect values of ') + ', '.join(invalid_values) + '.'
        return msg
