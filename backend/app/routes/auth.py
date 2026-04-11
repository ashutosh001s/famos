from flask import request, jsonify
from app import db, bcrypt
from app.models import User, Family
from . import auth_bp
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import json


def make_token(user):
    return create_access_token(identity=json.dumps({
        'id': user.id,
        'family_id': user.family_id,
        'role': user.role,
        'name': user.name
    }))


# ── Get current user info ────────────────────────────────────
@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_me():
    current_user = json.loads(get_jwt_identity())
    user = User.query.get(current_user['id'])
    if not user:
        return jsonify({'message': 'User not found'}), 404
    family = Family.query.get(user.family_id)
    return jsonify({
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'role': user.role,
        'family_id': user.family_id,
        'family_name': family.name if family else None,
        'invite_code': family.invite_code if (family and user.role == 'admin') else None
    }), 200


# ── Register — creates a new family, user becomes admin ──────
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password') or not data.get('name'):
        return jsonify({'message': 'Name, email, and password are required'}), 400

    if User.query.filter_by(email=data['email'].lower().strip()).first():
        return jsonify({'message': 'An account with this email already exists'}), 400

    family_name = data.get('family_name', f"{data['name'].strip()}'s Family")
    family = Family(name=family_name)
    db.session.add(family)
    db.session.flush()  # gets family.id without committing

    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    user = User(
        name=data['name'].strip(),
        email=data['email'].lower().strip(),
        password_hash=hashed_pw,
        role='admin',
        family_id=family.id
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        'message': 'Family created! Share the invite code with members.',
        'access_token': make_token(user),
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'family_id': family.id,
            'family_name': family.name,
            'invite_code': family.invite_code
        }
    }), 201


# ── Join Family — member registers using invite code ─────────
@auth_bp.route('/join', methods=['POST'])
def join_family():
    data = request.get_json()
    required = ['name', 'email', 'password', 'invite_code']
    if not data or not all(data.get(f) for f in required):
        return jsonify({'message': 'Name, email, password, and invite_code are required'}), 400

    if User.query.filter_by(email=data['email'].lower().strip()).first():
        return jsonify({'message': 'An account with this email already exists'}), 400

    family = Family.query.filter_by(invite_code=data['invite_code'].strip().upper()).first()
    if not family:
        return jsonify({'message': 'Invalid invite code. Ask your family admin for the correct code.'}), 404

    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    user = User(
        name=data['name'].strip(),
        email=data['email'].lower().strip(),
        password_hash=hashed_pw,
        role='member',
        family_id=family.id
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        'message': f"Joined {family.name} successfully!",
        'access_token': make_token(user),
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'family_id': family.id,
            'family_name': family.name,
        }
    }), 201


# ── Login ─────────────────────────────────────────────────────
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Email and password are required'}), 400

    user = User.query.filter_by(email=data['email'].lower().strip()).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, data['password']):
        return jsonify({'message': 'Invalid email or password'}), 401

    family = Family.query.get(user.family_id)
    return jsonify({
        'message': 'Login successful',
        'access_token': make_token(user),
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'family_id': user.family_id,
            'family_name': family.name if family else None,
            'invite_code': family.invite_code if (family and user.role == 'admin') else None
        }
    }), 200


# ── Get family members ────────────────────────────────────────
@auth_bp.route('/family/members', methods=['GET'])
@jwt_required()
def get_family_members():
    current_user = json.loads(get_jwt_identity())
    members = User.query.filter_by(family_id=current_user['family_id']).all()
    return jsonify([{
        'id': m.id,
        'name': m.name,
        'email': m.email,
        'role': m.role
    } for m in members]), 200


# ── Get invite code (admin only) ──────────────────────────────
@auth_bp.route('/family/invite-code', methods=['GET'])
@jwt_required()
def get_invite_code():
    current_user = json.loads(get_jwt_identity())
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Only the family admin can view the invite code'}), 403
    family = Family.query.get(current_user['family_id'])
    return jsonify({
        'invite_code': family.invite_code,
        'family_name': family.name
    }), 200


# ── Regenerate invite code (admin only) ───────────────────────
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
