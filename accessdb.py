import psycopg2
from pybossa.settings_local import SQLALCHEMY_DATABASE_URI as db_uri

class AccessDatabase:

    def init_conn(self):
        self.conn = psycopg2.connect(db_uri)
        self.cursor = self.conn.cursor() if self.conn else None

    def __init__(self):
        self.init_conn()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cursor.close() if self.cursor else None
        self.conn.close() if self.conn else None

    def execute_sql(self, sql, params):
        if not (self.conn and self.cursor):
            self.reinit_conn()
        self.cursor.execute(sql, params)

