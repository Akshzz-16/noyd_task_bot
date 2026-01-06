import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    assigned_to BIGINT,
    created_by BIGINT,
    status TEXT,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
)
""")

conn.commit()
conn.close()
print("✅ tasks table created")
