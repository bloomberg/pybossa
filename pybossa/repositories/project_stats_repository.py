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

from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError

from pybossa.repositories import Repository
from pybossa.model.project_stats import ProjectStats
from pybossa.exc import WrongObjectError, DBIntegrityError


class ProjectStatsRepository(Repository):

    def __init__(self, db):
        self.db = db

    def get(self, id):
        # bytes to unicode string
        if type(id) == bytes:
            id = id.decode()
        return self.db.session.query(ProjectStats).get(id)

    def filter_by(self, limit=None, offset=0, yielded=False, last_id=None,
                  fulltextsearch=None, desc=False, orderby='id',
                  **filters):
        return self._filter_by(ProjectStats, limit, offset, yielded,
                               last_id, fulltextsearch, desc, orderby,
                               **filters)
