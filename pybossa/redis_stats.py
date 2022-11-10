from pybossa.core import db, sentinel

session = db.slave_session


def increase_bitfield_in_redis(key, offset_list, sql_list,
                               increase_values, encoding='u32'):
    """
    increase key in Redis using bitfield data structure. If the key doesn't exist,
    using the 'sql_query' to get the data from DB and then update Redis
    """
    redis_conn = sentinel.master
    bitfield = redis_conn.bitfield(key)

    for offset in offset_list:
        bitfield = bitfield.get(encoding, offset)
    counts = bitfield.execute()

    for i in range(len(counts)):
        increase_count = increase_values[i]
        if counts[i] == 0:  # data not in Redis
            results = session.execute(sql_list[i])
            for row in results:
                counts[i] = row.n_tasks
            increase_count = counts[i]
        bitfield.incrby(encoding, offset_list[i], increase_count)

    bitfield.execute()


def set_bitfield_in_redis(key, offset_list, sql_list,
                          values=None, encoding='u32'):
    """
    set key in Redis using bitfield data structure. If the values is None
    using the 'sql_query' to get the data from DB and then update Redis
    """
    redis_conn = sentinel.master
    bitfield = redis_conn.bitfield(key)

    if values is None:
        values = [0] * len(sql_list)

    for i in range(len(sql_list)):
        value = values[i]
        if value == 0:  # set data using the SQL count
            results = session.execute(sql_list[i])
            for row in results:
                value = row.n_tasks
        bitfield.set(encoding, offset_list[i], value)

    bitfield.execute()


def set_project_stats_in_redis(project_id, operation=None, **kwargs):
    """
    params: operation: batch_delete, insert, delete, update
    """
    project_stats_key = f"project:{project_id}:stats"

    # offset '#0': n_tasks, offset '#1': n_available_tasks
    offset_list = ['#0', '#1']
    n_tasks_sql = f"SELECT count(*) AS n_tasks  FROM task WHERE project_id={project_id}"
    n_available_tasks_sql = f'''SELECT COUNT(*) AS n_tasks FROM task
                                    WHERE project_id={project_id} AND state !='completed'
                                    AND state !='enrich';'''
    sql_list = [n_tasks_sql, n_available_tasks_sql]

    if operation == "batch_delete" or operation == "bulk_redundancy_update":
        set_bitfield_in_redis(project_stats_key, offset_list, sql_list)
    elif operation == "insert":  # new task
        increase_values = [1] * len(offset_list)
        increase_bitfield_in_redis(project_stats_key, offset_list, sql_list, increase_values)
    elif operation == "delete":
        increase_values = [-1] * len(offset_list)
        # if tasks is completed, #1 offset keeps the same
        if kwargs.get("task") and kwargs.get("task").state == 'completed':
            increase_values[1] = 0
        increase_bitfield_in_redis(project_stats_key, offset_list, sql_list, increase_values)
    elif operation == "complete_task_update":
        increase_values = [0, -1]
        increase_bitfield_in_redis(project_stats_key, offset_list, sql_list, increase_values)
    elif operation == "redundancy_update":
        increase_values = [0] * len(offset_list)
        old_task_state = kwargs.get("old_task_state")
        new_task_state = kwargs.get("new_task_state")
        if old_task_state == "ongoing" and new_task_state == "completed":
            increase_values[1] = -1
            increase_bitfield_in_redis(project_stats_key, offset_list, sql_list, increase_values)
        elif old_task_state == "completed" and new_task_state == "ongoing":
            increase_values[1] = 1
            increase_bitfield_in_redis(project_stats_key, offset_list, sql_list, increase_values)