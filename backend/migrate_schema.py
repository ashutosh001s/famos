import os
from sqlalchemy import create_engine, MetaData
from dotenv import load_dotenv

load_dotenv()

def migrate_database():
    print("🚀 Starting FamOS Data Migration (SQLite -> PostgreSQL)")
    
    sqlite_uri = 'sqlite:///app.db'
    postgres_uri = os.getenv('DATABASE_URI')
    
    if not postgres_uri or postgres_uri.startswith('sqlite'):
        print("❌ Error: You must set DATABASE_URI to a valid PostgreSQL connection string in your .env file!")
        print("Example: DATABASE_URI=postgresql://user:pass@localhost:5432/famos_db")
        return

    # Extract engines
    sqlite_engine = create_engine(sqlite_uri)
    postgres_engine = create_engine(postgres_uri)
    
    meta = MetaData()
    meta.reflect(bind=sqlite_engine)
    
    print("📦 Found the following tables in SQLite:", meta.tables.keys())
    
    # Mirror identical Schema strictly into Postgres
    meta.create_all(bind=postgres_engine)
    
    # Batch export and import
    with sqlite_engine.connect() as sqlite_conn:
        with postgres_engine.begin() as pg_conn:
            # We must truncate/clean postgres prior to migrating to avoid duplicate PK keys if rerunning
            for table_name, table in meta.tables.items():
                print(f"🧹 Clearing existing data in Postgres table: {table_name}")
                pg_conn.execute(table.delete())

            for table_name, table in meta.tables.items():
                print(f"📥 Migrating data for table: {table_name}...")
                rows = sqlite_conn.execute(table.select()).fetchall()
                if rows:
                    # Convert row tuples back into dicts mapped to columns perfectly
                    data_dicts = [dict(zip(table.columns.keys(), row)) for row in rows]
                    pg_conn.execute(table.insert(), data_dicts)
                    print(f"   ✅ Moved {len(rows)} records.")
                else:
                    print(f"   ⚠️ Table {table_name} is empty. Skipping.")

    print("\n🎉 Migration Complete! Your data is fully safely housed inside PostgreSQL.")
    print("You can now safely restart your Flask application!")

if __name__ == '__main__':
    migrate_database()
