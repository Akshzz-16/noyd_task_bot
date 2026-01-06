import sqlite3

conn = sqlite3.connect("noyd_tasks.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER PRIMARY KEY,
    role TEXT
)
""")

conn.commit()
conn.close()

print("✅ user_roles table created")
