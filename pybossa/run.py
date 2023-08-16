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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with PYBOSSA. If not, see <http://www.gnu.org/licenses/>.
from pybossa.core import create_app
from flask_openapi3 import OpenAPI

def get_app():
    app = create_app()
    # app = OpenAPI(__name__)

    from pybossa.api import blueprint as api
    from pybossa.view.test_view import blueprint as test

    blueprints = [
                #   {'handler': home, 'url_prefix': '/'},
                #   {'handler': api,  'url_prefix': '/api'},
                #   {'handler': account, 'url_prefix': '/account'},
                #   {'handler': bloomberg, 'url_prefix': '/bloomberg'},
                #   {'handler': projects, 'url_prefix': '/project'},
                #   {'handler': projectids, 'url_prefix': '/projectid'},
                #   {'handler': admin, 'url_prefix': '/admin'},
                #   {'handler': announcements, 'url_prefix': '/announcements'},
                #   {'handler': leaderboard, 'url_prefix': '/leaderboard'},
                #   {'handler': helper, 'url_prefix': '/help'},
                #   {'handler': stats, 'url_prefix': '/stats'},
                #   {'handler': uploads, 'url_prefix': '/uploads'},
                #   {'handler': amazon, 'url_prefix': '/amazon'},
                #   {'handler': diagnostics, 'url_prefix': '/diagnostics'},
                #   {'handler': fileproxy, 'url_prefix': '/fileproxy'}

                    {'handler': api, 'url_prefix': '/api'},
                    {'handler': test, 'url_prefix': '/test'}
                  ]


    for bp in blueprints:
        print("registering: ", bp)
        app.register_api(bp['handler'])
    print([str(p) for p in app.url_map.iter_rules()])
    return app

if __name__ == "__main__":  # pragma: no cover
    app = get_app()
    app.run(debug=True)
else:
    app = get_app()
