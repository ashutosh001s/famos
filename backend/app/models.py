from app import db
from datetime import datetime
import secrets, string


class Family(db.Model):
    __tablename__ = 'families'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    users = db.relationship('User', backref='family', lazy=True)
    tasks = db.relationship('Task', backref='family', lazy=True)
    groceries = db.relationship('Grocery', backref='family', lazy=True)
    transactions = db.relationship('Transaction', backref='family', lazy=True)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('families.id'), nullable=True)
    phone_hash = db.Column(db.String(50), unique=True, nullable=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128), nullable=True)
    role = db.Column(db.String(20), default='member')  # 'admin' or 'member'
    expo_push_token = db.Column(db.String(255), nullable=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('families.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    message_type = db.Column(db.String(20), default='text') # 'text', 'file', 'alert'
    content = db.Column(db.Text, nullable=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('families.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Fixed: not nullable
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(20), default='medium')
    status = db.Column(db.String(20), default='pending')
    requires_transaction = db.Column(db.Boolean, default=False)
    due_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Grocery(db.Model):
    __tablename__ = 'groceries'
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('families.id'), nullable=False)
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit = db.Column(db.String(20), default='')
    category = db.Column(db.String(50), default='Other')
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('families.id'), nullable=False)
    paid_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    for_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    receipt_doc_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    type = db.Column(db.String(20), default='expense')  # 'income', 'expense'
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(300), nullable=True)  # Added: notes/description field
    payment_method = db.Column(db.String(50), nullable=True)  # UPI, Cash, Card
    location = db.Column(db.String(150), nullable=True)
    tags = db.Column(db.String(200), nullable=True)
    is_recurring = db.Column(db.Boolean, default=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PasswordVault(db.Model):
    __tablename__ = 'password_vault'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(150), nullable=True)
    encrypted_password = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(300), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    family_id = db.Column(db.Integer, db.ForeignKey('families.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    stored_filename = db.Column(db.String(300), nullable=False)  # uuid-prefixed safe name
    file_path = db.Column(db.String(300), nullable=True, default='') # Legacy structural anchor
    size_bytes = db.Column(db.Integer, default=0)
    mime_type = db.Column(db.String(100), default='application/octet-stream')
    tags = db.Column(db.String(200), nullable=True)
    category = db.Column(db.String(50), nullable=False)  # Govt ID, Bank Docs, etc.
    visibility = db.Column(db.String(20), default='individual')  # individual or family
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
