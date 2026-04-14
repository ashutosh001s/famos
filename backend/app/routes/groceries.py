from flask import Blueprint, request, jsonify
from app import db
from app.models import Grocery, User
from app.routes.auth import get_current_user
from flask_jwt_extended import jwt_required
from app.routes.chat import auto_alert

groceries_bp = Blueprint('groceries', __name__)


def _build_user_map(items):
    """Fetch all referenced user names in a single DB query (avoids N+1)."""
    user_ids = {i.added_by for i in items if i.added_by}
    if not user_ids:
        return {}
    return {u.id: u.name for u in User.query.filter(User.id.in_(user_ids)).all()}


@groceries_bp.route('/', methods=['GET'])
@jwt_required()
def get_groceries():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify([]), 200

    items = Grocery.query.filter_by(family_id=user.family_id).order_by(Grocery.id.desc()).all()
    user_map = _build_user_map(items)

    return jsonify([{
        'id': g.id,
        'name': g.name,
        'quantity': g.quantity,
        'unit': g.unit,
        'category': g.category,
        'status': g.status,
        'added_by': g.added_by,
        'added_by_name': user_map.get(g.added_by),
    } for g in items]), 200


@groceries_bp.route('/', methods=['POST'])
@jwt_required()
def add_grocery():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify({'message': 'You must be in a family to add groceries'}), 403

    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'message': 'Item name is required'}), 400

    quantity = data.get('quantity', 1)
    try:
        quantity = max(1, int(quantity))
    except (TypeError, ValueError):
        quantity = 1

    item = Grocery(
        family_id=user.family_id,
        added_by=user.id,
        name=data.get('name').strip(),
        quantity=quantity,
        unit=str(data.get('unit', '')).strip()[:20],
        category=data.get('category', 'Other')
    )
    db.session.add(item)
    db.session.commit()
    auto_alert(user.family_id, user.name, f"added grocery item: {item.name}")
    return jsonify({'message': 'Item added', 'id': item.id}), 201


@groceries_bp.route('/<int:item_id>', methods=['PATCH'])
@jwt_required()
def update_grocery(item_id):
    user = get_current_user()
    item = Grocery.query.filter_by(id=item_id, family_id=user.family_id).first()
    if not item:
        return jsonify({'message': 'Item not found'}), 404

    data = request.get_json() or {}  # Fixed: guard against None body

    if 'status' in data:
        old_status = item.status
        item.status = data['status']
        if old_status != 'bought' and item.status == 'bought':
             auto_alert(user.family_id, user.name, f"bought: {item.name}")
    if 'quantity' in data:
        try:
            item.quantity = max(1, int(data['quantity']))
        except (TypeError, ValueError):
            pass

    db.session.commit()
    return jsonify({'message': 'Item updated'}), 200


@groceries_bp.route('/<int:item_id>', methods=['DELETE'])
@jwt_required()
def delete_grocery(item_id):
    user = get_current_user()
    item = Grocery.query.filter_by(id=item_id, family_id=user.family_id).first()
    if not item:
        return jsonify({'message': 'Item not found'}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Item deleted'}), 200
