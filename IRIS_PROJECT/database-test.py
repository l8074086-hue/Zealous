import sqlite3

conn = sqlite3.connect("agent_memory.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS conversation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        role TEXT,
        content TEXT
    )
""")

def log_message(role, content):
    cur.execute("INSERT INTO conversation_history (role, content) VALUES (?,?)", (role, content))
    conn.commit()
def fetch_memories():
    cur.execute("SELECT * FROM conversation_history")
    return cur.fetchall()


log_message("user", "Hello")
log_message("AI", "Hi!")
print(fetch_memories())

conn.close()
