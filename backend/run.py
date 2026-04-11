from app import create_app, db
from app.services.scheduler import start_scheduler
import sqlalchemy
import os

app = create_app()

with app.app_context():
    db.create_all()
    # Enable SQLite WAL mode for better concurrent read/write
    db_uri = os.getenv('DATABASE_URI', 'sqlite:///app.db')
    if db_uri.startswith('sqlite'):
        with db.engine.connect() as conn:
            conn.execute(sqlalchemy.text('PRAGMA journal_mode=WAL'))
            conn.execute(sqlalchemy.text('PRAGMA synchronous=NORMAL'))
            conn.execute(sqlalchemy.text('PRAGMA foreign_keys=ON'))
            conn.commit()

start_scheduler(app)

if __name__ == '__main__':
    # Dev only — production uses gunicorn
    app.run(debug=False, host='0.0.0.0', port=5000)
