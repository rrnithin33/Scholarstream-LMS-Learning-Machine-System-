import MySQLdb
import os

DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = 'ewcm'
DB_NAME = 'scholarstream_lms'

def init_db():
    try:
        # Connect to MySQL first without DB name to create it if it doesn't exist
        db = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASSWORD)
        cursor = db.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        db.select_db(DB_NAME)
        
        with open('schema.sql', 'r') as f:
            sql_script = f.read()
        
        # Split by semicolon but ignore inside quotes (simplistic split for this schema)
        for statement in sql_script.split(';'):
            if statement.strip():
                cursor.execute(statement)
        
        db.commit()
        print("Database initialized successfully.")
        db.close()
    except Exception as e:
        print(f"Error initializing database: {e}")

if __name__ == "__main__":
    init_db()
