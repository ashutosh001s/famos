from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from datetime import timedelta
import os
import logging
import json

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["500/day"])

def create_app():
    # Setup structured logging targeting terminal
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    logger = logging.getLogger('famos')

    app = Flask(__name__)

    # These fallbacks are INSECURE — always set real values in .env
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'CHANGE-ME-in-dotenv')
    db_uri = os.getenv('DATABASE_URI', 'sqlite:///app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'CHANGE-ME-in-dotenv')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)  # Reverted back to 30 days for personal UX
    
    if db_uri.startswith('sqlite'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {
                'check_same_thread': False,
                'timeout': 15,
            }
        }

    # Lock CORS to known frontend origins
    allowed_origins = os.getenv(
        'ALLOWED_ORIGINS',
        'https://famos.reqnode.com'
    ).split(',')

    CORS(app, resources={r"/api/*": {
        "origins": allowed_origins,
        "allow_headers": ["Content-Type", "Authorization"],
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "supports_credentials": False
    }})

    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)

    with app.app_context():
        if db_uri.startswith('sqlite'):
            # Force WAL mode for aggressive concurrent read/writes mapping back to native hardware
            from sqlalchemy import text
            with db.engine.connect() as conn:
                conn.execute(text('PRAGMA journal_mode=WAL;'))
                conn.execute(text('PRAGMA synchronous=NORMAL;'))
        
        # Setup OTP temp table dynamically so we don't need manual alembic migrations for just this memory state.
        try:
            db.session.execute(db.text('''
                CREATE TABLE IF NOT EXISTS otp_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    code VARCHAR(6) NOT NULL,
                    expires_at DATETIME NOT NULL
                )
            '''))
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed configuring OTP memory table: {e}")

        # Synchronize users.json
        from app.models import User, Family
        
        # Self-healing: assure schema updates exist since we deleted deploy bash migrations 
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN phone_hash VARCHAR(50)"))
            db.session.commit()
        except Exception: pass
        
        try:
            db.session.execute(db.text("ALTER TABLE transactions ADD COLUMN description VARCHAR(300)"))
            db.session.commit()
        except Exception: pass

        try:
            # Add created_at just in case it's missing from previous versions
            db.session.execute(db.text("ALTER TABLE transactions ADD COLUMN created_at DATETIME"))
            db.session.commit()
        except Exception: pass

        try:
            db.session.execute(db.text("ALTER TABLE documents ADD COLUMN stored_filename VARCHAR(300)"))
            db.session.commit()
        except Exception: pass

        try:
            db.session.execute(db.text("ALTER TABLE documents ADD COLUMN category VARCHAR(50) DEFAULT 'Other'"))
            db.session.commit()
        except Exception: pass

        try:
            db.session.execute(db.text("ALTER TABLE tasks ADD COLUMN requires_transaction BOOLEAN DEFAULT 0"))
            db.session.commit()
        except Exception: pass

        try:
            db.session.execute(db.text("ALTER TABLE documents ADD COLUMN visibility VARCHAR(20) DEFAULT 'individual'"))
            db.session.commit()
        except Exception: pass

        try:
            db.session.execute(db.text("ALTER TABLE groceries ADD COLUMN unit VARCHAR(20) DEFAULT ''"))
            db.session.commit()
        except Exception: pass

        # New Transactions Enhancements Core
        try:
            db.session.execute(db.text("ALTER TABLE transactions ADD COLUMN for_user_id INTEGER"))
            db.session.execute(db.text("ALTER TABLE transactions ADD COLUMN receipt_doc_id INTEGER"))
            db.session.execute(db.text("ALTER TABLE transactions ADD COLUMN location VARCHAR(150)"))
            db.session.execute(db.text("ALTER TABLE transactions ADD COLUMN tags VARCHAR(200)"))
            db.session.execute(db.text("ALTER TABLE transactions ADD COLUMN is_recurring BOOLEAN DEFAULT 0"))
            db.session.commit()
        except Exception: pass

        # Fam-Drive Schema Upgrades
        try:
            db.session.execute(db.text("ALTER TABLE documents ADD COLUMN size_bytes INTEGER DEFAULT 0"))
            db.session.execute(db.text("ALTER TABLE documents ADD COLUMN mime_type VARCHAR(100) DEFAULT 'application/octet-stream'"))
            db.session.execute(db.text("ALTER TABLE documents ADD COLUMN tags VARCHAR(200)"))
            db.session.commit()
        except Exception: pass

        # Chat & Push Tracking Schema Upgrades
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN expo_push_token VARCHAR(255)"))
            db.session.commit()
        except Exception: pass

        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN last_seen DATETIME"))
            db.session.commit()
        except Exception: pass

        try:
            db.session.execute(db.text('''
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL REFERENCES families(id),
                    sender_id INTEGER REFERENCES users(id),
                    message_type VARCHAR(20) DEFAULT 'text',
                    content TEXT,
                    document_id INTEGER REFERENCES documents(id),
                    created_at DATETIME
                )
            '''))
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed configuring chat tables: {e}")

        users_file = os.path.join(app.root_path, '..', 'users.json')
        if os.path.exists(users_file):
            logger.info("Synchronizing static users.json definitions to DB...")
            try:
                with open(users_file, 'r') as f:
                    data = json.load(f)
                
                # Setup Family
                family_name = data.get('family_name', 'Personal Core')
                family = Family.query.first()
                if not family:
                    family = Family(name=family_name)
                    db.session.add(family)
                    db.session.commit()
                else:
                    family.name = family_name
                    db.session.commit()

                # Upsert Users
                for u_data in data.get('users', []):
                    user = User.query.filter_by(id=u_data['id']).first()
                    if not user:
                        # SQLite NOT NULL legacy constraint bypass
                        user = User(
                            id=u_data['id'], 
                            phone_hash=u_data['phone_hash'], 
                            name=u_data['name'], 
                            role=u_data.get('role', 'member'), 
                            family_id=family.id,
                            email=f"dummy_{u_data['id']}@localhost.local",
                            password_hash="removed"
                        )
                        db.session.add(user)
                    else:
                        user.phone_hash = u_data.get('phone_hash', user.phone_hash)
                        user.name = u_data.get('name', user.name)
                        user.role = u_data.get('role', user.role)
                        user.family_id = family.id
                db.session.commit()
            except Exception as e:
                logger.error(f"Failed to sync users.json: {e}")
        else:
            logger.warning("No users.json found in root. Cannot synchronize identities.")

    from app.routes.auth import auth_bp
    from app.routes.tasks import tasks_bp
    from app.routes.groceries import groceries_bp
    from app.routes.expenses import expenses_bp
    from app.routes.passwords import passwords_bp
    from app.routes.documents import documents_bp
    from app.routes.summary import summary_bp
    from app.routes.webhook import webhook_bp
    from app.routes.chat import chat_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
    app.register_blueprint(groceries_bp, url_prefix='/api/groceries')
    app.register_blueprint(expenses_bp, url_prefix='/api/expenses')
    app.register_blueprint(passwords_bp, url_prefix='/api/passwords')
    app.register_blueprint(documents_bp, url_prefix='/api/documents')
    app.register_blueprint(summary_bp, url_prefix='/api/summary')
    app.register_blueprint(webhook_bp, url_prefix='/webhook')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')

    @app.route('/health')
    def health():
        try:
            # Touch the DB to ensure viability without rendering private records
            db.session.execute(db.text('SELECT 1'))
            return jsonify({'status': 'ok', 'db': 'connected', 'info': 'System operational and secured.'}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'db': str(e)}), 503

    return app
