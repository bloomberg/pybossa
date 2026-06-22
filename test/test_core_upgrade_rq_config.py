# -*- coding: utf8 -*-
import unittest
from unittest.mock import MagicMock, patch

from test import with_context
from pybossa.core import upgrade_rq_config, RQ_DASHBOARD_LEGACY_CONFIG_OPTIONS


class TestUpgradeRqConfig(unittest.TestCase):

    def _make_app(self, config=None):
        app = MagicMock()
        app.config = config or {}
        app.logger = MagicMock()
        return app

    # --- RQ_DASHBOARD_REDIS_URL tuple coercion ---

    def test_string_rq_dashboard_redis_url_is_wrapped_in_tuple(self):
        """Lines 144-145: str RQ_DASHBOARD_REDIS_URL is coerced to a 1-tuple."""
        app = self._make_app({'RQ_DASHBOARD_REDIS_URL': 'redis://localhost:6379'})

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis://localhost:6379',))

    def test_tuple_rq_dashboard_redis_url_is_left_unchanged(self):
        """A tuple value must not be double-wrapped."""
        url_tuple = ('redis://host:6379',)
        app = self._make_app({'RQ_DASHBOARD_REDIS_URL': url_tuple})

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'], url_tuple)

    def test_missing_rq_dashboard_redis_url_is_set_from_defaults(self):
        """Line 140-143: missing key gets a default URL from REDIS_MASTER_DNS / REDIS_PORT."""
        app = self._make_app({
            'REDIS_MASTER_DNS': 'myredis.host',
            'REDIS_PORT': 6380,
        })

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis://myredis.host:6380',))

    def test_missing_rq_dashboard_redis_url_falls_back_to_localhost(self):
        """When neither REDIS_MASTER_DNS nor REDIS_PORT are set, use localhost:6379."""
        app = self._make_app({})

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis://localhost:6379',))

    # --- Legacy config option migration ---

    def test_legacy_redis_url_option_is_migrated(self):
        """Line 135-137: REDIS_URL → RQ_DASHBOARD_REDIS_URL."""
        app = self._make_app({'REDIS_URL': 'redis://legacy:6379'})

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis://legacy:6379',))

    def test_all_legacy_options_are_migrated(self):
        """Every legacy key in RQ_DASHBOARD_LEGACY_CONFIG_OPTIONS is copied."""
        config = {old: f'val_{old}' for old in RQ_DASHBOARD_LEGACY_CONFIG_OPTIONS}
        app = self._make_app(config)

        upgrade_rq_config(app)

        for old, new in RQ_DASHBOARD_LEGACY_CONFIG_OPTIONS.items():
            expected = f'val_{old}'
            actual = app.config[new]
            # RQ_DASHBOARD_REDIS_URL gets coerced to a tuple after migration
            if new == 'RQ_DASHBOARD_REDIS_URL':
                self.assertEqual(actual, (expected,),
                                 msg=f'Legacy key {old!r} was not migrated to {new!r}')
            else:
                self.assertEqual(actual, expected,
                                 msg=f'Legacy key {old!r} was not migrated to {new!r}')

    def test_absent_legacy_options_are_not_created(self):
        """Legacy keys not in config must not be added."""
        app = self._make_app({})

        upgrade_rq_config(app)

        for _, new in RQ_DASHBOARD_LEGACY_CONFIG_OPTIONS.items():
            if new != 'RQ_DASHBOARD_REDIS_URL':
                self.assertNotIn(new, app.config)

    # --- REDIS_SENTINELS_DNS path (lines 125-131) ---

    def test_redis_sentinels_dns_env_var_resolves_and_sets_config(self):
        """Lines 125-131: when REDIS_SENTINELS_DNS is set, DNS SRV records are resolved."""
        fake_record = MagicMock()
        fake_record.target.to_text.return_value = 'sentinel1.host.'
        fake_record.port = 26379

        app = self._make_app({})

        with patch.dict('os.environ', {'REDIS_SENTINELS_DNS': 'sentinels.example.com'}), \
             patch('pybossa.core.resolver.resolve', return_value=[fake_record]) as mock_resolve:

            upgrade_rq_config(app)

            mock_resolve.assert_called_once_with('sentinels.example.com', 'SRV')
            self.assertEqual(app.config['REDIS_SENTINEL'],
                             [('sentinel1.host.', 26379)])
            self.assertEqual(app.config['REDIS_SENTINELS'], 'sentinel1.host.:26379')

    def test_redis_sentinels_dns_not_set_logs_info(self):
        """Lines 132-133: absence of REDIS_SENTINELS_DNS logs a message."""
        app = self._make_app({})

        with patch.dict('os.environ', {}, clear=True):
            # Remove key if present
            import os
            os.environ.pop('REDIS_SENTINELS_DNS', None)
            upgrade_rq_config(app)

        app.logger.info.assert_called()
        logged_msg = app.logger.info.call_args_list[0][0][0]
        self.assertIn('REDIS_SENTINELS_DNS', logged_msg)

    def test_missing_rq_dashboard_redis_url_includes_password(self):
        """Lines 143-145: when REDIS_PWD is set, URL includes :password@ auth."""
        app = self._make_app({
            'REDIS_MASTER_DNS': 'redis.host',
            'REDIS_PORT': 6379,
            'REDIS_PWD': 's3cret',
        })

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis://:s3cret@redis.host:6379',))

    def test_missing_rq_dashboard_redis_url_no_password(self):
        """Lines 146-147: when REDIS_PWD is empty, URL has no auth segment."""
        app = self._make_app({
            'REDIS_MASTER_DNS': 'redis.host',
            'REDIS_PORT': 6379,
            'REDIS_PWD': '',
        })

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis://redis.host:6379',))

    def test_multiple_sentinel_dns_records(self):
        """Multiple SRV records produce a comma-separated REDIS_SENTINELS string."""
        records = []
        for host, port in [('s1.host.', 26379), ('s2.host.', 26380)]:
            r = MagicMock()
            r.target.to_text.return_value = host
            r.port = port
            records.append(r)

        app = self._make_app({})

        with patch.dict('os.environ', {'REDIS_SENTINELS_DNS': 'sentinels.example.com'}), \
             patch('pybossa.core.resolver.resolve', return_value=records):

            upgrade_rq_config(app)

            self.assertEqual(app.config['REDIS_SENTINEL'],
                             [('s1.host.', 26379), ('s2.host.', 26380)])
            self.assertEqual(app.config['REDIS_SENTINELS'],
                             's1.host.:26379,s2.host.:26380')

    # --- Sentinel URL construction (lines 151-162) ---

    def test_sentinel_url_from_redis_sentinels_string_no_password(self):
        """Line 151,154-162: when REDIS_SENTINELS string is in config, builds sentinel URL."""
        app = self._make_app({
            'REDIS_SENTINELS': 'sentinel1:26379,sentinel2:26380',
            'REDIS_MASTER': 'my-master',
            'REDIS_DB': 2,
            'REDIS_PWD': '',
        })

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis+sentinel://sentinel1:26379,sentinel2:26380/my-master/2',))

    def test_sentinel_url_from_redis_sentinels_string_with_password(self):
        """Line 157-159: sentinel URL includes password when REDIS_PWD is set."""
        app = self._make_app({
            'REDIS_SENTINELS': 'sentinel1:26379',
            'REDIS_MASTER': 'mymaster',
            'REDIS_DB': 0,
            'REDIS_PWD': 'p@ss',
        })

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis+sentinel://:p%40ss@sentinel1:26379/mymaster/0',))

    def test_sentinel_url_built_from_redis_sentinel_list(self):
        """Line 152-153: when REDIS_SENTINELS string is absent but REDIS_SENTINEL list
        exists, sentinels_str is constructed from the list."""
        app = self._make_app({
            'REDIS_SENTINEL': [('host1', 26379), ('host2', 26380)],
            'REDIS_MASTER': 'mymaster',
            'REDIS_DB': 0,
            'REDIS_PWD': '',
        })

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis+sentinel://host1:26379,host2:26380/mymaster/0',))

    def test_sentinel_url_from_list_with_password(self):
        """Sentinel URL from REDIS_SENTINEL list includes password."""
        app = self._make_app({
            'REDIS_SENTINEL': [('sentinel-node', 26379)],
            'REDIS_MASTER': 'master1',
            'REDIS_DB': 3,
            'REDIS_PWD': 'secret',
        })

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis+sentinel://:secret@sentinel-node:26379/master1/3',))

    def test_sentinel_url_defaults_master_name_and_db(self):
        """When REDIS_MASTER and REDIS_DB are absent, defaults to 'mymaster' and 0."""
        app = self._make_app({
            'REDIS_SENTINELS': 'sentinel1:26379',
            'REDIS_PWD': '',
        })

        upgrade_rq_config(app)

        self.assertEqual(app.config['RQ_DASHBOARD_REDIS_URL'],
                         ('redis+sentinel://sentinel1:26379/mymaster/0',))
