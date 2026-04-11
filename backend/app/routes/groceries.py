from flask import Blueprint, request, jsonify
from app import db
from app.models import Grocery, User
from flask_jwt_extended import jwt_required, get_jwt_identity
import json

groceries_bp = Blueprint('groceries', __name__)

def _user_name(user_id):
    u = User.query.get(user_id)
    return u.name if u else 'Unknown'

@groceries_bp.route('/', methods=['GET'])
@jwt_required()
def get_groceries():
    current_user = json.loads(get_jwt_identity())
    items = Grocery.query.filter_by(family_id=current_user['family_id']).order_by(Grocery.id.desc()).all()
    return jsonify([{
        'id': g.id,
        'name': g.name,
        'quantity': g.quantity,
        'category': g.category,
        'status': g.status,
        'added_by': g.added_by,
        'added_by_name': _user_name(g.added_by) if g.added_by else None,
    } for g in items]), 200

@groceries_bp.route('/', methods=['POST'])
@jwt_required()
def add_grocery():
    current_user = json.loads(get_jwt_identity())
    data = request.get_json()

    if not data or not data.get('name'):
        return jsonify({'message': 'Item name is required'}), 400

    quantity = data.get('quantity', 1)
    try:
        quantity = max(1, int(quantity))
    except (TypeError, ValueError):
        quantity = 1

    item = Grocery(
        family_id=current_user['family_id'],
        added_by=current_user['id'],
        name=data.get('name').strip(),
        quantity=quantity,
        category=data.get('category', 'Other')
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'message': 'Item added', 'id': item.id}), 201

@groceries_bp.route('/<int:item_id>', methods=['PATCH'])
@jwt_required()
def update_grocery(item_id):
    current_user = json.loads(get_jwt_identity())
    item = Grocery.query.filter_by(id=item_id, family_id=current_user['family_id']).first()
    if not item:
        return jsonify({'message': 'Item not found'}), 404
    data = request.get_json()
    if 'status' in data: item.status = data['status']
    if 'quantity' in data: item.quantity = max(1, int(data['quantity']))
    db.session.commit()
    return jsonify({'message': 'Item updated'}), 200

@groceries_bp.route('/<int:item_id>', methods=['DELETE'])
@jwt_required()
def delete_grocery(item_id):
    current_user = json.loads(get_jwt_identity())
    item = Grocery.query.filter_by(id=item_id, family_id=current_user['family_id']).first()
    if not item:
        return jsonify({'message': 'Item not found'}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Item deleted'}), 200
