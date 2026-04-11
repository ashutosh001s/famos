from flask import Blueprint, request, jsonify
import hmac, hashlib, subprocess, os, threading

webhook_bp = Blueprint('webhook', __name__)

def _verify_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """Verify GitHub's HMAC-SHA256 webhook signature."""
    secret = os.getenv('GITHUB_WEBHOOK_SECRET', '')
    if not secret:
        return False  # Reject all requests if secret not set
    mac = hmac.new(secret.encode(), payload_bytes, hashlib.sha256)
    expected = 'sha256=' + mac.hexdigest()
    return hmac.compare_digest(expected, signature_header or '')

def _run_deploy():
    """Run deploy.sh in the background so Flask can return 200 immediately."""
    deploy_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', '..', '..', 'deploy.sh'
    )
    deploy_script = os.path.normpath(deploy_script)
    try:
        subprocess.Popen(
            ['bash', deploy_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Detach from Flask process
        )
    except Exception as e:
        print(f'[Webhook] Deploy script error: {e}')

@webhook_bp.route('/github', methods=['POST'])
def github_webhook():
    # 1. Verify signature
    sig = request.headers.get('X-Hub-Signature-256', '')
    if not _verify_signature(request.data, sig):
        return jsonify({'error': 'Invalid signature'}), 401

    # 2. Only act on pushes to main branch
    payload = request.get_json(silent=True) or {}
    ref = payload.get('ref', '')

    if ref != 'refs/heads/main':
        return jsonify({'message': f'Ignored ref: {ref}'}), 200

    # 3. Fire deploy in background thread (returns 200 immediately)
    print(f"[Webhook] Push to main detected — deploying commit {payload.get('after', '')[:7]}")
    thread = threading.Thread(target=_run_deploy, daemon=True)
    thread.start()

    return jsonify({'message': 'Deploy started'}), 200
