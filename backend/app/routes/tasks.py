from flask import Blueprint, request, jsonify
from app import db
from app.models import Task, User
from app.routes.auth import get_current_user
from flask_jwt_extended import jwt_required
from datetime import datetime
from app.routes.chat import auto_alert

tasks_bp = Blueprint('tasks', __name__)


def _build_user_map(tasks):
    """Fetch all referenced user names in a single DB query (avoids N+1)."""
    user_ids = set()
    for t in tasks:
        if t.created_by:
            user_ids.add(t.created_by)
        if t.assigned_to:
            user_ids.add(t.assigned_to)
    if not user_ids:
        return {}
    return {u.id: u.name for u in User.query.filter(User.id.in_(user_ids)).all()}


@tasks_bp.route('/', methods=['GET'])
@jwt_required()
def get_tasks():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify([]), 200

    tasks = Task.query.filter_by(family_id=user.family_id).order_by(Task.id.desc()).all()
    user_map = _build_user_map(tasks)

    return jsonify([{
        'id': t.id,
        'title': t.title,
        'description': t.description,
        'priority': t.priority,
        'status': t.status,
        'due_date': t.due_date.isoformat() if t.due_date else None,
        'requires_transaction': bool(t.requires_transaction),
        'assigned_to': t.assigned_to,
        'assigned_to_name': user_map.get(t.assigned_to),
        'created_by': t.created_by,
        'created_by_name': user_map.get(t.created_by),
        'created_at': t.created_at.isoformat() if t.created_at else None
    } for t in tasks]), 200


@tasks_bp.route('/', methods=['POST'])
@jwt_required()
def add_task():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify({'message': 'You must be in a family to add tasks'}), 403

    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'message': 'Title is required'}), 400

    due_date = None
    if data.get('due_date'):
        try:
            due_date = datetime.fromisoformat(data['due_date'])
        except (ValueError, TypeError):
            pass

    # Validate assigned_to belongs to same family
    assigned_to = data.get('assigned_to')
    if assigned_to:
        assignee = User.query.filter_by(id=assigned_to, family_id=user.family_id).first()
        if not assignee:
            return jsonify({'message': 'Assignee not found in your family'}), 400

    task = Task(
        family_id=user.family_id,
        created_by=user.id,
        assigned_to=assigned_to,
        title=data.get('title').strip(),
        description=data.get('description', '').strip(),
        priority=data.get('priority', 'medium'),
        requires_transaction=bool(data.get('requires_transaction', False)),
        due_date=due_date
    )
    db.session.add(task)
    db.session.commit()
    return jsonify({'message': 'Task created!', 'id': task.id}), 201


@tasks_bp.route('/<int:task_id>', methods=['PUT', 'PATCH'])
@jwt_required()
def update_task(task_id):
    user = get_current_user()
    task = Task.query.filter_by(id=task_id, family_id=user.family_id).first()
    if not task:
        return jsonify({'message': 'Task not found'}), 404

    data = request.get_json() or {}  # Fixed: guard against None body

    if 'status' in data:
        old_status = task.status
        task.status = data['status']
        if old_status != 'completed' and task.status == 'completed':
            auto_alert(user.family_id, user.name, f"completed the task: {task.title}")
    if 'priority' in data:
        task.priority = data['priority']
    if 'title' in data:
        task.title = data['title']
    if 'assigned_to' in data:
        # Validate assignee is in the same family
        assigned_to = data['assigned_to']
        if assigned_to is not None:
            assignee = User.query.filter_by(id=assigned_to, family_id=user.family_id).first()
            if not assignee:
                return jsonify({'message': 'Assignee not found in your family'}), 400
        task.assigned_to = assigned_to

    db.session.commit()
    return jsonify({'message': 'Task updated'}), 200


@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@jwt_required()
def delete_task(task_id):
    user = get_current_user()
    task = Task.query.filter_by(id=task_id, family_id=user.family_id).first()
    if not task:
        return jsonify({'message': 'Task not found'}), 404
    db.session.delete(task)
    db.session.commit()
    return jsonify({'message': 'Task deleted'}), 200
