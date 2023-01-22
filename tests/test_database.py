import sqlite3
import pytest
from main import create_connection, create_table, insert_data, select_all_data


def test_create_connection():
    conn = create_connection()
    assert conn is not None
    conn.close()


def test_create_table():
    conn = create_connection()
    create_table(conn)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = c.fetchall()
    assert ('user_inputs',) in tables
    conn.close()


def test_insert_data():
    conn = create_connection()
    create_table(conn)
    insert_data(conn, (1, '2022-01-01 10:00:00', 100, 5.6))
    c = conn.cursor()
    c.execute("SELECT * FROM user_inputs")
    data = c.fetchall()
    assert (1, '2022-01-01 10:00:00', 100, 5.6) in data
    conn.close()


def test_select_all_data():
    conn = create_connection()
    create_table(conn)
    insert_data(conn, (1, '2022-01-01 10:00:00', 100, 5.6))
    insert_data(conn, (1, '2022-01-02 12:00:00', 120, 6.7))
    data = select_all_data(conn)
    assert (1, '2022-01-01 10:00:00', 100, 5.6) in data
    assert (1, '2022-01-02 12:00:00', 120, 6.7) in data
    conn.close()
