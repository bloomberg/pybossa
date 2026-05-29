# -*- coding: utf8 -*-
import importlib
import os
import sys
import tempfile
import types
import unittest


class TestImpShim(unittest.TestCase):

    def setUp(self):
        import pybossa.imp_shim as shim
        self.shim = shim

    # --- find_module ---

    def test_find_module_finds_py_file_on_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mod_path = os.path.join(tmpdir, 'mymod.py')
            with open(mod_path, 'w') as f:
                f.write('x = 1\n')

            result = self.shim.find_module('mymod', path=[tmpdir])

            fh, filename, desc = result
            self.assertEqual(filename, mod_path)
            self.assertEqual(desc, ('.py', 'r', self.shim.PY_SOURCE))
            fh.close()

    def test_find_module_finds_package_on_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = os.path.join(tmpdir, 'mypkg')
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, '__init__.py'), 'w') as f:
                f.write('')

            result = self.shim.find_module('mypkg', path=[tmpdir])

            fh, filename, desc = result
            self.assertIsNone(fh)
            self.assertEqual(filename, pkg_dir)
            self.assertEqual(desc, ('', '', self.shim.PKG_DIRECTORY))

    def test_find_module_falls_back_to_importlib_when_path_misses(self):
        # Use 'json' — a pure-Python stdlib module with a real .py file
        result = self.shim.find_module('json', path=['/nonexistent_path_xyz'])

        fh, filename, desc = result
        self.assertIsNotNone(fh)
        self.assertTrue(filename.endswith('.py'))
        self.assertEqual(desc, ('.py', 'r', self.shim.PY_SOURCE))
        fh.close()

    def test_find_module_no_path_finds_stdlib_module(self):
        # Use 'json' — a pure-Python stdlib module with a real .py file
        result = self.shim.find_module('json')

        fh, filename, desc = result
        self.assertIsNotNone(fh)
        self.assertTrue(filename.endswith('.py'))
        self.assertEqual(desc, ('.py', 'r', self.shim.PY_SOURCE))
        fh.close()

    def test_find_module_raises_import_error_for_unknown_module(self):
        with self.assertRaises(ImportError):
            self.shim.find_module('nonexistent_module_xyz_abc')

    def test_find_module_raises_import_error_with_path_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ImportError):
                self.shim.find_module('nonexistent_module_xyz_abc', path=[tmpdir])

    # --- load_module ---

    def test_load_module_loads_py_source_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mod_path = os.path.join(tmpdir, 'loadme.py')
            with open(mod_path, 'w') as f:
                f.write('answer = 42\n')

            module = self.shim.load_module(
                'loadme', None, mod_path, ('.py', 'r', self.shim.PY_SOURCE))

            self.assertIsNotNone(module)
            self.assertEqual(module.answer, 42)

    def test_load_module_loads_package_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = os.path.join(tmpdir, 'mypkg2')
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, '__init__.py'), 'w') as f:
                f.write('value = "pkg"\n')

            module = self.shim.load_module(
                'mypkg2', None, pkg_dir, ('', '', self.shim.PKG_DIRECTORY))

            self.assertIsNotNone(module)
            self.assertEqual(module.value, 'pkg')

    def test_load_module_returns_none_on_bad_file(self):
        result = self.shim.load_module(
            'bad', None, '/nonexistent/path/bad.py', ('.py', 'r', self.shim.PY_SOURCE))

        self.assertIsNone(result)

    # --- acquire_lock / release_lock ---

    def test_acquire_lock_is_noop(self):
        result = self.shim.acquire_lock()
        self.assertIsNone(result)

    def test_release_lock_is_noop(self):
        result = self.shim.release_lock()
        self.assertIsNone(result)

    # --- load_source ---

    def test_load_source_executes_file(self):
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write('loaded = True\nvalue = 99\n')
            path = f.name

        try:
            module = self.shim.load_source('test_loaded', path)
            self.assertTrue(module.loaded)
            self.assertEqual(module.value, 99)
        finally:
            os.unlink(path)

    # --- new_module ---

    def test_new_module_returns_module_type(self):
        mod = self.shim.new_module('testmod')

        self.assertIsInstance(mod, types.ModuleType)
        self.assertEqual(mod.__name__, 'testmod')
