import sqlite3
from pathlib import Path
from config import get_settings

def migrate():
    settings = get_settings()
    db_path = settings.db_path
    if not db_path.exists():
        print("Database not found, no migration needed.")
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if we need to migrate UNIQUE constraint
    cursor.execute("PRAGMA table_info(invoices)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # If table is already migrated (or not), we can just try to execute the migration safely
    # SQLite doesn't support DROP CONSTRAINT, so we need to recreate the table
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        # Check if index exists on content_hash
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='invoices'")
        sql = cursor.fetchone()[0]
        if "UNIQUE(created_by, content_hash)" in sql:
            print("Already migrated.")
            return

        print("Migrating invoices table...")
        
        cursor.execute("CREATE TABLE invoices_new ("
                       "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                       "invoice_number TEXT NOT NULL,"
                       "vendor_name TEXT NOT NULL,"
                       "document_path TEXT NOT NULL,"
                       "subtotal REAL NOT NULL DEFAULT 0,"
                       "tax REAL NOT NULL DEFAULT 0,"
                       "total REAL NOT NULL DEFAULT 0,"
                       "currency TEXT NOT NULL DEFAULT 'USD',"
                       "content TEXT NOT NULL,"
                       "content_hash TEXT NOT NULL,"
                       "metadata_json TEXT NOT NULL DEFAULT '{}',"
                       "created_by INTEGER NOT NULL DEFAULT 1,"
                       "created_at TEXT NOT NULL,"
                       "FOREIGN KEY (created_by) REFERENCES users(id),"
                       "UNIQUE(created_by, content_hash)"
                       ")")
                       
        cursor.execute("INSERT INTO invoices_new SELECT id, invoice_number, vendor_name, document_path, subtotal, tax, total, currency, content, content_hash, metadata_json, COALESCE(created_by, 1), created_at FROM invoices")
        
        cursor.execute("DROP TABLE invoices")
        cursor.execute("ALTER TABLE invoices_new RENAME TO invoices")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_hash ON invoices (content_hash)")
        
        conn.commit()
        print("Migration complete.")
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
