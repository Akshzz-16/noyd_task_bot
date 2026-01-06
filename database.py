import sqlite3

conn = sqlite3.connect("noyd_tasks.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    assigned_to INTEGER,
    created_by INTEGER,
    status TEXT,
    created_at TEXT,
    completed_at TEXT
)
""")

conn.commit()
conn.close()

print("✅ Database initialized")



