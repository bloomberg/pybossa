import hashlib
import hmac


PUBLISHED_SECRET_VALUES = {
    'SECRET': 'foobar',
    'SECRET_KEY': 'my-session-secret',
    'ITSDANGEROUSKEY': 'its-dangerous-key',
    'CRYPTOPAN_KEY': '32-char-str-for-AES-key-and-pad.',
}

REQUIRED_SECRET_KEYS = (
    'SECRET_KEY',
    'ITSDANGEROUSKEY',
    'CRYPTOPAN_KEY',
)


def derive_cryptopan_key(secret_key):
    if not secret_key:
        return None
    return hmac.new(
        secret_key.encode('utf-8'),
        b'pybossa-cryptopan-v1',
        hashlib.sha256,
    ).hexdigest()[:32]


def validate_secret_keys(config):
    if config.get('TESTING'):
        return

    unsafe_keys = {
        key for key, published_value in PUBLISHED_SECRET_VALUES.items()
        if config.get(key) == published_value
    }
    unsafe_keys.update(
        key for key in REQUIRED_SECRET_KEYS
        if not config.get(key)
    )

    cryptopan_key = config.get('CRYPTOPAN_KEY')
    if cryptopan_key and len(cryptopan_key.encode('utf-8')) != 32:
        unsafe_keys.add('CRYPTOPAN_KEY')

    if unsafe_keys:
        raise RuntimeError(
            'Refusing to start with unsafe secret configuration: {}'.format(
                ', '.join(sorted(unsafe_keys))))
