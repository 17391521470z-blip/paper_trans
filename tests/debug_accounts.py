import sqlite3
conn = sqlite3.connect(r'd:\AI编程\PDF论文翻译\paper-translate\backend\paper_translate.db')
cur = conn.cursor()
print("=== users ===")
cur.execute('SELECT id, email FROM users WHERE email IS NOT NULL')
for r in cur.fetchall():
    print(r)
print("\n=== latest task ===")
cur.execute("SELECT id, status, filename, source_url, error_message FROM tasks ORDER BY created_at DESC LIMIT 3")
for r in cur.fetchall():
    print(r)
