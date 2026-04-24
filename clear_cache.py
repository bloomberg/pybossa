from redis.sentinel import Sentinel
from pybossa.settings_local import REDIS_SENTINEL as RS
import pybossa.settings_local as settings
from redis import StrictRedis

db = getattr(settings, 'REDIS_DB', 0)
ssl = getattr(settings, 'REDIS_SSL', False)
ssl_ca_certs = getattr(settings, 'REDIS_SSL_CA_CERTS', None)
if all(hasattr(settings, attr) for attr in
    ['REDIS_MASTER_DNS', 'REDIS_PORT']):
    conn = StrictRedis(host=settings.REDIS_MASTER_DNS,
        port=settings.REDIS_PORT, db=db, ssl=ssl, ssl_ca_certs=ssl_ca_certs)
else:
    sentinel_kwargs = {'ssl': ssl} if ssl else {}
    sentinel = Sentinel(RS, sentinel_kwargs=sentinel_kwargs)
    conn = sentinel.master_for('mymaster', ssl=ssl, ssl_ca_certs=ssl_ca_certs)

cache_items = conn.keys(pattern='{}*'.format(settings.REDIS_KEYPREFIX))
for item in cache_items:
    conn.delete(item)
