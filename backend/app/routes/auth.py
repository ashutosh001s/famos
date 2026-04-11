from flask import request, jsonify
from app import db, bcrypt
from app.models import User, Family
from . import auth_bp
from flask_jwt_extended import create_access_token
import json

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password') or not data.get('name'):
        return jsonify({'message': 'Missing fields'}), 400
        
    if User.query.filter_by(email=data.get('email')).first():
        return jsonify({'message': 'User already exists'}), 400
        
    # Create family for new user
    family_name = data.get('family_name', f"{data.get('name')}'s Family")
    family = Family(name=family_name)
    db.session.add(family)
    db.session.commit()
    
    hashed_password = bcrypt.generate_password_hash(data.get('password')).decode('utf-8')
    user = User(
        name=data.get('name'),
        email=data.get('email'),
        password_hash=hashed_password,
        role='admin', # First user is admin
        family_id=family.id
    )
    
    db.session.add(user)
    db.session.commit()
    
    access_token = create_access_token(identity=json.dumps({'id': user.id, 'family_id': user.family_id, 'role': user.role}))
    
    return jsonify({
        'message': 'User created successfully',
        'access_token': access_token,
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'family_id': user.family_id
        }
    }), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Missing email or password'}), 400
        
    user = User.query.filter_by(email=data.get('email')).first()
    
    if user and bcrypt.check_password_hash(user.password_hash, data.get('password')):
        access_token = create_access_token(identity=json.dumps({'id': user.id, 'family_id': user.family_id, 'role': user.role}))
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'family_id': user.family_id
            }
        }), 200
        
    return jsonify({'message': 'Invalid credentials'}), 401
        'invite_code': family.invite_code,
        'family_name': family.name
    }), 200

# ── Regenerate invite code (admin only) ──────────────────────
@auth_bp.route('/family/invite-code/regenerate', methods=['POST'])
@jwt_required()
def regenerate_invite_code():
    current_user = json.loads(get_jwt_identity())
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Only the family admin can regenerate the invite code'}), 403
    from app.models import generate_invite_code
    family = Family.query.get(current_user['family_id'])
    family.invite_code = generate_invite_code()
    db.session.commit()
    return jsonify({
        'message': 'Invite code regenerated',
        'invite_code': family.invite_code
    }), 200
