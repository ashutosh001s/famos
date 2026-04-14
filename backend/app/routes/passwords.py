from flask import Blueprint, request, jsonify
from app import db
from app.models import PasswordVault
from app.routes.auth import get_current_user
from flask_jwt_extended import jwt_required
from cryptography.fernet import Fernet
from app.routes.chat import auto_alert
import os

passwords_bp = Blueprint('passwords', __name__)

# Key MUST be in .env — app will refuse to start without it
_vault_key = os.getenv('VAULT_ENCRYPTION_KEY')
if not _vault_key:
    raise RuntimeError('VAULT_ENCRYPTION_KEY is not set. Add it to your .env file.')
fernet = Fernet(_vault_key.encode())


@passwords_bp.route('/', methods=['GET'])
@jwt_required()
def get_passwords():
    """Return vault entries WITHOUT decrypting passwords.
    Passwords are returned as Fernet ciphertext — decryption happens client-side on reveal.
    This prevents bulk plaintext exposure over the network."""
    user = get_current_user()
    vaults = PasswordVault.query.filter_by(user_id=user.id).all()

    return jsonify([{
        'id': v.id,
        'title': v.title,
        'username': v.username,
        'encrypted_password': v.encrypted_password,  # ciphertext only — NOT decrypted
        'url': v.url,
        'notes': v.notes
    } for v in vaults]), 200


@passwords_bp.route('/reveal/<int:vault_id>', methods=['GET'])
@jwt_required()
def reveal_password(vault_id):
    """Decrypt and return a single password on-demand for the owner only."""
    user = get_current_user()
    vault_entry = PasswordVault.query.filter_by(id=vault_id, user_id=user.id).first()

    if not vault_entry:
        return jsonify({'message': 'Not found or unauthorized'}), 404

    try:
        pwd = fernet.decrypt(vault_entry.encrypted_password.encode()).decode()
    except Exception:
        return jsonify({'message': 'Failed to decrypt — vault key may have changed'}), 500

    return jsonify({'password': pwd}), 200


@passwords_bp.route('/', methods=['POST'])
@jwt_required()
def add_password():
    user = get_current_user()
    data = request.get_json()

    if not data or not data.get('password') or not data.get('title'):  # Fixed: guard None
        return jsonify({'message': 'Title and password required'}), 400

    encrypted_pwd = fernet.encrypt(data['password'].encode()).decode()

    vault_entry = PasswordVault(
        user_id=user.id,
        title=data['title'],
        username=data.get('username'),
        encrypted_password=encrypted_pwd,
        url=data.get('url'),
        notes=data.get('notes')
    )
    db.session.add(vault_entry)
    db.session.commit()
    
    auto_alert(user.family_id, user.name, f"secured a vault entry: {data['title']}")

    return jsonify({'message': 'Password securely stored', 'id': vault_entry.id}), 201


@passwords_bp.route('/<int:vault_id>', methods=['DELETE'])
@jwt_required()
def delete_password(vault_id):
    user = get_current_user()
    vault_entry = PasswordVault.query.filter_by(id=vault_id, user_id=user.id).first()

    if not vault_entry:
        return jsonify({'message': 'Not found or unauthorized'}), 404

    db.session.delete(vault_entry)
    db.session.commit()
    return jsonify({'message': 'Deleted successfully'}), 200
