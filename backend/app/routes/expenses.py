from flask import Blueprint, request, jsonify
from app import db
from app.models import Transaction
from app.routes.auth import get_current_user
from flask_jwt_extended import jwt_required
from fpdf import FPDF
from flask import send_file
import io
from datetime import datetime

expenses_bp = Blueprint('expenses', __name__)


@expenses_bp.route('/', methods=['GET'])
@jwt_required()
def get_expenses():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify([]), 200

    expenses = Transaction.query.filter_by(
        family_id=user.family_id
    ).order_by(Transaction.id.desc()).all()

    return jsonify([{
        'id': e.id,
        'type': e.type,
        'amount': e.amount,
        'category': e.category,
        'description': e.description,
        'payment_method': e.payment_method,
        'paid_by': e.paid_by,
        'for_user_id': e.for_user_id,
        'receipt_doc_id': e.receipt_doc_id,
        'location': e.location,
        'tags': e.tags,
        'is_recurring': bool(e.is_recurring),
        'date': e.date.isoformat() if e.date else None
    } for e in expenses]), 200


@expenses_bp.route('/', methods=['POST'])
@jwt_required()
def add_expense():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify({'message': 'You must be in a family to log transactions'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'message': 'No data provided'}), 400

    amount = data.get('amount')
    if amount is None or not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({'message': 'A valid positive amount is required'}), 400

    tx_type = data.get('type', 'expense')
    category = data.get('category', 'Deposit') if tx_type == 'income' else data.get('category')

    if tx_type == 'expense' and not category:
        return jsonify({'message': 'Category is required for expenses'}), 400

    exp = Transaction(
        family_id=user.family_id,
        paid_by=user.id,
        for_user_id=data.get('for_user_id'),
        receipt_doc_id=data.get('receipt_doc_id'),
        location=data.get('location', '').strip() or None,
        tags=data.get('tags', '').strip() or None,
        is_recurring=bool(data.get('is_recurring', False)),
        type=tx_type,
        amount=float(amount),
        category=category,
        description=data.get('description', '').strip() or None,
        payment_method=data.get('payment_method')
    )
    db.session.add(exp)
    db.session.commit()
    return jsonify({'message': 'Transaction logged', 'id': exp.id}), 201


@expenses_bp.route('/<int:tx_id>', methods=['DELETE'])
@jwt_required()
def delete_expense(tx_id):
    """Delete a transaction. Any family member can delete any family transaction."""
    user = get_current_user()
    tx = Transaction.query.filter_by(id=tx_id, family_id=user.family_id).first()
    if not tx:
        return jsonify({'message': 'Transaction not found'}), 404
    db.session.delete(tx)
    db.session.commit()
    return jsonify({'message': 'Transaction deleted'}), 200


@expenses_bp.route('/summary', methods=['GET'])
@jwt_required()
def get_summary():
    user = get_current_user()
    transactions = Transaction.query.filter_by(family_id=user.family_id).all()

    balance = 0
    family_spent = 0
    individual_spent = 0
    breakdown = {}

    from app.models import User
    members = User.query.filter_by(family_id=user.family_id).all()
    user_map = {m.id: m.name for m in members}

    member_breakdown = {m.name: 0 for m in members}

    for t in transactions:
        if t.type == 'income':
            balance += t.amount
        else:
            balance -= t.amount
            family_spent += t.amount
            if t.paid_by == user.id:
                individual_spent += t.amount
            breakdown[t.category] = breakdown.get(t.category, 0) + t.amount
            
            p_name = user_map.get(t.paid_by, "Unknown")
            member_breakdown[p_name] = member_breakdown.get(p_name, 0) + t.amount

    return jsonify({
        'balance': round(balance, 2),
        'family_spent': round(family_spent, 2),
        'individual_spent': round(individual_spent, 2),
        'breakdown': {k: round(v, 2) for k, v in breakdown.items()},
        'member_breakdown': {k: round(v, 2) for k, v in member_breakdown.items()}
    }), 200


@expenses_bp.route('/statement/pdf', methods=['GET'])
@jwt_required()
def generate_statement():
    user = get_current_user()
    
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')

    query = Transaction.query.filter_by(family_id=user.family_id)
    if start_str:
        try: query = query.filter(Transaction.date >= datetime.strptime(start_str, '%Y-%m-%d'))
        except ValueError: pass
    if end_str:
        try:
            end_parsed = datetime.strptime(end_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(Transaction.date <= end_parsed)
        except ValueError: pass

    transactions = query.order_by(Transaction.date.asc()).all()

    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("helvetica", "B", 20)
    pdf.set_fill_color(25, 118, 210)
    pdf.set_text_color(255, 255, 255)
    
    title = "Family Financial Statement"
    if start_str and end_str: title = f"Statement ({start_str} to {end_str})"
    elif start_str: title = f"Statement (From {start_str})"

    pdf.cell(0, 15, title, ln=1, align="C", fill=True)
    pdf.ln(5)

    # Summary
    balance = sum(t.amount if t.type == 'income' else -t.amount for t in transactions)
    family_spent = sum(t.amount for t in transactions if t.type == 'expense')

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 11)
    pdf.cell(0, 8, f"Total Balance: Rs. {round(balance, 2)}", ln=1)
    pdf.cell(0, 8, f"Total Family Spending: Rs. {round(family_spent, 2)}", ln=1)
    pdf.cell(0, 8, f"Total Transactions: {len(transactions)}", ln=1)
    pdf.ln(5)

    # Table header
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(220, 230, 241)
    pdf.cell(35, 10, "Date", border=1, fill=True)
    pdf.cell(45, 10, "Category", border=1, fill=True)
    pdf.cell(35, 10, "Method", border=1, fill=True)
    pdf.cell(35, 10, "Amount", border=1, fill=True)
    pdf.cell(30, 10, "Type", border=1, ln=1, fill=True)

    def _s(text):
        if text is None: return ''
        return str(text).encode('latin-1', 'replace').decode('latin-1')

    pdf.set_font("helvetica", "", 9)
    for t in transactions:
        row_color = (240, 255, 240) if t.type == 'income' else (255, 245, 245)
        pdf.set_fill_color(*row_color)
        pdf.cell(35, 8, t.date.strftime("%Y-%m-%d"), border=1, fill=True)
        pdf.cell(45, 8, _s(t.category)[:20], border=1, fill=True)
        pdf.cell(35, 8, _s(t.payment_method or 'N/A')[:12], border=1, fill=True)
        prefix = "+" if t.type == 'income' else "-"
        pdf.cell(35, 8, f"{prefix} Rs.{t.amount}", border=1, fill=True)
        pdf.cell(30, 8, t.type.capitalize(), border=1, ln=1, fill=True)

    pdf.ln(10)
    pdf.set_font("helvetica", "B", 13)
    color = (0, 128, 0) if balance >= 0 else (200, 0, 0)
    pdf.set_text_color(*color)
    pdf.cell(0, 10, f"Closing Balance: Rs. {round(balance, 2)}")

    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(path)
    
    return send_file(
        path,
        as_attachment=True,
        download_name='Family_Statement.pdf',
        mimetype='application/pdf'
    )
