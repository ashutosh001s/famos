from flask import Blueprint, request, jsonify
from app import db
from app.models import Task
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
from datetime import datetime

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('/', methods=['GET'])
@jwt_required()
def get_tasks():
    current_user = json.loads(get_jwt_identity())
    tasks = Task.query.filter_by(family_id=current_user['family_id']).order_by(Task.id.desc()).all()
    return jsonify([{
        'id': t.id,
        'title': t.title,
        'description': t.description,
        'priority': t.priority,
        'status': t.status,
        'due_date': t.due_date.isoformat() if t.due_date else None,
        'assigned_to': t.assigned_to,
        'created_at': t.created_at.isoformat() if t.created_at else None
    } for t in tasks]), 200

@tasks_bp.route('/', methods=['POST'])
@jwt_required()
def add_task():
    current_user = json.loads(get_jwt_identity())
    data = request.get_json()

    if not data or not data.get('title'):
        return jsonify({'message': 'Title is required'}), 400

    due_date = None
    if data.get('due_date'):
        try:
            due_date = datetime.fromisoformat(data['due_date'])
        except (ValueError, TypeError):
            pass

    task = Task(
        family_id=current_user['family_id'],
        assigned_to=data.get('assigned_to'),
        title=data.get('title').strip(),
        description=data.get('description', '').strip(),
        priority=data.get('priority', 'medium'),
        due_date=due_date
    )

    db.session.add(task)
    db.session.commit()
    return jsonify({'message': 'Task created!', 'id': task.id}), 201

@tasks_bp.route('/<int:task_id>', methods=['PUT', 'PATCH'])
@jwt_required()
def update_task(task_id):
    current_user = json.loads(get_jwt_identity())
    task = Task.query.filter_by(id=task_id, family_id=current_user['family_id']).first()

    if not task:
        return jsonify({'message': 'Task not found'}), 404

    data = request.get_json()
    if 'status' in data:
        task.status = data['status']
    if 'priority' in data:
        task.priority = data['priority']
    if 'title' in data:
        task.title = data['title']

    db.session.commit()
    return jsonify({'message': 'Task updated'}), 200

@tasks_bp.route('/<int:task_id>', methods=['DELETE'])
@jwt_required()
def delete_task(task_id):
    current_user = json.loads(get_jwt_identity())
    task = Task.query.filter_by(id=task_id, family_id=current_user['family_id']).first()

    if not task:
        return jsonify({'message': 'Task not found'}), 404

    db.session.delete(task)
    db.session.commit()
    return jsonify({'message': 'Task deleted'}), 200
