"""
Schema migration: v1 → v2

Changes:
  - Transaction: add `description` column (VARCHAR 300, nullable)
  - Document: add `stored_filename` column (VARCHAR 300), replace old `file_path`
  - Task: make `created_by` NOT NULL (if your db supports it inline)

Run:  python migrate.py
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'app.db')


def run():
    if not os.path.exists(DB_PATH):
        print(f'[migrate] DB not found at {DB_PATH} — skipping (will be created fresh on first run)')
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. transactions.description
    cols = [r[1] for r in cur.execute("PRAGMA table_info(transactions)").fetchall()]
    if 'description' not in cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN description VARCHAR(300)")
        print('[migrate] Added transactions.description')
    else:
        print('[migrate] transactions.description already exists — skip')

    # 2. documents.stored_filename
    cols = [r[1] for r in cur.execute("PRAGMA table_info(documents)").fetchall()]
    if 'stored_filename' not in cols:
        # Back-fill stored_filename from existing file_path (basename only)
        cur.execute("ALTER TABLE documents ADD COLUMN stored_filename VARCHAR(300)")
        cur.execute("""
            UPDATE documents
            SET stored_filename = REPLACE(file_path, RTRIM(file_path, REPLACE(file_path, '/', '')), '')
            WHERE stored_filename IS NULL OR stored_filename = ''
        """)
        # Fallback for Windows paths
        cur.execute("""
            UPDATE documents
            SET stored_filename = REPLACE(file_path, RTRIM(file_path, REPLACE(file_path, '\', '')), '')
            WHERE stored_filename IS NULL OR stored_filename = ''
        """)
        print('[migrate] Added documents.stored_filename and back-filled from file_path')
    else:
        print('[migrate] documents.stored_filename already exists — skip')

    # 3. users.phone_hash
    cols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
    if 'phone_hash' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN phone_hash VARCHAR(50)")
        print('[migrate] Added users.phone_hash')
    else:
        print('[migrate] users.phone_hash already exists — skip')

    conn.commit()
    conn.close()
    print('[migrate] Done.')


if __name__ == '__main__':
    run()
