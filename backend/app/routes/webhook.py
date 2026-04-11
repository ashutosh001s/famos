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
    """Run git pull intrinsically so Flask can return 200 immediately without relying on shell scripts."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        # Pull updates
        subprocess.run(['git', 'pull', 'origin', 'main'], cwd=base_dir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Hydrate dependencies natively using the active virtual environment Python
        pip_exec = os.path.join(base_dir, 'backend', 'venv', 'bin', 'pip')
        # Windows fallback just in case
        if not os.path.exists(pip_exec):
            pip_exec = os.path.join(base_dir, 'backend', 'venv', 'Scripts', 'pip')
        
        reqs_file = os.path.join(base_dir, 'backend', 'requirements.txt')
        if os.path.exists(pip_exec) and os.path.exists(reqs_file):
            subprocess.run([pip_exec, 'install', '-r', reqs_file], cwd=base_dir, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # If Gunicorn/Uvicorn or debug active, touching init forces an auto-reload
        init_file = os.path.join(base_dir, 'backend', 'app', '__init__.py')
        if os.path.exists(init_file):
            subprocess.run(['touch', init_file], cwd=base_dir)
        print('[Webhook] Automated Git deploy cycle completed natively.')
    except Exception as e:
        print(f'[Webhook] Intrinsic deploy error: {e}')

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
