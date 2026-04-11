"""
FamOS Database Setup Script
Run this once on a fresh server. Safe to run again — won't lose data.

For development: delete instance/app.db first to start completely fresh.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from app.models import Family, generate_invite_code

app = create_app()

with app.app_context():
    # Create all tables (skips tables that already exist)
    db.create_all()
    print("✓ All tables created")

    # Backfill invite codes for any family that doesn't have one yet
    families = Family.query.filter(
        (Family.invite_code == None) | (Family.invite_code == '')
    ).all()

    for family in families:
        # Generate unique code
        code = generate_invite_code()
        while Family.query.filter_by(invite_code=code).first():
            code = generate_invite_code()
        family.invite_code = code

    if families:
        db.session.commit()
        print(f"✓ Generated invite codes for {len(families)} existing families")

    # Print all families and their invite codes
    all_families = Family.query.all()
    if all_families:
        print("\n── Your Family Invite Codes ─────────────────")
        for f in all_families:
            count = len(f.users)
            print(f"  {f.name:30s}  →  {f.invite_code}  ({count} member{'s' if count != 1 else ''})")
        print("─────────────────────────────────────────────")
    else:
        print("\nNo families yet — register the first user to create one.")

    print("\n✅ Database ready.")
    print("   Start the server: python run.py")
