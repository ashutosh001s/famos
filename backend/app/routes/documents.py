from flask import Blueprint, request, jsonify, send_file, current_app
from app import db
from app.models import Document
from app.routes.auth import get_current_user
from app.routes.chat import auto_alert
from flask_jwt_extended import jwt_required
import os
from werkzeug.utils import secure_filename
import uuid

documents_bp = Blueprint('documents', __name__)

import tempfile
import mimetypes

def get_upload_dir():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    upload_folder = os.path.join(base_dir, 'secure_uploads')
    try:
        os.makedirs(upload_folder, exist_ok=True)
        return upload_folder
    except PermissionError:
        fallback = os.path.join(tempfile.gettempdir(), 'famos_secure_uploads')
        os.makedirs(fallback, exist_ok=True)
        return fallback

# Security: Fam-Drive blocks explicit executing malware
BANNED_EXTENSIONS = {
    'exe', 'sh', 'bat', 'apk', 'msi', 'cmd', 'vbs', 'scr', 'bin'
}
USER_QUOTA_BYTES = 50 * 1024 * 1024 * 1024  # 50 GB limit

def _allowed_file(filename):
    if '.' not in filename:
        return True # files without extensions allowed
    ext = filename.rsplit('.', 1)[1].lower()
    return ext not in BANNED_EXTENSIONS


def _safe_file_path(stored_filename):
    """Reconstruct path from stored filename, guarding against traversal."""
    safe_name = os.path.basename(stored_filename)
    upload_dir = get_upload_dir()
    full_path = os.path.join(upload_dir, safe_name)
    # Ensure the resolved path is still inside upload_dir
    if not os.path.abspath(full_path).startswith(os.path.abspath(upload_dir)):
        return None
    return full_path


@documents_bp.route('/quota', methods=['GET'])
@jwt_required()
def get_quota():
    user = get_current_user()
    docs = Document.query.filter_by(user_id=user.id).all()
    used = sum(d.size_bytes or 0 for d in docs)
    return jsonify({
        'used_bytes': used,
        'limit_bytes': USER_QUOTA_BYTES,
        'limit_gb': 50
    }), 200

@documents_bp.route('/', methods=['GET'])
@jwt_required()
def get_documents():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify([]), 200

    family_id = user.family_id
    user_id = user.id

    # Get all family docs OR individual docs belonging to me
    docs = Document.query.filter(
        db.or_(
            Document.visibility == 'family',
            db.and_(Document.visibility == 'individual', Document.user_id == user_id)
        ),
        Document.family_id == family_id
    ).order_by(Document.id.desc()).all()

    return jsonify([{
        'id': d.id,
        'filename': d.filename,
        'category': d.category,
        'visibility': d.visibility,
        'upload_date': d.upload_date.isoformat() if d.upload_date else None,
        'user_id': d.user_id,
        'size_bytes': d.size_bytes,
        'mime_type': d.mime_type
    } for d in docs]), 200


@documents_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_document():
    user = get_current_user()
    if not user or not user.family_id:
        return jsonify({'message': 'You must be in a family to upload documents'}), 403

    if 'file' not in request.files:
        return jsonify({'message': 'No file part'}), 400

    file = request.files['file']
    category = request.form.get('category', 'Other')
    visibility = request.form.get('visibility', 'individual')

    tags = request.form.get('tags', '').strip()

    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400

    if not _allowed_file(file.filename):
        return jsonify({'message': 'Security Breach: Executable/malicious files are completely forbidden.'}), 400

    # Quota logic
    user_docs = Document.query.filter_by(user_id=user.id).all()
    used_space = sum(d.size_bytes or 0 for d in user_docs)

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    
    if used_space + file_size > USER_QUOTA_BYTES:
        return jsonify({'message': 'Fam-Drive Storage limit exceeded (50GB max).'}), 413

    original_filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
    file_path = os.path.join(get_upload_dir(), unique_filename)

    try:
        file.save(file_path)

        mime_type = file.mimetype or mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'

        new_doc = Document(
            user_id=user.id,
            family_id=user.family_id,
            filename=original_filename,
            stored_filename=unique_filename,
            file_path=unique_filename,
            category=category,
            visibility=visibility,
            size_bytes=file_size,
            mime_type=mime_type,
            tags=tags or None
        )
        db.session.add(new_doc)
        db.session.commit()

        if category != 'Other' or tags != 'chat_media':
            auto_alert(user.family_id, user.name, f"uploaded a new document: {original_filename}")

        return jsonify({'message': 'File uploaded successfully', 'id': new_doc.id}), 201
    except Exception as e:
        return jsonify({'message': f'Server Error: {str(e)}'}), 500


@documents_bp.route('/<int:doc_id>/download', methods=['GET'])
@jwt_required()
def download_document(doc_id):
    user = get_current_user()
    doc = Document.query.filter_by(id=doc_id, family_id=user.family_id).first()

    if not doc:
        return jsonify({'message': 'Not found or unauthorized'}), 404

    if doc.visibility == 'individual' and doc.user_id != user.id:
        return jsonify({'message': 'Access Denied: Document is private'}), 403

    # Reconstruct path safely — never use stored absolute path
    safe_path = _safe_file_path(doc.stored_filename)
    if not safe_path or not os.path.exists(safe_path):
        return jsonify({'message': 'File not found on server'}), 404

    return send_file(safe_path, as_attachment=True, download_name=doc.filename)


@documents_bp.route('/<int:doc_id>/visibility', methods=['PATCH'])
@jwt_required()
def update_visibility(doc_id):
    user = get_current_user()
    doc = Document.query.filter_by(id=doc_id, user_id=user.id).first()
    if not doc:
        return jsonify({'message': 'Document not found or unauthorized'}), 404

    data = request.get_json() or {}
    new_vis = data.get('visibility')
    if new_vis in ['individual', 'family']:
        doc.visibility = new_vis
        db.session.commit()
        return jsonify({'message': 'Visibility updated'}), 200
    return jsonify({'message': 'Invalid visibility'}), 400

@documents_bp.route('/<int:doc_id>', methods=['DELETE'])
@jwt_required()
def delete_document(doc_id):
    """Delete a document. Only the uploader can delete their own document."""
    user = get_current_user()
    doc = Document.query.filter_by(id=doc_id, family_id=user.family_id).first()

    if not doc:
        return jsonify({'message': 'Not found or unauthorized'}), 404

    if doc.user_id != user.id:
        return jsonify({'message': 'Only the uploader can delete this document'}), 403

    # Delete physical file
    safe_path = _safe_file_path(doc.stored_filename)
    if safe_path and os.path.exists(safe_path):
        os.remove(safe_path)

    db.session.delete(doc)
    db.session.commit()
    return jsonify({'message': 'Document deleted'}), 200
