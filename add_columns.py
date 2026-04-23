import sqlite3
conn = sqlite3.connect('comply.db')

conn.execute("""
    CREATE TABLE IF NOT EXISTS fmd_files (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        part_number  TEXT NOT NULL UNIQUE,
        filename     TEXT NOT NULL,
        file_path    TEXT NOT NULL,
        uploaded_at  TEXT DEFAULT (datetime('now'))
    )
""")
conn.execute("UPDATE parts SET is_active=0 WHERE UPPER(description) LIKE '%INACTIVE%'")
conn.execute("ALTER TABLE parts ADD COLUMN is_hidden INTEGER DEFAULT 0")
conn.commit()
conn.close()
print("Done")