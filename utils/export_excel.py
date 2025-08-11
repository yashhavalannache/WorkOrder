# utils/export_excel.py

import sqlite3
import pandas as pd

def export_to_excel():
    conn = sqlite3.connect('database/workorders.db')
    df = pd.read_sql_query('''
        SELECT tasks.id, title, description, machine_id, area, deadline,
               status, users.username as assigned_to
        FROM tasks
        JOIN users ON tasks.assigned_to = users.id
    ''', conn)

    file_path = 'exported_tasks.xlsx'
    df.to_excel(file_path, index=False)
    conn.close()
    return file_path
