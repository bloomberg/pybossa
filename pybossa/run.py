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
from werkzeug.middleware.proxy_fix import ProxyFix
from pybossa.core import create_app
import werkzeug.serving

werkzeug.serving._log_add_style = False
if __name__ == "__main__":  # pragma: no cover
    app = create_app()

    # tell flask that app is behind the proxy
    app_behind_proxy = app.config.get("APP_BEHIND_PROXY", False)
    app.logger.info("APP_BEHIND_PROXY %r", app_behind_proxy)
    if app_behind_proxy:
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
        )

    app.run(host=app.config['HOST'], port=app.config['PORT'],
            debug=app.config.get('DEBUG', True))
else:
    app = create_app()