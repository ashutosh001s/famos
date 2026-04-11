"""
FamOS Database Migration Script — run after every major update.
Safe to run multiple times (checks before altering).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from app.models import Family, generate_invite_code
import sqlalchemy as sa

app = create_app()

MIGRATIONS = [
    # (table, column, definition)
    ('families',  'invite_code', 'VARCHAR(10)'),
    ('tasks',     'created_by',  'INTEGER'),
    ('groceries', 'category',    "VARCHAR(50) DEFAULT 'Other'"),
]

with app.app_context():
    inspector = sa.inspect(db.engine)
    conn = db.engine.connect()

    for table, column, definition in MIGRATIONS:
        existing = [c['name'] for c in inspector.get_columns(table)]
        if column not in existing:
            print(f"  + Adding {table}.{column}...")
            conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
            conn.commit()
            print(f"    ✓ Done")
        else:
            print(f"  ✓ {table}.{column} already exists")

    # Backfill invite codes for existing families that have none
    families_missing_code = Family.query.filter(
        (Family.invite_code == None) | (Family.invite_code == '')
    ).all()
    for family in families_missing_code:
        code = generate_invite_code()
        while Family.query.filter_by(invite_code=code).first():
            code = generate_invite_code()
        family.invite_code = code
        print(f"  ✓ Generated invite code for '{family.name}': {code}")
    if families_missing_code:
        db.session.commit()

    # Ensure all tables exist (new installs)
    db.create_all()
    print("\n✅ Migration complete.")

    # Print all family invite codes for reference
    print("\n── Family Invite Codes ──────────────────")
    for f in Family.query.all():
        members = len(f.users)
        print(f"  {f.name:30s}  Code: {f.invite_code}  ({members} member{'s' if members != 1 else ''})")
    print("─────────────────────────────────────────")
