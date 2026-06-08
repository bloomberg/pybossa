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

import unittest
from unittest.mock import MagicMock, patch, call

from pybossa.sentinel import Sentinel


def make_app(config):
    """Return a minimal fake Flask app with the given config dict."""
    app = MagicMock()
    app.config = config
    return app


class TestSentinelInitAppDNS(unittest.TestCase):
    """Tests for init_app when REDIS_MASTER_DNS / REDIS_SLAVE_DNS / REDIS_PORT are set."""

    BASE_CONFIG = {
        'REDIS_MASTER_DNS': 'redis-master.example.com',
        'REDIS_SLAVE_DNS': 'redis-slave.example.com',
        'REDIS_PORT': 6379,
        'REDIS_DB': 0,
        'REDIS_PWD': None,
        'REDIS_SOCKET_TIMEOUT': 0.1,
        'REDIS_RETRY_ON_TIMEOUT': True,
    }

    @patch('pybossa.sentinel.StrictRedis')
    def test_dns_mode_no_ssl(self, mock_strict_redis):
        """init_app with DNS mode and SSL disabled does not pass ssl args."""
        config = {**self.BASE_CONFIG, 'REDIS_SSL': False}
        app = make_app(config)

        s = Sentinel()
        s.init_app(app)

        expected_kwargs = {
            'db': 0,
            'password': None,
            'socket_timeout': 0.1,
            'retry_on_timeout': True,
        }
        # init_app calls StrictRedis for both master and slave; assert_any_call
        # checks that at least one of them matches.
        mock_strict_redis.assert_any_call(
            host='redis-master.example.com',
            port=6379,
            **expected_kwargs,
        )
        mock_strict_redis.assert_any_call(
            host='redis-slave.example.com',
            port=6379,
            **expected_kwargs,
        )
        # ssl must NOT appear in any of the init_app calls (skip the no-arg
        # call made by Sentinel.__init__)
        for c in mock_strict_redis.call_args_list:
            if c.args or c.kwargs:  # skip the bare StrictRedis() from __init__
                assert 'ssl' not in c.kwargs

    @patch('pybossa.sentinel.StrictRedis')
    def test_dns_mode_ssl_enabled(self, mock_strict_redis):
        """init_app with DNS mode and SSL enabled passes ssl and ssl_ca_certs."""
        config = {
            **self.BASE_CONFIG,
            'REDIS_SSL': True,
            'REDIS_SSL_CA_CERTS': '/path/to/ca.crt',
        }
        app = make_app(config)

        s = Sentinel()
        s.init_app(app)

        expected_kwargs = {
            'db': 0,
            'password': None,
            'socket_timeout': 0.1,
            'retry_on_timeout': True,
            'ssl': True,
            'ssl_ca_certs': '/path/to/ca.crt',
        }
        mock_strict_redis.assert_called_with(
            host='redis-slave.example.com',
            port=6379,
            **expected_kwargs,
        )

    @patch('pybossa.sentinel.StrictRedis')
    def test_dns_mode_ssl_enabled_no_ca_certs(self, mock_strict_redis):
        """init_app with SSL=True but no CA certs passes ssl_ca_certs=None."""
        config = {
            **self.BASE_CONFIG,
            'REDIS_SSL': True,
            'REDIS_SSL_CA_CERTS': None,
        }
        app = make_app(config)

        s = Sentinel()
        s.init_app(app)

        # Only check calls that carry keyword arguments (skip the bare
        # StrictRedis() invocation from Sentinel.__init__)
        init_app_calls = [c for c in mock_strict_redis.call_args_list if c.kwargs]
        assert len(init_app_calls) == 2  # master and slave
        for c in init_app_calls:
            assert c.kwargs.get('ssl') is True
            assert c.kwargs.get('ssl_ca_certs') is None


class TestSentinelInitAppSentinelConfig(unittest.TestCase):
    """Tests for init_app when REDIS_SENTINEL list is configured (no DNS)."""

    BASE_CONFIG = {
        'REDIS_SENTINEL': [('sentinel1.example.com', 26379)],
        'REDIS_MASTER': 'mymaster',
        'REDIS_DB': 1,
        'REDIS_PWD': 'secret',
        'REDIS_SOCKET_TIMEOUT': 0.2,
        'REDIS_RETRY_ON_TIMEOUT': False,
    }

    @patch('pybossa.sentinel.sentinel')
    def test_sentinel_mode_no_ssl(self, mock_sentinel_module):
        """init_app with sentinel list and SSL disabled passes empty sentinel_kwargs."""
        config = {**self.BASE_CONFIG, 'REDIS_SSL': False}
        app = make_app(config)

        mock_sentinel_instance = MagicMock()
        mock_sentinel_module.Sentinel.return_value = mock_sentinel_instance

        s = Sentinel()
        s.init_app(app)

        mock_sentinel_module.Sentinel.assert_called_once_with(
            [('sentinel1.example.com', 26379)],
            sentinel_kwargs={},
            db=1,
            password='secret',
            socket_timeout=0.2,
            retry_on_timeout=False,
        )
        assert s.master is mock_sentinel_instance.master_for.return_value
        assert s.slave is mock_sentinel_instance.slave_for.return_value

    @patch('pybossa.sentinel.sentinel')
    def test_sentinel_mode_ssl_enabled(self, mock_sentinel_module):
        """init_app with sentinel list and SSL enabled passes sentinel_kwargs with ssl."""
        config = {
            **self.BASE_CONFIG,
            'REDIS_SSL': True,
            'REDIS_SSL_CA_CERTS': '/certs/ca.pem',
        }
        app = make_app(config)

        mock_sentinel_instance = MagicMock()
        mock_sentinel_module.Sentinel.return_value = mock_sentinel_instance

        s = Sentinel()
        s.init_app(app)

        mock_sentinel_module.Sentinel.assert_called_once_with(
            [('sentinel1.example.com', 26379)],
            sentinel_kwargs={'ssl': True, 'ssl_ca_certs': '/certs/ca.pem'},
            db=1,
            password='secret',
            socket_timeout=0.2,
            retry_on_timeout=False,
            ssl=True,
            ssl_ca_certs='/certs/ca.pem',
        )

    @patch('pybossa.sentinel.sentinel')
    def test_sentinel_mode_master_and_slave_set(self, mock_sentinel_module):
        """init_app calls master_for and slave_for with the configured master name."""
        config = {**self.BASE_CONFIG, 'REDIS_SSL': False}
        app = make_app(config)

        mock_sentinel_instance = MagicMock()
        mock_sentinel_module.Sentinel.return_value = mock_sentinel_instance

        s = Sentinel()
        s.init_app(app)

        mock_sentinel_instance.master_for.assert_called_once_with('mymaster')
        mock_sentinel_instance.slave_for.assert_called_once_with('mymaster')


