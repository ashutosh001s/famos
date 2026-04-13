import requests
import logging
from app import db
from app.models import User

logger = logging.getLogger('famos')

def send_push_notification(to_token, title, body, data=None):
    if not to_token:
        return
    try:
        payload = {
            "to": to_token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default"
        }
        response = requests.post(
            'https://exp.host/--/api/v2/push/send',
            json=payload,
            headers={
                'Accept': 'application/json',
                'Accept-encoding': 'gzip, deflate',
                'Content-Type': 'application/json',
            },
            timeout=5
        )
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send push to {to_token}: {e}")

def broadcast_to_family(family_id, exclude_user_id, title, body, data=None):
    """Sends a push notification to all users in a family except the trigger user."""
    members = User.query.filter_by(family_id=family_id).all()
    for member in members:
        if member.id != exclude_user_id and member.expo_push_token:
            send_push_notification(member.expo_push_token, title, body, data)
