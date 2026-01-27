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
PYBOSSA api module for domain object APP via an API.

This package adds GET, POST, PUT and DELETE methods for:
    * projects,

"""
import copy
from werkzeug.exceptions import BadRequest, Forbidden, Unauthorized
from flask import current_app, request
from flask_babel import gettext
from flask_login import current_user
from .api_base import APIBase
from pybossa.model.project import Project
from pybossa.cache.categories import get_all as get_categories
from pybossa.util import is_reserved_name, description_from_long_description, validate_ownership_id
from pybossa.core import auditlog_repo, result_repo, http_signer
from pybossa.auditlogger import AuditLogger
from pybossa.data_access import ensure_user_assignment_to_project, set_default_amp_store
from sqlalchemy.orm.base import _entity_descriptor
from pybossa.cache import delete_memoized
from pybossa.cache.projects import get_project_data

auditlogger = AuditLogger(auditlog_repo, caller='api')


class ProjectAPI(APIBase):

    """
    Class for the domain object Project.

    It refreshes automatically the cache, and updates the project properly.

    """

    __class__ = Project
    reserved_keys = set(['id', 'created', 'updated', 'completed', 'contacted', 'secret_key'])
    private_keys = set(['secret_key'])
    restricted_keys = set(['info::ext_config::authorized_services'])

    def _has_filterable_attribute(self, attribute):
        if attribute not in ["coowner_id"]:
            getattr(self.__class__, attribute)

    def _custom_filter(self, query):
        if "coowner_id" in query:
            try:
                coowner_id = int(query.pop("coowner_id"))
            except ValueError:
                raise ValueError(gettext("Please enter a valid id."))

            query.pop("owner_id", None)

            if current_user.id == coowner_id:
                query['custom_query_filters'] = [
                    _entity_descriptor(Project, "owners_ids").any(coowner_id),
                ]
            else:
                query['custom_query_filters'] = [
                    _entity_descriptor(Project, "owners_ids").any(current_user.id),
                    _entity_descriptor(Project, "owners_ids").any(coowner_id),
                ]
        return query

    def _preprocess_request(self, request):
        # Limit maximum post data size.
        content_length = request.content_length if request else 0
        max_length_mb = current_app.config.get('TASK_PRESENTER_MAX_SIZE_MB', 2)
        max_length_bytes = max_length_mb * 1024 * 1024 # Maximum POST data size (MB)
        if content_length and content_length > max_length_bytes:
            raise BadRequest('The task presenter/guidelines content exceeds ' +
                str(max_length_mb) +
                ' MB. Please move large content to an external file.')

    def _preprocess_post_data(self, data):
        # set amp_store default as true when not passed as input param
        amp_config = data.get('info', {}).get('annotation_config', {}).get('amp_store')
        if amp_config is None:
            set_default_amp_store(data)
        # clean up description and long description
        long_desc = data.get("long_description")
        desc = data.get("description")
        if not long_desc and not desc:
            raise BadRequest("description or long description required")
        if not long_desc:
            data["long_description"] = desc
        if not desc:
            data["description"] = description_from_long_description(desc, long_desc)
        # set default data_access
        if not data.get('info', {}).get("data_access"):
            data["info"] = data.get("info", {})
            # set to least restrictive, will overwrite when saved
            data["info"]["data_access"] = ["L4"]
        # creating projects with encryption is deprecated
        enc_config = data.get('info', {}).get('ext_config', {}).get('encryption', {})
        if enc_config:
            raise BadRequest("Creating projects with encryption is deprecated")

    def _create_instance_from_request(self, data):
        # password required if not syncing
        sync_json = data["info"].get("sync", {})
        # keys added when syncing
        sync_keys = ("latest_sync", "source_url", "syncer")
        sync = all(sync_key in sync_json for sync_key in sync_keys)
        password = data.pop("password", "")
        if not (sync or password) or (sync and "passwd_hash" not in data["info"]):
            raise BadRequest("password required")
        inst = super(ProjectAPI, self)._create_instance_from_request(data)
        if not sync:
            # set password if not syncing
            inst.set_password(password)
        category_ids = [c.id for c in get_categories()]
        default_category = get_categories()[0]
        inst.category_id = default_category.id
        if 'category_id' in data.keys():
            if int(data.get('category_id')) in category_ids:
                inst.category_id = data.get('category_id')
            else:
                raise BadRequest("category_id does not exist")
        return inst

    def _update_object(self, obj):
        if not current_user.is_anonymous:
            obj.owner_id = current_user.id
            owners = obj.owners_ids or []
            if current_user.id not in owners:
                owners.append(current_user.id)
            obj.owners_ids = owners

    def _update_attribute(self, new, old):
        # updating encryption key is deprecated
        new_key = new.info.get("ext_config", {}).get("encryption", {}).get("bpv_key_id")
        old_key = old.info.get("ext_config", {}).get("encryption", {}).get("bpv_key_id")
        if new_key and new_key != old_key:
            raise BadRequest("Updating encryption key is deprecated")

        for key, value in old.info.items():
            new.info.setdefault(key, value)

    def _validate_instance(self, project):
        if project.short_name and is_reserved_name('project', project.short_name):
            msg = "Project short_name is not valid, as it's used by the system."
            raise ValueError(msg)
        ensure_user_assignment_to_project(project)
        validate_ownership_id(project.info.get('ownership_id'))
        self._validate_task_filter_fields(project)

    def _validate_task_filter_fields(self, project):
        """Validate task_filter_fields is a list when provided."""
        task_filter_fields = project.info.get('task_filter_fields')
        if task_filter_fields is not None and not isinstance(task_filter_fields, list):
            raise BadRequest("task_filter_fields must be a list")

    def _log_changes(self, old_project, new_project):
        auditlogger.add_log_entry(old_project, new_project, current_user)

    def _forbidden_attributes(self, data):
        for key in data.keys():
            if key in self.reserved_keys:
                raise BadRequest("Reserved keys in payload")

    def _restricted_attributes(self, data):
        if (current_user.is_authenticated and
            not current_user.admin and
            not http_signer.valid(request)):

            for key in data.keys():
                self._raise_if_restricted(key, data)

    @classmethod
    def _raise_if_restricted(cls, key, data, restricted_keys=None):
        if not restricted_keys:
            restricted_keys = list(cls.restricted_keys)

        for restricted_key in restricted_keys:
            split_key = restricted_key.split('::', 1)
            restricted_key = split_key.pop(0)
            if key == restricted_key:
                if isinstance(data, dict) and split_key:
                    for k in data[key].keys():
                        cls._raise_if_restricted(
                            k, data[key], split_key)
                else:
                    raise Unauthorized(
                        'Restricted key in payload '
                        '(Admin privilege required)')

    def _filter_private_data(self, data):
        tmp = copy.deepcopy(data)
        public = Project().public_attributes()
        public.append('link')
        public.append('links')
        public.append('stats')
        for key in list(tmp.keys()):  # make a copy of keys because of del tmp[key]
            if key not in public:
                del tmp[key]
        for key in list(tmp['info'].keys()):
            if key not in Project().public_info_keys():
                del tmp['info'][key]
        return tmp

    def _select_attributes(self, data):
        if (current_user.is_authenticated and
                (current_user.id in data['owners_ids'] or
                    current_user.admin or current_user.subadmin)):
            return data
        else:
            data = self._filter_private_data(data)
            return data

    def _after_save(self, original_data, instance):
        delete_memoized(get_project_data, instance.id)

    def _customize_response_dict(self, response_dict):
        """Customize the response dictionary to include dynamically generated warnings."""
        # Generate warnings dynamically based on current configuration
        project_info = response_dict.get('info', {})
        product = project_info.get('product')
        subproduct = project_info.get('subproduct')

        if product and subproduct:
            warnings = self._generate_product_subproduct_warnings(product, subproduct)
            if warnings:
                response_dict['warnings'] = warnings

        return response_dict


    def _is_product_or_subproduct_deprecated(self, product, subproduct=None):
        """Check if a product or product/subproduct combination is deprecated."""
        deprecated_products_subproducts = current_app.config.get('DEPRECATED_PRODUCTS_SUBPRODUCTS', {})

        # Check if product or product/subproduct combination is deprecated
        if product not in deprecated_products_subproducts:
            return False  # Valid and not deprecated

        if subproduct and subproduct in deprecated_products_subproducts[product]:
            return True  # Valid and Deprecated combination

        return False # Valid and not deprecated


    def _generate_product_subproduct_warnings(self, product, subproduct):
        """Generate warnings for product and subproduct selections."""
        warnings = []

        if product and self._is_product_or_subproduct_deprecated(product, subproduct):
            warnings.append(
                'Combination of selected Product and Subproduct has been deprecated '
                'and will be removed in future. Refer to GIGwork documentation for '
                'taxonomy updates.'
            )

        return warnings
