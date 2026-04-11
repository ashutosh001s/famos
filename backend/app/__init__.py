from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import timedelta
import os

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    
    # These fallbacks are INSECURE — always set real values in .env
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'CHANGE-ME-in-dotenv')
    db_uri = os.getenv('DATABASE_URI', 'sqlite:///app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'CHANGE-ME-in-dotenv')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)
    
    CORS(app, resources={r"/api/*": {
        "origins": "*",
        "allow_headers": ["Content-Type", "Authorization"],
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "supports_credentials": False
    }})
    
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    jwt.init_app(app)
    
    from app.routes.auth import auth_bp
    from app.routes.tasks import tasks_bp
    from app.routes.groceries import groceries_bp
    from app.routes.expenses import expenses_bp
    from app.routes.passwords import passwords_bp
    from app.routes.documents import documents_bp
    from app.routes.summary import summary_bp
    from app.routes.webhook import webhook_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
    app.register_blueprint(groceries_bp, url_prefix='/api/groceries')
    app.register_blueprint(expenses_bp, url_prefix='/api/expenses')
    app.register_blueprint(passwords_bp, url_prefix='/api/passwords')
    app.register_blueprint(documents_bp, url_prefix='/api/documents')
    app.register_blueprint(summary_bp, url_prefix='/api/summary')
    app.register_blueprint(webhook_bp, url_prefix='/webhook')

    # Health check endpoint — used by Docker and monitoring
    from flask import jsonify
    @app.route('/health')
    def health():
        try:
            db.session.execute(db.text('SELECT 1'))
            return jsonify({'status': 'ok', 'db': 'connected'}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'db': str(e)}), 503

    return app
