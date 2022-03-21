import argparse
import pandas as pd
import json
import datetime
import numpy as np
import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import psycopg2

from accessdb import AccessDatabase

root_logger = logging.getLogger()
hdlr = TimedRotatingFileHandler("purgedata.log", when="D", backupCount=10)
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


def get_data_to_purge(duration):
    sql = f"""
        SELECT project_id, count(*) as n_tasks, min(created) as first_create_date, max(created) as last_create_date
        FROM task
        WHERE TO_DATE(created, 'YYYY-MM-DD"T"HH24:MI:SS.US') <= NOW() - '{duration} months' :: INTERVAL
        GROUP BY project_id
        ORDER BY n_tasks DESC;
    """
    logger.info("get_data_to_purge sql")
    logger.info(sql)
    with AccessDatabase() as db:
        data = pd.read_sql_query(sql, db.conn)
    return data


def get_tasks_to_purge(project_id, duration):
    sql = f"""
        SELECT id, created
        FROM task
        WHERE project_id={project_id} AND
        TO_DATE(created, 'YYYY-MM-DD"T"HH24:MI:SS.US') <= NOW() - '{duration} months' :: INTERVAL
        ORDER BY created;
    """
    with AccessDatabase() as db:
        tasks = pd.read_sql_query(sql, db.conn)
    return tasks


def generate_sql_cols_vals(table_prefix, data):
    columns, columns_placeholders, columns_values = "", "", {}
    if data.empty:
        return columns, columns_placeholders, columns_values

    data_cols, col_placeholders = [], []
    for col in data.columns:
        val = data[col].values[0]
        if val is None:
            continue

        col_id = f"{table_prefix}_{col}"
        if isinstance(val, dict):
            val = json.dumps(val)
            data_cols.append(col)
            col_placeholders.append(f"%({col_id})s")
            columns_values[col_id] = val
            continue

        if isinstance(val, list):
            data_cols.append(col)
            col_placeholders.append(f"%({col_id})s")
            columns_values[col_id] = val
            continue

        if isinstance(val, np.int64) or isinstance(val, np.int):
            data_cols.append(col)
            col_placeholders.append(f"%({col_id})s")
            columns_values[col_id] = int(val)
            continue

        # True/False -> true/false
        if isinstance(val, bool):
            val = "true" if val else "false"
            data_cols.append(col)
            col_placeholders.append(f"%({col_id})s")
            columns_values[col_id] = val
            continue

        # convert value to sql string value
        val = str(data[col].values[0])
        data_cols.append(col)
        col_placeholders.append(f"%({col_id})s")
        columns_values[col_id] = val

    if not(data_cols and columns_values and col_placeholders):
        return columns, columns_placeholders, columns_values

    col = "updated"
    data_cols.append(col)
    col_id = f"{table_prefix}_{col}"
    col_placeholders.append(f"%({col_id})s")
    columns_values[col_id] = datetime.datetime.utcnow()

    columns = ", ".join(data_cols)
    columns_placeholders = ", ".join(col_placeholders)

    return columns, columns_placeholders, columns_values

def generate_multiple_records(table, records):
    isql, dsql, columns_dict = "", "", {}
    table_prefixes = {"task_run": "tr", "result": "r"}

    table_prefix = table_prefixes[table]

    if records.empty:
        return isql, dsql, columns_dict

    for i, record in records.iterrows():
        data = pd.DataFrame(record).transpose()
        columns, col_placeholders, col_dict = generate_sql_cols_vals(f"{table_prefix}_{i}", data)
        if not(columns or col_placeholders or col_dict):
            continue

        isql += f"INSERT INTO {table}_archived({columns}) VALUES({col_placeholders});"
        columns_dict.update(col_dict)
    dsql = f"DELETE FROM {table} WHERE project_id = %(project_id)s AND task_id = %(task_id)s;"
    return isql, dsql, columns_dict



