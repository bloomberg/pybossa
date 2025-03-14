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
PYBOSSA api module for exposing domain objects via an API.

This package adds GET, POST, PUT and DELETE methods for any class:
    * projects,
    * tasks,
    * task_runs,
    * users,
    * etc.

"""
import json
from flask import request, abort, Response, current_app
from flask_login import current_user
from flask.views import MethodView
from flasgger import swag_from
from werkzeug.exceptions import NotFound, Unauthorized, Forbidden, BadRequest
from werkzeug.exceptions import MethodNotAllowed
from pybossa.util import jsonpify, fuzzyboolean, get_avatar_url
from pybossa.util import get_user_id_or_ip
from pybossa.core import ratelimits, uploader
from pybossa.auth import ensure_authorized_to
from pybossa.hateoas import Hateoas
from pybossa.ratelimit import ratelimit
from pybossa.error import ErrorStatus
from pybossa.core import project_repo, user_repo, task_repo, result_repo, auditlog_repo
from pybossa.core import announcement_repo, blog_repo, helping_repo, performance_stats_repo
from pybossa.core import project_stats_repo
from pybossa.model import DomainObject, announcement
from pybossa.model.task import Task
from pybossa.cache.projects import clean_project
from pybossa.cache.users import delete_user_summary_id
from pybossa.cache.categories import reset as reset_categories
from pybossa.cache.announcements import reset as reset_announcements

repos = {'Task': {'repo': task_repo, 'filter': 'filter_tasks_by',
                  'get': 'get_task', 'save': 'save', 'update': 'update',
                  'delete': 'delete'},
         'TaskRun': {'repo': task_repo, 'filter': 'filter_task_runs_by',
                     'get': 'get_task_run',  'save': 'save',
                     'update': 'update', 'delete': 'delete'},
         'User': {'repo': user_repo, 'filter': 'filter_by', 'get': 'get',
                  'save': 'save', 'update': 'update'},
         'Project': {'repo': project_repo, 'filter': 'filter_by',
                     'context': 'filter_owner_by', 'get': 'get',
                     'save': 'save', 'update': 'update', 'delete': 'delete'},
         'ProjectStats': {'repo': project_stats_repo, 'filter': 'filter_by',
                          'get': 'get'},
         'Category': {'repo': project_repo, 'filter': 'filter_categories_by',
                      'get': 'get_category', 'save': 'save_category',
                      'update': 'update_category',
                      'delete': 'delete_category'},
         'Result': {'repo': result_repo, 'filter': 'filter_by', 'get': 'get',
                    'update': 'update', 'save': 'save'},
         'Announcement': {'repo': announcement_repo, 'filter': 'filter_by', 'get': 'get',
                          'get_all_announcements': 'get_all_announcements',
                          'update': 'update', 'save': 'save', 'delete': 'delete'},
         'Blogpost': {'repo': blog_repo, 'filter': 'filter_by', 'get': 'get',
                      'update': 'update', 'save': 'save', 'delete': 'delete'},
         'HelpingMaterial': {'repo': helping_repo, 'filter': 'filter_by',
                             'get': 'get', 'update': 'update',
                             'save': 'save', 'delete': 'delete'},
         'PerformanceStats': {'repo': performance_stats_repo, 'filter': 'filter_by',
                              'get': 'get'},
         'Auditlog': {'repo': auditlog_repo, 'filter': 'filter_by',
                              'get': 'get'}
        }

caching = {'Project': {'refresh': clean_project},
           'User': {'refresh': delete_user_summary_id},
           'Category': {'refresh': reset_categories},
           'Announcement': {'refresh': reset_announcements}}

cors_headers = ['Content-Type', 'Authorization']

error = ErrorStatus()


class APIBase(MethodView):

    """Class to create CRUD methods."""

    hateoas = Hateoas()

    allowed_classes_upload = ['blogpost',
                              'helpingmaterial',
                              'announcement']

    immutable_keys = set(['short_name'])

    def refresh_cache(self, cls_name, oid):
        """Refresh the cache."""
        if caching.get(cls_name):
            if cls_name not in ['Category', 'Announcement']:
                caching.get(cls_name)['refresh'](oid)
            else:
                caching.get(cls_name)['refresh']()

    def valid_args(self):
        """Check if the domain object args are valid."""
        for k in request.args.keys():
            if k not in ['api_key']:
                getattr(self.__class__, k)

    def options(self, **kwargs):  # pragma: no cover
        """Return '' for Options method."""
        return ''

    @jsonpify
    @ratelimit(limit=ratelimits.get('LIMIT'), per=ratelimits.get('PER'))
    @swag_from('docs/task/task_get.yaml', endpoint='api.api_task_oid')
    @swag_from('docs/project/project_get.yaml', endpoint='api.api_project_oid')
    def get(self, oid):
        """Get an object.

        Returns an item from the DB with the request.data JSON object or all
        the items if oid == None

        :arg self: The class of the object to be retrieved
        :arg integer oid: the ID of the object in the DB
        :returns: The JSON item/s stored in the DB

        """
        try:
            ensure_authorized_to('read', self.__class__)
            query = self._db_query(oid)
            json_response = self._create_json_response(query, oid)
            return Response(json_response, mimetype='application/json')
        except Exception as e:
            return error.format_exception(
                e,
                target=self.__class__.__name__.lower(),
                action='GET')

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
                ensure_authorized_to('read', item)
                items.append(datum)
            except (Forbidden, Unauthorized):
                # pass as it is 401 or 403
                pass
            except Exception:  # pragma: no cover
                raise
        if oid is not None:
            if not items:
                raise Forbidden('Forbidden')
            ensure_authorized_to('read', query_result[0])
            self._sign_item(items[0])
            items = items[0]
        return json.dumps(items)

    def _create_dict_from_model(self, model):
        return self._select_attributes(self._add_hateoas_links(model))

    def _add_hateoas_links(self, item):
        obj = item.dictize()
        related = request.args.get('related')
        if related:
            if item.__class__.__name__ == 'Task':
                obj['task_runs'] = []
                obj['result'] = None
                task_runs = task_repo.filter_task_runs_by(task_id=item.id)
                results = result_repo.filter_by(task_id=item.id, last_version=True)
                for tr in task_runs:
                    obj['task_runs'].append(tr.dictize())
                for r in results:
                    obj['result'] = r.dictize()

            if item.__class__.__name__ == 'TaskRun':
                tasks = task_repo.filter_tasks_by(id=item.task_id)
                results = result_repo.filter_by(task_id=item.task_id, last_version=True)
                obj['task'] = None
                obj['result'] = None
                for t in tasks:
                    obj['task'] = t.dictize()
                for r in results:
                    obj['result'] = r.dictize()

            if item.__class__.__name__ == 'Result':
                tasks = task_repo.filter_tasks_by(id=item.task_id)
                task_runs = task_repo.filter_task_runs_by(task_id=item.task_id)
                obj['task_runs'] = []
                for t in tasks:
                    obj['task'] = t.dictize()
                for tr in task_runs:
                    obj['task_runs'].append(tr.dictize())

        stats = request.args.get('stats')
        if stats:
            if item.__class__.__name__ == 'Project':
                stats = project_stats_repo.filter_by()
                obj['stats'] = stats[0].dictize() if stats else {}

        links, link = self.hateoas.create_links(item)
        if links:
            obj['links'] = links
        if link:
            obj['link'] = link
        return obj

    def _db_query(self, oid):
        """Returns a list with the results of the query"""
        repo_info = repos[self.__class__.__name__]
        if oid is None:
            limit, offset, orderby = self._set_limit_and_offset()
            results = self._filter_query(repo_info, limit, offset, orderby)
        else:
            repo = repo_info['repo']
            query_func = repo_info['get']
            results = [getattr(repo, query_func)(oid)]
        return results

    def api_context(self, all_arg, **filters):
        if current_user.is_authenticated:
            filters['owner_id'] = current_user.id
        if filters.get('owner_id') and all_arg == '1':
            del filters['owner_id']
        return filters

    def _filter_query(self, repo_info, limit, offset, orderby):
        filters = {}
        for k in request.args.keys():
            if k not in ['limit', 'offset', 'api_key', 'last_id', 'all',
                         'fulltextsearch', 'desc', 'orderby', 'related',
                         'participated', 'full', 'stats',
                         'from_finish_time', 'to_finish_time', 'created_from', 'created_to']:
                # Raise an error if the k arg is not a column
                if self.__class__ == Task and k == 'external_uid':
                    pass
                else:
                    self._has_filterable_attribute(k)
                filters[k] = request.args[k]

        repo = repo_info['repo']
        filters = self.api_context(all_arg=request.args.get('all'), **filters)
        query_func = repo_info['filter']
        filters = self._custom_filter(filters)
        last_id = request.args.get('last_id')
        if request.args.get('participated'):
            filters['participated'] = get_user_id_or_ip()
        fulltextsearch = request.args.get('fulltextsearch')
        desc = request.args.get('desc') if request.args.get('desc') else False
        desc = fuzzyboolean(desc)

        if request.args.get('created_from'):
            filters['created_from'] = request.args.get('created_from')

        if request.args.get('created_to'):
            filters['created_to'] = request.args.get('created_to')

        if last_id:
            results = getattr(repo, query_func)(limit=limit, last_id=last_id,
                                                fulltextsearch=fulltextsearch,
                                                desc=False,
                                                orderby=orderby,
                                                **filters)
        else:
            results = getattr(repo, query_func)(limit=limit, offset=offset,
                                                fulltextsearch=fulltextsearch,
                                                desc=desc,
                                                orderby=orderby,
                                                **filters)
        return results

    def _set_limit_and_offset(self):
        try:
            limit = min(100, int(request.args.get('limit')))
        except (ValueError, TypeError):
            limit = 20
        try:
            offset = int(request.args.get('offset'))
        except (ValueError, TypeError):
            offset = 0
        try:
            orderby = request.args.get('orderby') if request.args.get('orderby') else 'id'
        except (ValueError, TypeError):
            orderby = 'updated'
        return limit, offset, orderby

    @jsonpify
    @ratelimit(limit=ratelimits.get('LIMIT'), per=ratelimits.get('PER'))
    @swag_from('docs/task/task_post.yaml', endpoint='api.api_task')
    @swag_from('docs/project/project_post.yaml', endpoint='api.api_project')
    def post(self):
        """Post an item to the DB with the request.data JSON object.

        :arg self: The class of the object to be inserted
        :returns: The JSON item stored in the DB

        """
        try:
            cls_name = self.__class__.__name__
            data = None
            self.valid_args()
            self._preprocess_request(request)
            data = self._file_upload(request)
            if data is None:
                data = self._parse_request_data()
            original_data = self._copy_original(data)
            self._forbidden_attributes(data)
            self._restricted_attributes(data)
            self._preprocess_post_data(data)
            inst = self._create_instance_from_request(data)
            repo = repos[self.__class__.__name__]['repo']
            save_func = repos[self.__class__.__name__]['save']
            getattr(repo, save_func)(inst)
            self._after_save(original_data, inst)
            self._log_changes(None, inst)
            self.refresh_cache(cls_name, inst.id)
            response_dict = inst.dictize()
            self._customize_response_dict(response_dict)
            json_response = json.dumps(response_dict)
            message = f"Created {cls_name}"
            self._log_operation(message, info=response_dict)
            return Response(json_response, mimetype='application/json')
        except Exception as e:
            return error.format_exception(
                e,
                target=self.__class__.__name__.lower(),
                action='POST')

    def _customize_response_dict(self, response_dict):
        """Method to be overridden by inheriting classes that want
        to modify the returned response to something other than
        the raw data from the DB."""
        pass

    def _parse_request_data(self):
        if 'request_json' in request.form:
            data = json.loads(request.form['request_json'])
        else:
            data = json.loads(request.data)
        return data

    def _preprocess_post_data(self, data):
        """Method to be overridden by inheriting classes that will
        perform preprocessing on the POST data"""
        pass

    def _preprocess_request(self, request):
        """Method to be overridden by inheriting classes that will
        perform preprocessong on the POST and PUT request"""
        pass

    def _create_instance_from_request(self, data):
        data = self.hateoas.remove_links(data)
        inst = self.__class__(**data)
        self._update_object(inst)
        ensure_authorized_to('create', inst)
        self._validate_instance(inst)
        return inst

    @jsonpify
    @ratelimit(limit=ratelimits.get('LIMIT'), per=ratelimits.get('PER'))
    @swag_from('docs/task/task_delete.yaml', endpoint='api.api_task_oid')
    @swag_from('docs/project/project_delete.yaml', endpoint='api.api_project_oid')
    def delete(self, oid):
        """Delete a single item from the DB.

        :arg self: The class of the object to be deleted
        :arg integer oid: the ID of the object in the DB
        :returns: An HTTP status code based on the output of the action.

        More info about HTTP status codes for this action `here
        <http://www.w3.org/Protocols/rfc2616/rfc2616-sec9.html#sec9.7>`_.

        """
        try:
            self.valid_args()
            self._delete_instance(oid)
            cls_name = self.__class__.__name__
            self.refresh_cache(cls_name, oid)
            message = f"Deleted {cls_name} id {oid}"
            self._log_operation(message)
            return Response('', 204, mimetype='application/json')
        except Exception as e:
            return error.format_exception(
                e,
                target=self.__class__.__name__.lower(),
                action='DELETE')

    def _delete_instance(self, oid):
        repo = repos[self.__class__.__name__]['repo']
        query_func = repos[self.__class__.__name__]['get']
        inst = getattr(repo, query_func)(oid)
        if inst is None:
            raise NotFound
        ensure_authorized_to('delete', inst)
        self._file_delete(request, inst)
        self._log_changes(inst, None)
        delete_func = repos[self.__class__.__name__]['delete']
        getattr(repo, delete_func)(inst)
        return inst

    @jsonpify
    @ratelimit(limit=ratelimits.get('LIMIT'), per=ratelimits.get('PER'))
    @swag_from('docs/project/project_put.yaml', endpoint='api.api_project_oid')
    def put(self, oid):
        """Update a single item in the DB.

        :arg self: The class of the object to be updated
        :arg integer oid: the ID of the object in the DB
        :returns: An HTTP status code based on the output of the action.

        More info about HTTP status codes for this action `here
        <http://www.w3.org/Protocols/rfc2616/rfc2616-sec9.html#sec9.6>`_.

        """
        try:
            self.valid_args()
            self._preprocess_request(request)
            cls_name = self.__class__.__name__
            repo = repos[cls_name]['repo']
            query_func = repos[cls_name]['get']
            existing = getattr(repo, query_func)(oid)
            if existing is None:
                raise NotFound
            ensure_authorized_to('update', existing)
            data = self._file_upload(request)
            inst = self._update_instance(existing, repo,
                                         repos,
                                         new_upload=data)
            self.refresh_cache(cls_name, oid)
            response_dict = inst.dictize()
            message = f"Updated {cls_name}"
            self._log_operation(message, info=response_dict)
            return Response(json.dumps(response_dict), 200,
                            mimetype='application/json')
        except Exception as e:
            return error.format_exception(
                e,
                target=self.__class__.__name__.lower(),
                action='PUT')

    def _update_instance(self, existing, repo, repos, new_upload=None):
        data = dict()
        if new_upload is None:
            data = json.loads(request.data)
            new_data = data
        else:
            new_data = request.form
        self._forbidden_attributes(new_data)
        self._restricted_attributes(new_data)
        # Remove hateoas links
        data = self.hateoas.remove_links(data)
        # may be missing the id as we allow partial updates
        self.__class__(**data)
        old = self.__class__(**existing.dictize())
        for key in data:
            if key not in self.immutable_keys:
                setattr(existing, key, data[key])
            elif not (getattr(existing, key) == data[key]):
                raise Forbidden('Cannot change {} via API'.format(key))

        if new_upload:
            existing.media_url = new_upload['media_url']
            existing.info['container'] = new_upload['info']['container']
            existing.info['file_name'] = new_upload['info']['file_name']
        self._update_attribute(existing, old)
        update_func = repos[self.__class__.__name__]['update']
        self._validate_instance(existing)
        getattr(repo, update_func)(existing)
        self._log_changes(old, existing)
        return existing

    def _update_object(self, data_dict):
        """Update object.

        Method to be overriden in inheriting classes which wish to update
        data dict.

        """
        pass

    def _update_attribute(self, new, old):
        """Update object attribute if new value is passed.
        Method to be overriden in inheriting classes which wish to update
        data dict.

        """

    def _select_attributes(self, item_data):
        """Method to be overriden in inheriting classes in case it is not
        desired that every object attribute is returned by the API.
        """
        return item_data

    def _custom_filter(self, query):
        """Method to be overriden in inheriting classes which wish to consider
        specific filtering criteria.
        """
        return query

    def _has_filterable_attribute(self, attribute):
        """Method to be overridden by inheriting classes that want
        to have custom filterable attributes"""
        getattr(self.__class__, attribute)

    def _validate_instance(self, instance):
        """Method to be overriden in inheriting classes which may need to
        validate the creation (POST) or modification (PUT) of a domain object
        for reasons other than business logic ones (e.g. overlapping of a
        project name witht a URL).
        """
        pass

    def _after_save(self, original_data, instance):
        """Method to be overriden by inheriting classes to perform operations
        after new object has been saved
        """
        pass

    def _log_changes(self, old_obj, new_obj):
        """Method to be overriden by inheriting classes for logging purposes"""
        pass

    def _forbidden_attributes(self, data):
        """Method to be overriden by inheriting classes that will not allow for
        certain fields to be used in PUT or POST requests"""
        pass

    def _restricted_attributes(self, data):
        """Method to be overriden by inheriting classes that will restrict
        certain fields to be used in PUT or POST requests for certain users"""
        pass

    def _file_upload(self, data):
        """Method that must be overriden by the class to allow file uploads for
        only a few classes."""
        cls_name = self.__class__.__name__.lower()
        content_type = 'multipart/form-data'
        if (content_type in request.headers.get('Content-Type', []) and
                cls_name in self.allowed_classes_upload):
            tmp = dict()
            for key in request.form.keys():
                tmp[key] = request.form[key]

            if isinstance(self, announcement.Announcement):
                # don't check project id for announcements
                ensure_authorized_to('create', self)
                if tmp.get('info') is not None:
                    try:
                        tmp['info'] = json.loads(tmp['info'])
                    except ValueError:
                        raise BadRequest
                upload_method = current_app.config.get('UPLOAD_METHOD')
                if request.files.get('file') is None:
                    raise AttributeError
                _file = request.files['file']
                container = "user_%s" % current_user.id
            else:
                ensure_authorized_to('create', self.__class__,
                                     project_id=tmp['project_id'])
                project = project_repo.get(tmp['project_id'])
                upload_method = current_app.config.get('UPLOAD_METHOD')
                if request.files.get('file') is None:
                    raise AttributeError
                _file = request.files['file']
                if current_user.is_authenticated:
                    if current_user.admin:
                        container = "user_%s" % project.owner.id
                    else:
                        container = "user_%s" % current_user.id
                else:
                    container = "anonymous"
            uploader.upload_file(_file,
                                 container=container)
            avatar_absolute = current_app.config.get('AVATAR_ABSOLUTE')
            file_url = get_avatar_url(upload_method,
                                      _file.filename,
                                      container,
                                      avatar_absolute)
            tmp['media_url'] = file_url
            if tmp.get('info') is None:
                tmp['info'] = dict()
            tmp['info']['container'] = container
            tmp['info']['file_name'] = _file.filename
            return tmp
        else:
            return None

    def _file_delete(self, request, obj):
        """Delete file object."""
        cls_name = self.__class__.__name__.lower()
        if cls_name in self.allowed_classes_upload:
            keys = obj.info.keys()
            if 'file_name' in keys and 'container' in keys:
                ensure_authorized_to('delete', obj)
                uploader.delete_file(obj.info['file_name'],
                                     obj.info['container'])

    def _verify_auth(self, item):
        """Method to be overriden in inheriting classes for additional checks
        on the items to return
        """
        return True

    def _sign_item(self, item):
        """Apply custom signature"""
        pass

    def _copy_original(self, item):
        """change if need to keep some information about the original request"""
        return item

    def _log_operation(self, message, info=None):
        """Log api operation with message and additonal info provided"""
        if not info:
            current_app.logger.info("%s", message)
            return

        log_info = [f"{key} {info[key]}" for key in ["id", "name", "short_name", "owner_id", "project_id"] if key in info]
        current_app.logger.info("%s %s", message, ", ".join(log_info))
