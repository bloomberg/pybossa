import ast
from pathlib import Path

SAFE_CONFIG = {
    'SECRET_KEY': 'deployment-session-secret',
    'ITSDANGEROUSKEY': 'deployment-signing-secret',
    'CRYPTOPAN_KEY': '0123456789abcdef0123456789abcdef',
}


def _config_security():
    from pybossa import config_security
    return config_security


def test_configure_app_validates_secrets_after_settings_override():
    core_path = Path(__file__).parents[1] / 'pybossa' / 'core.py'
    tree = ast.parse(core_path.read_text())
    configure_app = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == 'configure_app')
    calls = [
        (node.lineno, getattr(node.func, 'id', None) or
         getattr(node.func, 'attr', None))
        for node in ast.walk(configure_app)
        if isinstance(node, ast.Call)
    ]
    settings_load_lines = [
        line for line, name in calls
        if name in ('from_object', 'from_pyfile')
    ]
    validation_lines = [
        line for line, name in calls
        if name == 'validate_secret_keys'
    ]

    assert validation_lines
    assert max(settings_load_lines) < validation_lines[0]


def _assert_invalid_config(key, value):
    config = dict(SAFE_CONFIG, **{key: value})
    try:
        _config_security().validate_secret_keys(config)
    except RuntimeError as error:
        assert key in str(error)
    else:
        raise AssertionError('{} was accepted'.format(key))


def test_published_secret_values_refuse_startup():
    for key, published_value in (
        ('SECRET', 'foobar'),
        ('SECRET_KEY', 'my-session-secret'),
        ('ITSDANGEROUSKEY', 'its-dangerous-key'),
        ('CRYPTOPAN_KEY', '32-char-str-for-AES-key-and-pad.'),
    ):
        yield _assert_invalid_config, key, published_value


def test_missing_required_secret_refuses_startup():
    for key in ('SECRET_KEY', 'ITSDANGEROUSKEY', 'CRYPTOPAN_KEY'):
        yield _assert_invalid_config, key, None


def test_testing_config_allows_fixture_secrets():
    _config_security().validate_secret_keys({
        'TESTING': True,
        'SECRET_KEY': 'my-session-secret',
        'ITSDANGEROUSKEY': 'its-dangerous-key',
        'CRYPTOPAN_KEY': '32-char-str-for-AES-key-and-pad.',
    })


def test_cryptopan_key_is_stable_and_deployment_specific():
    first_key = _config_security().derive_cryptopan_key(
        'deployment-session-secret')
    second_key = _config_security().derive_cryptopan_key(
        'different-session-secret')

    assert len(first_key.encode('utf-8')) == 32
    assert first_key != second_key
    assert first_key != '32-char-str-for-AES-key-and-pad.'
    _config_security().validate_secret_keys(
        dict(SAFE_CONFIG, CRYPTOPAN_KEY=first_key))
