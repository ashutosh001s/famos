from flask import Blueprint, request, jsonify
from app import db
from app.models import ChatMessage, User, Document
from app.routes.auth import get_current_user
from flask_jwt_extended import jwt_required
from app.push_service import broadcast_to_family

chat_bp = Blueprint('chat', __name__)

def _build_user_map(messages):
    user_ids = {m.sender_id for m in messages if m.sender_id}
    if not user_ids:
        return {}
    return {u.id: u.name for u in User.query.filter(User.id.in_(user_ids)).all()}

def _build_doc_map(messages):
    doc_ids = {m.document_id for m in messages if m.document_id}
    if not doc_ids:
        return {}
    return {d.id: d.mime_type for d in Document.query.filter(Document.id.in_(doc_ids)).all()}

@chat_bp.route('/', methods=['GET'])
@jwt_required()
def get_chat_history():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify([]), 200

    # Fetch last 100 messages chronologically correctly (oldest to newest by reversing the desc limit)
    messages = ChatMessage.query.filter_by(family_id=user.family_id).order_by(ChatMessage.id.desc()).limit(100).all()
    messages.reverse()
    
    user_map = _build_user_map(messages)
    doc_map = _build_doc_map(messages)

    return jsonify([{
        'id': m.id,
        'sender_id': m.sender_id,
        'sender_name': user_map.get(m.sender_id, 'System'),
        'message_type': m.message_type,
        'content': m.content,
        'document_id': m.document_id,
        'mime_type': doc_map.get(m.document_id),
        'created_at': m.created_at.isoformat() if m.created_at else None
    } for m in messages]), 200

@chat_bp.route('/', methods=['POST'])
@jwt_required()
def send_message():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify({'message': 'You must be in a family to chat'}), 403

    data = request.get_json()
    message_type = data.get('message_type', 'text')
    content = data.get('content', '').strip()
    document_id = data.get('document_id')

    if message_type == 'text' and not content:
        return jsonify({'message': 'Message cannot be empty'}), 400

    msg = ChatMessage(
        family_id=user.family_id,
        sender_id=user.id,
        message_type=message_type,
        content=content,
        document_id=document_id
    )
    db.session.add(msg)
    db.session.commit()

    # Trigger Push Notification
    title_text = f"New Message from {user.name}" if message_type == 'text' else f"🖼️ {user.name} sent media"
    body_text = content[:100] if message_type == 'text' else "Tap to view in FamOS Chat."
    broadcast_to_family(user.family_id, user.id, title_text, body_text)

    return jsonify({'message': 'Sent', 'id': msg.id}), 201

def auto_alert(family_id, user_name, action_text):
    """Utility to inject a system alert into the chat stream and trigger a Push."""
    try:
        msg = ChatMessage(
            family_id=family_id,
            sender_id=None,
            message_type='alert',
            content=f"{user_name} {action_text}"
        )
        db.session.add(msg)
        db.session.commit()
        
        # Broadcast Push Notification
        broadcast_to_family(family_id, None, "FamOS Alert", f"{user_name} {action_text}")
    except Exception as e:
        import logging
        logging.getLogger('famos.chat').error(f"Failed to auto-alert: {e}")
