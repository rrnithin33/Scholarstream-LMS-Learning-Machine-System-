import MySQLdb

DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = 'ewcm'
DB_NAME = 'scholarstream_lms'

def verify():
    try:
        db = MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASSWORD, db=DB_NAME)
        cursor = db.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print(f"Connected to database. Tables: {[t[0] for t in tables]}")
        db.close()
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    verify()
