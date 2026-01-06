import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_roles (
    user_id BIGINT PRIMARY KEY,
    role TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS admin_logs (
    id SERIAL PRIMARY KEY,
    admin_id BIGINT,
    action TEXT,
    target TEXT,
    timestamp TIMESTAMP
)
""")

conn.commit()
conn.close()
print("✅ user_roles and admin_logs tables created")
