# -*- coding: utf8 -*-
"""Focused regressions for dynamic links in project templates.

This file is intentionally runnable directly without the DB-backed test package bootstrap:

    python3 pybossa/test/test_external_link_templates.py
"""

import html
from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import unittest

THEME = (Path(__file__).parents[1] / 'pybossa' / 'themes' / 'default' /
         'templates' / 'projects')
URL_UTILS = Path(__file__).parents[1] / 'pybossa' / 'url_utils.py'
SPEC = importlib.util.spec_from_file_location('url_utils', URL_UTILS)
url_utils = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(url_utils)
http_url_or_none = url_utils.http_url_or_none


class _AnchorParser(HTMLParser):

    def handle_starttag(self, tag, attrs):
        if tag == 'a' and not hasattr(self, 'attrs'):
            self.attrs = dict(attrs)


class ExternalLinkTemplateTest(unittest.TestCase):

    def _line(self, filename, needle):
        lines = (THEME / filename).read_text().splitlines()
        return next(line for line in lines if needle in line)

    def _anchor_attrs(self, source, expression, value):
        rendered = source.replace(expression, html.escape(value, quote=True))
        parser = _AnchorParser()
        parser.feed(rendered.strip())
        return parser.attrs

    def test_task_column_value_remains_one_attribute(self):
        value = 'column "name" data-extra=marker'
        expression = '{{column_name}}'
        for filename in ('tasks_browse.html', 'tasks_browse.webpack.ejs'):
            source = self._line(filename, 'data-value="{{column_name}}"')
            attrs = self._anchor_attrs(source, expression, value)
            self.assertEqual(attrs['data-value'], value)
            self.assertNotIn('data-extra', attrs)

    def test_dynamic_hrefs_are_quoted(self):
        cases = (
            ('href="{{ guidelines_ref_url }}"', '{{ guidelines_ref_url }}'),
            ('href="{{ task_presenter_ref_url }}"', '{{ task_presenter_ref_url }}'),
            ("href=\"{{ sync_source_url + '/project/' + project.short_name }}\"",
             "{{ sync_source_url + '/project/' + project.short_name }}"),
            ('href="{{ sync_ref_url }}"', '{{ sync_ref_url }}'),
        )
        value = 'https://example.test/"path" data-extra=marker'
        for needle, expression in cases:
            source = self._line('task_presenter_editor.html', needle)
            attrs = self._anchor_attrs(source, expression, value)
            self.assertEqual(attrs['href'], value)
            self.assertNotIn('data-extra', attrs)

    def test_only_absolute_http_urls_are_linkable(self):
        accepted = (
            'http://example.test/path',
            'https://example.test/path?key=value#fragment',
            'HTTPS://example.test/path',
        )
        rejected = (
            None,
            12,
            '',
            '/relative/path',
            '//example.test/path',
            'mailto:user@example.test',
            'custom:marker',
            'javascript:alert(1)',
            'data:text/html,<script>alert(1)</script>',
            'https:///missing-host',
            'https://example.test:invalid-port/path',
            'https://[invalid-host/path',
        )
        for value in accepted:
            self.assertEqual(http_url_or_none(value), value)
        for value in rejected:
            self.assertIsNone(http_url_or_none(value))


if __name__ == '__main__':
    unittest.main()
