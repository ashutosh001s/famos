from flask import Blueprint, request, jsonify
from app import db, limiter
from app.models import User, Family
from . import auth_bp
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import logging
from datetime import datetime, timedelta
import secrets

logger = logging.getLogger('famos.auth')

def make_token(user):
    return create_access_token(identity=str(user.id))

def get_current_user():
    try:
        user_id = int(get_jwt_identity())
        return User.query.get(user_id)
    except:
        return None

# ── Get current user info ────────────────────────────────────
@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_me():
    user = get_current_user()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    family = Family.query.get(user.family_id)
    return jsonify({
        'id': user.id,
        'name': user.name,
        'phone_hash': user.phone_hash,
        'role': user.role,
        'family_id': user.family_id,
        'family_name': family.name if family else None
    }), 200

# ── Request OTP ──────────────────────────────────────────────
@auth_bp.route('/request-otp', methods=['POST'])
@limiter.limit("5/minute")
def request_otp():
    data = request.get_json()
    if not data or not data.get('phone_hash'):
        return jsonify({'message': 'Identifier required'}), 400

    phone_hash = data['phone_hash'].strip().lower()
    user = User.query.filter_by(phone_hash=phone_hash).first()

    if not user:
        # Generic message to prevent enumeration
        return jsonify({'message': 'If the identifier exists, an OTP has been generated.'}), 200

    # Clean old OTPs for this user
    db.session.execute(db.text("DELETE FROM otp_codes WHERE user_id = :user_id"), {'user_id': user.id})
    
    # Generate 6-digit strict numerical code
    code = f"{secrets.randbelow(1000000):06d}"
    expires = datetime.utcnow() + timedelta(minutes=5)

    db.session.execute(db.text('''
        INSERT INTO otp_codes (user_id, code, expires_at)
        VALUES (:user_id, :code, :expires)
    '''), {'user_id': user.id, 'code': code, 'expires': expires})
    db.session.commit()

    # CORE MECHANIC: Print OTP to server console explicitly
    print(f"\n" + "="*40 + f"\n[SECURE OTP] {user.name}'s Auth Code: {code}\n" + "="*40, flush=True)

    return jsonify({'message': 'If the identifier exists, an OTP has been generated.'}), 200

# ── Verify OTP ───────────────────────────────────────────────
@auth_bp.route('/verify-otp', methods=['POST'])
@limiter.limit("15/minute")
def verify_otp():
    data = request.get_json()
    if not data or not data.get('phone_hash') or not data.get('otp'):
        return jsonify({'message': 'Identifier and OTP required'}), 400

    phone_hash = data['phone_hash'].strip().lower()
    otp = data['otp'].strip()

    user = User.query.filter_by(phone_hash=phone_hash).first()
    if not user:
        return jsonify({'message': 'Invalid identifier or OTP'}), 401

    # Fetch valid OTP
    now = datetime.utcnow()
    otp_record = db.session.execute(db.text('''
        SELECT id, code FROM otp_codes 
        WHERE user_id = :user_id AND expires_at > :now
        ORDER BY id DESC LIMIT 1
    '''), {'user_id': user.id, 'now': now}).fetchone()

    if not otp_record or otp_record.code != otp:
        print(f"[AUTH WARN] Failed OTP attempt for {user.name}", flush=True)
        return jsonify({'message': 'Invalid identifier or OTP'}), 401

    # Successfully verified — delete all OTPs for user and issue JWT
    db.session.execute(db.text("DELETE FROM otp_codes WHERE user_id = :user_id"), {'user_id': user.id})
    db.session.commit()

    print(f"[AUTH SUCCESS] User {user.name} successfully authenticated via OTP.", flush=True)

    family = Family.query.get(user.family_id)
    return jsonify({
        'message': 'Login successful',
        'access_token': make_token(user),
        'user': {
            'id': user.id,
            'name': user.name,
            'role': user.role,
            'family_id': user.family_id,
            'family_name': family.name if family else None
        }
    }), 200

# ── Get family members ────────────────────────────────────────
@auth_bp.route('/family/members', methods=['GET'])
@jwt_required()
def get_family_members():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify([]), 200
    members = User.query.filter_by(family_id=user.family_id).all()
    # Read-only API map
    return jsonify([{
        'id': m.id,
        'name': m.name,
        'role': m.role
    } for m in members]), 200
