import logging
import os
from redis import StrictRedis
from redis.sentinel import Sentinel
from rq_scheduler.scheduler import Scheduler
from time import sleep
import pybossa.app_settings as app_settings


logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)


def run_scheduler():
    ssl_enabled = app_settings.config.get('REDIS_SSL', False)
    conn_kwargs = {
        'db': app_settings.config.get('REDIS_DB') or 0,
        'password': app_settings.config.get('REDIS_PWD'),
        'ssl': ssl_enabled,
        'ssl_ca_certs': app_settings.config.get('REDIS_SSL_CA_CERTS'),
    }
    if all(app_settings.config.get(attr) for attr in
        ['REDIS_MASTER_DNS', 'REDIS_PORT']):
        master = StrictRedis(host=app_settings.config['REDIS_MASTER_DNS'],
            port=app_settings.config['REDIS_PORT'], **conn_kwargs)
    else:
        sentinel_kwargs = {'ssl': ssl_enabled} if ssl_enabled else {}
        sentinel = Sentinel(app_settings.config['REDIS_SENTINEL'],
                            sentinel_kwargs=sentinel_kwargs)
        master = sentinel.master_for(app_settings.config['REDIS_MASTER'], **conn_kwargs)
    scheduler = Scheduler(connection=master)
    while True:
        try:
            scheduler.run()
        except ValueError:
            sleep(600)


if __name__ == '__main__':
    run_scheduler()
