from flask import Blueprint, jsonify
from app import db
from app.models import Task, Grocery, Transaction, User
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
from datetime import datetime, timedelta

summary_bp = Blueprint('summary', __name__)

@summary_bp.route('/', methods=['GET'])
@jwt_required()
def get_dashboard_summary():
    current_user = json.loads(get_jwt_identity())
    family_id = current_user['family_id']
    user_id = current_user['id']

    # Tasks summary
    all_tasks = Task.query.filter_by(family_id=family_id).all()
    pending_tasks = [t for t in all_tasks if t.status == 'pending']
    completed_tasks = [t for t in all_tasks if t.status == 'completed']

    # Grocery summary
    all_groceries = Grocery.query.filter_by(family_id=family_id).all()
    pending_groceries = [g for g in all_groceries if g.status == 'pending']

    # Finance summary
    all_tx = Transaction.query.filter_by(family_id=family_id).order_by(Transaction.date.desc()).all()
    balance = 0
    month_spent = 0
    this_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)

    for t in all_tx:
        if t.type == 'income':
            balance += t.amount
        else:
            balance -= t.amount
            if t.date and t.date >= this_month:
                month_spent += t.amount

    # Recent 3 transactions
    recent_tx = [{
        'id': t.id,
        'type': t.type,
        'amount': t.amount,
        'category': t.category,
        'date': t.date.isoformat() if t.date else None
    } for t in all_tx[:3]]

    # Upcoming: tasks due in next 3 days
    soon = datetime.utcnow() + timedelta(days=3)
    due_soon = [{
        'id': t.id,
        'title': t.title,
        'priority': t.priority,
        'due_date': t.due_date.isoformat() if t.due_date else None
    } for t in pending_tasks if t.due_date and t.due_date <= soon]

    # Overdue tasks
    now = datetime.utcnow()
    overdue = [{
        'id': t.id,
        'title': t.title,
        'priority': t.priority
    } for t in pending_tasks if t.due_date and t.due_date < now]

    return jsonify({
        'tasks': {
            'total': len(all_tasks),
            'pending': len(pending_tasks),
            'completed': len(completed_tasks),
            'due_soon': due_soon,
            'overdue': overdue,
        },
        'groceries': {
            'total': len(all_groceries),
            'pending': len(pending_groceries),
            'bought': len(all_groceries) - len(pending_groceries),
        },
        'finances': {
            'balance': round(balance, 2),
            'month_spent': round(month_spent, 2),
            'recent_transactions': recent_tx,
        }
    }), 200
