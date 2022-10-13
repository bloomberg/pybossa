"""
This module is to create test data in bulk directly into the database.
* It updates task, task_run and result tables under database.
* For a given entry under task table, it adds multiple entries under task_run
table and a entry under result table.
* The creation date is randomly generated between 2018 and 2022 in order to
simulate real practical use cases so that tasks can be queries by different
task create date ranges.
"""

import argparse
import pandas as pd
import json
from datetime import datetime
import numpy as np
from random import randrange
import logging
from logging.handlers import TimedRotatingFileHandler
import sys

from accessdb import AccessDatabase
import psycopg2
from pybossa.core import db, create_app

root_logger = logging.getLogger()
hdlr = TimedRotatingFileHandler("databulk.log", when="D", backupCount=10)
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s : %(message)s %(module)s %(lineno)s", "%Y-%m-%d %H:%M:%S"
)
hdlr.setFormatter(formatter)
root_logger.addHandler(hdlr)
root_logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
root_logger.addHandler(handler)
logger = logging.getLogger("datapurge")
current_year = datetime.today().year

app = create_app(run_as_server=False)

def create_task(project_id, created, num_answers, priority, year):
    sql = """
        INSERT INTO task
            (created, project_id, state, priority_0, info, n_answers, exported, quorum, calibration)
        VALUES
            (%(created)s, %(project_id)s, %(state)s, %(priority_0)s, %(info)s, %(n_answers)s, %(exported)s, %(quorum)s, %(calibration)s)
        RETURNING id;
    """
    columns_values = dict(
        created=created,
        project_id=project_id, state="completed",
        info=json.dumps({"company": "bberg", "earning_year": year}),
        exported=True, n_answers=num_answers, priority_0=priority,
        quorum=0, calibration=0
    )
    try:
        with AccessDatabase() as db:
            db.execute_sql(sql, columns_values)
            db.conn.commit()
            return db.cursor.fetchone()[0]
    except (Exception, psycopg2.DatabaseError) as error:
        logger.exception("Error: ", error)

def create_task_run(project_id, task_id, user_id, created):
    sql = """
        INSERT INTO task_run
            (created, project_id, task_id, user_id, info, finish_time, timeout, calibration)
        VALUES
            (%(created)s, %(project_id)s, %(task_id)s, %(user_id)s, %(info)s,
            %(finish_time)s, %(timeout)s, %(calibration)s)
        RETURNING id;
    """
    year = randrange(2018, 2022)

    columns_values = dict(
        created=created,
        project_id=project_id, task_id=task_id,
        info=json.dumps({"company": "Bloomberg", "earning_year": year}),
        user_id=user_id, finish_time=created, timeout=30, calibration=0
    )
    try:
        with AccessDatabase() as db:
            db.execute_sql(sql, columns_values)
            db.conn.commit()
            return db.cursor.fetchone()[0]
    except (Exception, psycopg2.DatabaseError) as error:
        logger.exception("Error: ", error)

def create_result(project_id, task_id, task_run_ids, created):
    sql = """
        INSERT INTO result
            (created, project_id, task_id, task_run_ids, info)
        VALUES
            (%(created)s, %(project_id)s, %(task_id)s, %(task_run_ids)s, %(info)s)
        RETURNING id;
    """
    year = randrange(2018, 2022)

    columns_values = dict(
        created=created,
        project_id=project_id, task_id=task_id,
        task_run_ids=task_run_ids,
        info=json.dumps({"company": "Bloomberg", "earning_year": year})
    )
    try:
        with AccessDatabase() as db:
            db.execute_sql(sql, columns_values)
            db.conn.commit()
            return db.cursor.fetchone()[0]
    except (Exception, psycopg2.DatabaseError) as error:
        logger.exception("Error: ", error)


def create_bulk_data(project_id, num_records, random_year):
    for _ in range(num_records):
        month = randrange(1, 12)
        day = randrange(1, 30)
        year = randrange(current_year - 2, current_year) if random_year else current_year
        hour = randrange(1, 23)
        min = randrange(1, 59)
        priority=randrange(10)/10
        num_answers = 3
        created = f"{year}-{month}-{day}T{hour}:{min}:01.604603"
        user_ids = [4, 5, 6]

        with app.app_context():
            task_id = create_task(project_id, created, num_answers, priority, year)
            print("Task created: ", task_id)

            task_run_ids = [create_task_run(project_id, task_id, user_ids[i], created) for i in range(num_answers)]
            print("Taskruns created: ", str(task_run_ids))

            result_id = [create_result(project_id, task_id, task_run_ids, created) for _ in range(randrange(1, 5))]
            print("Result created: ", result_id)

def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--numtasks", dest="num_tasks", type=int, required=True, help="number of tasks to create")
    parser.add_argument("-p", "--projectid", dest="project_id", type=int, required=True, help="project id under which tasks to create")
    parser.add_argument("--random-year", dest="random_year", action="store_true", help="create tasks with random year with parameter passed, else current year")
    args = parser.parse_args()
    return args


def main():
    args = setup_args()
    logger.info(f"number of tasks to create: {args.num_tasks}")
    logger.info(f"number of projects: {args.project_id}")
    logger.info(f"generate tasks with random year: {args.random_year}")
    create_bulk_data(project_id=args.project_id, num_records=args.num_tasks, random_year=args.random_year)

if __name__ == "__main__":
    main()
