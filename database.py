import mysql.connector

def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Mysql@hema05",
        database="online_shopping"
    )
    return conn