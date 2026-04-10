from flask import Blueprint, request, jsonify, send_file
from app import db
from app.models import Document
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
import os
from werkzeug.utils import secure_filename
import uuid

documents_bp = Blueprint('documents', __name__)

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'secure_uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@documents_bp.route('/', methods=['GET'])
@jwt_required()
def get_documents():
    current_user = json.loads(get_jwt_identity())
    family_id = current_user['family_id']
    user_id = current_user['id']
    
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
    current_user = json.loads(get_jwt_identity())
    
    if 'file' not in request.files:
        return jsonify({'message': 'No file part'}), 400
        
    file = request.files['file']
    category = request.form.get('category', 'Other')
    visibility = request.form.get('visibility', 'individual')
    
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
        
    if file:
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        safe_filename = f"{unique_id}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        
        file.save(file_path)
        
        new_doc = Document(
            user_id=current_user['id'],
            family_id=current_user['family_id'],
            filename=filename,
            file_path=file_path,
            category=category,
            visibility=visibility
        )
        db.session.add(new_doc)
        db.session.commit()
        
        return jsonify({'message': 'File uploaded successfully', 'id': new_doc.id}), 201

@documents_bp.route('/<int:doc_id>/download', methods=['GET'])
@jwt_required()
def download_document(doc_id):
    current_user = json.loads(get_jwt_identity())
    doc = Document.query.filter_by(id=doc_id, family_id=current_user['family_id']).first()
    
    if not doc:
        return jsonify({'message': 'Not found or unauthorized'}), 404
        
    if doc.visibility == 'individual' and doc.user_id != current_user['id']:
        return jsonify({'message': 'Access Denied: Document is private'}), 403
        
    return send_file(doc.file_path, as_attachment=True, download_name=doc.filename)
