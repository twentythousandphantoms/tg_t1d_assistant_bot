import pytest
from database import create_connection, create_table, insert_data, select_all_data


def test_create_connection():
    conn = create_connection()
    assert conn is not None
    conn.close()


def test_create_table():
    conn = create_connection()
    create_table('user_inputs')
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = c.fetchall()
    assert ('user_inputs',) in tables
    conn.close()


def test_insert_data():
    conn = create_connection()
    create_table('user_inputs')
    insert_data(1, 100, 5.6, '2022-01-01 10:00:00')
    c = conn.cursor()
    c.execute("SELECT * FROM user_inputs")
    data = c.fetchall()
    assert ('2022-01-01 10:00:00', 1, 100.0, 5.6) in data
    conn.close()


def test_select_all_data():
    conn = create_connection()
    create_table('user_inputs')
    insert_data(1, 100, 5.6, '2022-01-01 10:00:00')
    insert_data(2, 110, 6.1, '2022-01-01 11:00:00')
    data = select_all_data()
    assert ('2022-01-01 10:00:00', 1, 100, 5.6) in data
    assert ('2022-01-01 11:00:00', 2, 110, 6.1) in data
    conn.close()


def test_delete_data():
    conn = create_connection()
    c = conn.cursor()
    c.execute("DELETE FROM user_inputs WHERE user_id in (1,2)")
    conn.commit()
    data = select_all_data()
    assert ('2022-01-01 10:00:00', 1, 100.0, 5.6) not in data
    conn.close()
