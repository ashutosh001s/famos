from flask import Blueprint, request, jsonify
from app import db
from app.models import PasswordVault
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
from cryptography.fernet import Fernet
import os

passwords_bp = Blueprint('passwords', __name__)

# Initialize Fernet with Vault Key
key = os.getenv('VAULT_ENCRYPTION_KEY', 'n1B6oP8jXoXq5_aP2Vq9A9jM8R-2lEaB385pLZGgM9M=')
fernet = Fernet(key.encode())

@passwords_bp.route('/', methods=['GET'])
@jwt_required()
def get_passwords():
    current_user = json.loads(get_jwt_identity())
    vaults = PasswordVault.query.filter_by(user_id=current_user['id']).all()
    
    decrypted_vaults = []
    for v in vaults:
        try:
            pwd = fernet.decrypt(v.encrypted_password.encode()).decode()
        except Exception:
            pwd = "ERROR_DECRYPTING"
            
        decrypted_vaults.append({
            'id': v.id,
            'title': v.title,
            'username': v.username,
            'password': pwd,
            'url': v.url,
            'notes': v.notes
        })
    return jsonify(decrypted_vaults), 200

@passwords_bp.route('/', methods=['POST'])
@jwt_required()
def add_password():
    current_user = json.loads(get_jwt_identity())
    data = request.get_json()
    
    if not data.get('password') or not data.get('title'):
        return jsonify({'message': 'Title and password required'}), 400
        
    encrypted_pwd = fernet.encrypt(data['password'].encode()).decode()
    
    vault_entry = PasswordVault(
        user_id=current_user['id'],
        title=data['title'],
        username=data.get('username'),
        encrypted_password=encrypted_pwd,
        url=data.get('url'),
        notes=data.get('notes')
    )
    db.session.add(vault_entry)
    db.session.commit()
    
    return jsonify({'message': 'Password securely stored'}), 201

@passwords_bp.route('/<int:vault_id>', methods=['DELETE'])
@jwt_required()
def delete_password(vault_id):
    current_user = json.loads(get_jwt_identity())
    vault_entry = PasswordVault.query.filter_by(id=vault_id, user_id=current_user['id']).first()
    
    if not vault_entry:
        return jsonify({'message': 'Not found or unauthorized'}), 404
        
    db.session.delete(vault_entry)
    db.session.commit()
    return jsonify({'message': 'Deleted successfully'}), 200
