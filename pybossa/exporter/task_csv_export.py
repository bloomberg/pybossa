# -*- coding: utf8 -*-
# This file is part of PyBossa.
#
# Copyright (C) 2017 SciFabric LTD.
#
# PyBossa is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PyBossa is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with PyBossa.  If not, see <http://www.gnu.org/licenses/>.
# Cache global variables for timeouts

import json
import tempfile
from contextlib import closing

import pandas as pd

from flask import send_file
from werkzeug.datastructures import FileStorage
from werkzeug.utils import safe_join, secure_filename

from pybossa.core import uploader
from pybossa.exporter.csv_export import CsvExporter
from pybossa.uploader import local
from .export_helpers import browse_tasks_export, filter_task_info_headers


class TaskCsvExporter(CsvExporter):
    """CSV Exporter for exporting ``Task``s and ``TaskRun``s
    for a project.
    """

    @classmethod
    def get_keys(self, row, ty='', parent_key=''):
        """Recursively get keys from a dictionary.
        Nested keys are prefixed with their parents key.
        Ex:
            >>> row = {"a": {"nested_x": "N"},
            ...        "b": 1,
            ...        "c": {
            ...          "nested_y": {"double_nested": "www.example.com"},
            ...          "nested_z": True
            ...       }}
            >>> exp = CsvExporter()
            >>> sorted(exp.get_keys(row, 'taskrun'))
            ['taskrun__a',
             'taskrun__a__nested_x',
             'taskrun__b',
             'taskrun__c',
             'taskrun__c__nested_y',
             'taskrun__c__nested_y__double_nested',
             'taskrun__c__nested_z']
        """
        if ty == '' and parent_key == '':
            _prefix = ''
        else:
            _prefix = '{}__{}'.format(ty, parent_key)

        keys = []
        for key in row.keys():
            keys = keys + [_prefix + key]
            try:
                keys = keys + self.get_keys(row[key], _prefix + key)
            except: pass

        return [str(key) for key in keys]

    @classmethod
    def get_value(cls, row, key):
        """Recursively get value from a dictionary by
        passing an arbitrarily long list of nested keys.
        Ex:
            >>> row = {"a": {"nested_x": "N"},
            ...        "b": 1,
            ...        "c": {
            ...          "nested_y": {"double_nested": "www.example.com"},
            ...          "nested_z": True
            ...       }}
            >>> exp = CsvExporter()
            >>> exp.get_value(row, 'c__nested_y__double_nested'])
            'www.example.com'
        """
        if not isinstance(row, dict):
            return None
        if key in row:
            return row[key]
        splits = key.split('__')
        for i in range(1, len(splits)):
            key1 = '__'.join(splits[:i])
            if key1 in row:
                key2 = '__'.join(splits[i:])
                val = cls.get_value(row[key1], key2)
                if isinstance(val, list):
                    return json.dumps(val)
                if val is not None:
                    return val

    @staticmethod
    def process_filtered_row(row):
        """Normalizes a row returned from a SQL query to
        the same format as that of merging joined domain
        objects.
        """
        def set_nested_value(row, keys, value):
            for key in keys[:-1]:
                row = row.setdefault(key, {})
            row[keys[-1]] = value

        new_row = {}
        for k, v in row.items():
            key_split = k.split('__', 1)
            if len(key_split) > 1 and key_split[0] in ('task', 'user'):
                set_nested_value(new_row, key_split, v)
            new_row[k] = v

        return new_row

    def _format_csv_row(self, row, headers):
        return [self.get_value(row, header.split('__', 1)[1])
                for header in headers]

    @staticmethod
    def flatten(key_value_pairs, key_prefix='', return_value=None):
        return_value = return_value if return_value is not None else {}
        for k, v in key_value_pairs:
            key = k if not key_prefix else '{}__{}'.format(key_prefix, k)
            if isinstance(v, dict):
                iterator = TaskCsvExporter.flatten(iter(v.items()), key, return_value)
            elif isinstance(v, list):
                iterator = TaskCsvExporter.flatten(enumerate(v), key, return_value)
            else:
                iterator = [(key, v)]
            for kk, vv, in iterator:
                yield kk, vv

    def _get_all_headers(self, objs, expanded, table=None):
        """Construct headers to **guarantee** that all headers
        for all tasks are included, regardless of whether
        or not all tasks were imported with the same headers.

        :param objs: an iterable of objects or dicts to
            extract keys from
        :param expanded: determines if joined objects should
            be merged
        :param table: the table that the objects belong to
        :param from_obj: does ``objs`` iterable contain
            domain objects. If it does then different methods
            can be used.
        """
        headers = set()

        for obj in objs:
            headers.update(self.get_keys(obj, table))

        headers = sorted(list(headers))
        return headers

    def _respond_csv(self, ty, project_id, expanded=False, filters=None, disclose_gold=False):
        objs = browse_tasks_export(ty, project_id, expanded, filters, disclose_gold)
        rows = [obj for obj in objs]
        headers = self._get_all_headers(objs=rows, expanded=expanded, table=ty)
        if (filters and 'display_info_columns' in filters and \
            len(filters['display_info_columns']) > 0):
            headers = filter_task_info_headers(headers, filters['display_info_columns'])

        formatted_rows = []
        for row in rows:
            row = self.process_filtered_row(dict(row))
            formatted_row = self._format_csv_row(row, headers)
            formatted_rows.append(formatted_row)

        df = pd.DataFrame(formatted_rows, columns=headers)

        return df

    def response_zip(self, project, ty, expanded=False):
        return self.get_zip(project, ty, expanded)

    def get_zip(self, project, ty, expanded=False):
        """Delete existing ZIP file directly from uploads directory,
        generate one on the fly and upload it.
        """
        filename = self.download_name(project, ty)
        self.delete_existing_zip(project, ty)
        self._make_zip(project, ty, expanded)
        if isinstance(uploader, local.LocalUploader):
            filepath = self._download_path(project)
            res = send_file(path_or_file=safe_join(filepath, filename),
                            mimetype='application/octet-stream',
                            as_attachment=True,
                            attachment_filename=filename)
            # fail safe mode for more encoded filenames.
            # It seems Flask and Werkzeug do not support RFC 5987
            # http://greenbytes.de/tech/tc2231/#encoding-2231-char
            # res.headers['Content-Disposition'] = 'attachment; filename*=%s' % filename
            return res

    def make_zip(self, project, obj, expanded=False, filters=None, disclose_gold=False):
        dataframe = self._respond_csv(obj, project.id, expanded, filters, disclose_gold)

        if dataframe is None:
            return

        name = self._project_name_latin_encoded(project)
        with tempfile.NamedTemporaryFile(mode='w+t') as datafile:
            dataframe.to_csv(datafile, index=False, encoding='utf-8')
            datafile.flush()

            zipped_datafile = tempfile.NamedTemporaryFile()

            with self._zip_factory(zipped_datafile.name) as _zip:
                _zip.write(datafile.name, secure_filename(f'{name}_{obj}.csv'))
                _zip.content_type = 'application/zip'

        filename = self.download_name(project, obj)
        fs = FileStorage(filename=filename, stream=zipped_datafile)
        return closing(fs)

    def _make_zip(self, project, obj, expanded=False, filters=None):
        self.make_zip(self, project, obj, expanded, filters)
