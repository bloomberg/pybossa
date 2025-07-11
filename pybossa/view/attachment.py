# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2025 Scifabric LTD.
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
from flask import current_app, abort
from flask import Blueprint, request, Response
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden, BadRequest

from pybossa.cloud_store_api.s3 import s3_get_email_attachment
from pybossa.core import signer
from pybossa.util import admin_or_project_owner
from itsdangerous import BadSignature

blueprint = Blueprint('attachment', __name__)

TASK_SIGNATURE_MAX_SIZE = 128

@login_required
@blueprint.route('/<string:signature>/<string:path>', methods=['GET', 'POST'])
def download_attachment(signature, path):
    """download attachment from storage location"""

    from pybossa.core import project_repo

    try:
        size_signature = len(signature)
        if size_signature > TASK_SIGNATURE_MAX_SIZE:
            current_app.logger.exception(
                "Invalid task signature. Signature length exceeds max allowed length. signature %s, path %s",
                signature, path)
            raise BadRequest('Invalid signature')
        
        signed_payload = signer.loads(signature)
        project_id = signed_payload.get("project_id")
        user_email = signed_payload.get("user_email")
        current_app.logger.info("download attachment url signed info. project id %d, user email %s", project_id, user_email)

        # admins and project owners are authorized to download the attachment
        if project_id:
            project = project_repo.get(project_id)
            if not project:
                raise BadRequest(f"Invalid project id {project_id}")

            current_app.logger.info("project info: id %d, owner ids %s. current user info: id %d, admin %r, authenticated %r",
                                    project.id, str(project.owners_ids), current_user.id, current_user.admin, current_user.is_authenticated)
            admin_or_project_owner(current_user, project)

        # admins or subadmin users tagged in signature can download the attachment
        if user_email:
            if not (current_user.admin or (current_user.subadmin and current_user.email_addr == user_email)):
                raise Forbidden('Access denied')

        resp = s3_get_email_attachment(path)
        response = Response(resp["content"], mimetype=resp["type"], status=200)
        if resp["content"]:
            response.headers['Content-Disposition'] = f'attachment; filename={resp["name"]}'
    except BadSignature as ex:
        current_app.logger.exception("BadSignature. %s, signature %s, path %s",str(ex), signature, path)
        response = Response(f"An internal error has occurred.", mimetype="text/plain", status=400)
    except BadRequest as ex:
        current_app.logger.exception("%s, signature %s, path %s",str(ex), signature, path)
        response = Response(f"An internal error has occurred.", mimetype="text/plain", status=400)
    except Forbidden as ex:
        current_app.logger.exception("%s, signature %s, path %s",str(ex), signature, path)
        response = Response(f"An internal error has occurred.", mimetype="text/plain", status=403)
    except Exception as ex:
        current_app.logger.exception("%s, signature %s, path %s", str(ex), signature, path)
        response = Response(f"Failed loading requested url.", mimetype="text/plain", status=400)
    return response
