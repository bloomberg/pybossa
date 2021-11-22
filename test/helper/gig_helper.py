# -*- coding: utf8 -*-
# This file is part of PYBOSSA.
#
# Copyright (C) 2017 Scifabric LTD.
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

from test import db
from pybossa.repositories import UserRepository


def make_admin(user):
    user_repo = UserRepository(db)
    user.admin = True
    user_repo.save(user)


def make_admin_by(**attributes):
    user_repo = UserRepository(db)
    user = user_repo.get_by(**attributes)
    make_admin(user)


def make_subadmin(user):
    user_repo = UserRepository(db)
    user.subadmin = True
    user_repo.save(user)


def make_subadmin_by(**attributes):
    user_repo = UserRepository(db)
    user = user_repo.get_by(**attributes)
    make_subadmin(user)
