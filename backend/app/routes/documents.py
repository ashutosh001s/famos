from flask import Blueprint, request, jsonify, send_file, current_app
from app import db
from app.models import Document
from app.routes.auth import get_current_user
from flask_jwt_extended import jwt_required
import os
from werkzeug.utils import secure_filename
import uuid

documents_bp = Blueprint('documents', __name__)

import tempfile

def get_upload_dir():
    # Safely targets the base application layer to evade proxy-locked isolated directories
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    upload_folder = os.path.join(base_dir, 'secure_uploads')
    try:
        os.makedirs(upload_folder, exist_ok=True)
        return upload_folder
    except PermissionError:
        # Failsafe for tightly isolated linux deployments
        fallback = os.path.join(tempfile.gettempdir(), 'famos_secure_uploads')
        os.makedirs(fallback, exist_ok=True)
        return fallback

# Security: only allow known safe file types
ALLOWED_EXTENSIONS = {
    'pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp',
    'doc', 'docx', 'xls', 'xlsx', 'txt', 'csv'
}
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _safe_file_path(stored_filename):
    """Reconstruct path from stored filename, guarding against traversal."""
    safe_name = os.path.basename(stored_filename)
    upload_dir = get_upload_dir()
    full_path = os.path.join(upload_dir, safe_name)
    # Ensure the resolved path is still inside upload_dir
    if not os.path.abspath(full_path).startswith(os.path.abspath(upload_dir)):
        return None
    return full_path


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
        'user_id': d.user_id
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

    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400

    if not _allowed_file(file.filename):
        return jsonify({'message': f'File type not allowed. Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}'}), 400

    # Check file size
    file.seek(0, 2)  # seek to end
    file_size = file.tell()
    file.seek(0)     # reset
    if file_size > MAX_FILE_BYTES:
        return jsonify({'message': f'File too large (max {MAX_FILE_BYTES // (1024*1024)}MB)'}), 413

    original_filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
    file_path = os.path.join(get_upload_dir(), unique_filename)

    try:
        file.save(file_path)

        new_doc = Document(
            user_id=user.id,
            family_id=user.family_id,
            filename=original_filename,       # human-readable name shown in UI
            stored_filename=unique_filename,  # safe uuid-prefixed name on disk
            category=category,
            visibility=visibility
        )
        db.session.add(new_doc)
        db.session.commit()

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
