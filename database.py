# database.py
import sqlite3
from typing import List, Tuple


def create_connection():
    conn = sqlite3.connect('user_inputs.db')
    return conn


def create_table(table_name):
    conn = create_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if c.fetchone():
        print(f"Table {table_name} already exists.")
    else:
        c.execute('''CREATE TABLE {} (timestamp TIMESTAMP, user_id INTEGER, mg_dl REAL, mmol_l REAL)'''.format(table_name))
        print(f"Table {table_name} has been created.")
    conn.close()


def insert_data(user_id, mg_dl, mmol_l, timestamp=None, table_name='user_inputs'):
    create_table(table_name)
    conn = create_connection()
    c = conn.cursor()
    if timestamp is None:
        c.execute("INSERT INTO {} (timestamp, user_id, mg_dl, mmol_l) VALUES (datetime('now'), ?, ?, ?)".format(table_name), (user_id, mg_dl, mmol_l))
    else:
        c.execute("INSERT INTO {} (timestamp, user_id, mg_dl, mmol_l) VALUES (?, ?, ?, ?)".format(table_name), (timestamp, user_id, mg_dl, mmol_l))
    conn.commit()
    conn.close()


def select_all_data(user_id: int = None, table_name='user_inputs'):
    create_table(table_name)
    conn = create_connection()
    c = conn.cursor()
    if user_id:
        c.execute("SELECT * FROM ? WHERE user_id=?", (table_name, user_id,))
    else:
        c.execute("SELECT * FROM ?", (table_name,))
    rows = c.fetchall()
    conn.close()
    return rows


def select_history_data(user_id: int, date_from: str, date_to: str, table_name='user_inputs') -> List[Tuple]:
    create_table(table_name)
    conn = create_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM ? WHERE user_id=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp DESC",
              (table_name, user_id, date_from, date_to))
    rows = c.fetchall()
    conn.close()
    return rows