def purge_task_data(task_id, project_id):
    # make copy of task into respective archived table
    # delete task data from results, task_runs, task table
    logger.info(f"Purging task data. project: {project_id}, task: {task_id}")
    with AccessDatabase() as db:
        task_data = pd.read_sql_query(f"SELECT * FROM task WHERE id={task_id}", db.conn)
        task_run_data = pd.read_sql_query(f"SELECT * FROM task_run WHERE task_id={task_id}", db.conn)
        result_data = pd.read_sql_query(f"SELECT * FROM result WHERE task_id={task_id}", db.conn)

    if task_data.empty:
        logger.info("Missing data for task id", task_id)
        logger.info("task_data", task_data)
        logger.info("task_run_data", task_run_data)
        logger.info("result_data", result_data)
        return

    insert_sql, delete_sql = "", ""
    # archive task data
    task_columns, task_col_placeholders, task_col_dict = generate_sql_cols_vals("t", task_data)
    if task_columns and task_col_placeholders and task_col_dict:
        insert_sql += f"INSERT INTO task_archived({task_columns}) VALUES({task_col_placeholders});"
        delete_sql += f"DELETE FROM task WHERE project_id = %(project_id)s AND id = %(task_id)s;"

    # archive task_run data
    insert_task_run, delete_task_run, task_run_col_dict = generate_multiple_records("task_run", task_run_data)
    insert_sql += insert_task_run
    delete_sql += delete_task_run

    # archive result data
    insert_result, delete_result, result_col_dict = generate_multiple_records("result", result_data)
    insert_sql += insert_result
    delete_sql += delete_result

    # combine task, task_run, result, col-val dict
    columns_values = {}
    for d in [task_col_dict, task_run_col_dict, result_col_dict]:
        columns_values.update(d)

    # add task_id, project_id for delete queries
    columns_values["task_id"] = task_id
    columns_values["project_id"] = project_id
    try:
        sql = f"""
            BEGIN;
            {insert_sql}
            SET session_replication_role = replica;
            {delete_sql}
            SET session_replication_role = DEFAULT;
            COMMIT;
        """

        # # TODO: disable delete during testing. Replace following with commented code above
        # sql = f"""
        #     BEGIN;
        #     {insert_sql}
        #     COMMIT;
        # """

        with AccessDatabase() as db:
            db.execute_sql(sql, columns_values)
    except (Exception, psycopg2.DatabaseError) as error:
        logger.exception("Error: ", error)


def purge_data(data, duration):
    # get all projects from data
    project_ids = data["project_id"].tolist()
    for project_id in project_ids:
        tasks = get_tasks_to_purge(project_id, duration)
        task_ids = tasks["id"].tolist()
        for task_id in task_ids:
            purge_task_data(task_id, project_id)


def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--duration", dest="duration", type=int, choices=[1, 6, 12, 24, 36], required=True, help="duration - integer value in months")
    parser.add_argument("-n", "--num_projects", dest="num_projects", type=int, required=True, help="top n number of projects")
    parser.add_argument("-p", "--purge", dest="purge", type=bool, default=False, help="purge data")
    args = parser.parse_args()
    return args


def main():
    args = setup_args()
    duration = args.duration
    num_projects = args.num_projects
    purge = args.purge

    data = get_data_to_purge(duration=duration)
    if data.empty:
        logger.info(f"No projects exists with data older than {duration} months")
        logger.info("End purge data script")
        return

    data.to_csv("purgedata.csv", index=False)
    logger.info(f"List of projects data older than {duration} months")
    logger.info(data)
    logger.info(f"Top {num_projects} projects data can be purged")
    logger.info(data.head(num_projects))
    if not purge:
        logger.info("Data purge not opted. Process complete...")
        return

    confirm_purge = input("Data will be purged now. Confirm (y/n)")
    if not confirm_purge in ['y', "Y"]:
        logger.info("Purge data cancelled upon confirmation.")
        logger.info("End purge data script")
        return

    logger.info(f"Purge data for top {num_projects} projects")
    purge_data(data.head(num_projects), duration=duration)
    logger.info("End purge data script")


if __name__ == "__main__":
    main()
