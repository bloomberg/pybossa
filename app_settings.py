import imp
import os


def _load_module_file_as_dict(path):
    module = imp.load_source('module', path)
    return {
        name: getattr(module, name)
        for name in dir(module)
        if not name.startswith('__')
    }


def _load_config():
    config_path, config = None, {}
    upref_mdata_path, upref_mdata = None, {}
    if os.environ.get('PYBOSSA_SETTINGS'):
        config_path = os.path.abspath(os.environ.get('PYBOSSA_SETTINGS'))
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(here, 'settings_local.py')
    if os.path.exists(config_path):
        os.environ['PYBOSSA_SETTINGS'] = config_path
        config = _load_module_file_as_dict(config_path)
    upref_mdata_path = os.path.join(os.path.dirname(config_path), 'settings_upref_mdata.py')
    if os.path.exists(upref_mdata_path):
        upref_mdata = _load_module_file_as_dict(upref_mdata_path)
    else:
        upref_mdata_path = None
    return config_path, config, upref_mdata_path, upref_mdata


config_path, config, upref_mdata_path, upref_mdata = _load_config()