class TestSentinelInitAppDNSResolution(unittest.TestCase):
    """Tests for init_app when REDIS_SENTINELS_DNS env var is set."""

    BASE_CONFIG = {
        'REDIS_MASTER': 'mymaster',
        'REDIS_DB': 0,
        'REDIS_PWD': None,
        'REDIS_SOCKET_TIMEOUT': 0.1,
        'REDIS_RETRY_ON_TIMEOUT': True,
    }

    def _make_srv_record(self, target, port):
        record = MagicMock()
        record.target.to_text.return_value = target
        record.port = port
        return record

    @patch('pybossa.sentinel.sentinel')
    @patch('pybossa.sentinel.resolver')
    @patch.dict('os.environ', {'REDIS_SENTINELS_DNS': 'sentinels.example.com'})
    def test_dns_resolution_no_ssl(self, mock_resolver, mock_sentinel_module):
        """init_app with REDIS_SENTINELS_DNS and SSL disabled passes empty sentinel_kwargs."""
        srv_records = [self._make_srv_record('sentinel1.example.com.', 26379)]
        mock_resolver.resolve.return_value = srv_records

        config = {**self.BASE_CONFIG, 'REDIS_SSL': False}
        app = make_app(config)

        mock_sentinel_instance = MagicMock()
        mock_sentinel_module.Sentinel.return_value = mock_sentinel_instance

        s = Sentinel()
        s.init_app(app)

        expected_nodes = [('sentinel1.example.com.', 26379)]
        mock_sentinel_module.Sentinel.assert_called_once_with(
            expected_nodes,
            sentinel_kwargs={},
            db=0,
            password=None,
            socket_timeout=0.1,
            retry_on_timeout=True,
        )

    @patch('pybossa.sentinel.sentinel')
    @patch('pybossa.sentinel.resolver')
    @patch.dict('os.environ', {'REDIS_SENTINELS_DNS': 'sentinels.example.com'})
    def test_dns_resolution_ssl_enabled(self, mock_resolver, mock_sentinel_module):
        """init_app with REDIS_SENTINELS_DNS and SSL enabled passes sentinel_kwargs with ssl."""
        srv_records = [self._make_srv_record('sentinel1.example.com.', 26379)]
        mock_resolver.resolve.return_value = srv_records

        config = {
            **self.BASE_CONFIG,
            'REDIS_SSL': True,
            'REDIS_SSL_CA_CERTS': '/etc/ssl/ca.crt',
        }
        app = make_app(config)

        mock_sentinel_instance = MagicMock()
        mock_sentinel_module.Sentinel.return_value = mock_sentinel_instance

        s = Sentinel()
        s.init_app(app)

        expected_nodes = [('sentinel1.example.com.', 26379)]
        mock_sentinel_module.Sentinel.assert_called_once_with(
            expected_nodes,
            sentinel_kwargs={'ssl': True, 'ssl_ca_certs': '/etc/ssl/ca.crt'},
            db=0,
            password=None,
            socket_timeout=0.1,
            retry_on_timeout=True,
            ssl=True,
            ssl_ca_certs='/etc/ssl/ca.crt',
        )

    @patch('pybossa.sentinel.sentinel')
    @patch('pybossa.sentinel.resolver')
    @patch.dict('os.environ', {'REDIS_SENTINELS_DNS': 'sentinels.example.com'})
    def test_dns_resolution_stores_sentinel_nodes_in_config(self, mock_resolver, mock_sentinel_module):
        """init_app with REDIS_SENTINELS_DNS populates REDIS_SENTINEL and REDIS_SENTINELS in config."""
        srv_records = [
            self._make_srv_record('s1.example.com.', 26379),
            self._make_srv_record('s2.example.com.', 26380),
        ]
        mock_resolver.resolve.return_value = srv_records

        config = {**self.BASE_CONFIG, 'REDIS_SSL': False}
        app = make_app(config)

        s = Sentinel()
        s.init_app(app)

        assert app.config['REDIS_SENTINEL'] == [('s1.example.com.', 26379), ('s2.example.com.', 26380)]
        assert app.config['REDIS_SENTINELS'] == 's1.example.com.:26379,s2.example.com.:26380'
