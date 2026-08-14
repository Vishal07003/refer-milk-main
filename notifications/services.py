import os
import logging
from django.conf import settings
from accounts.models import DeviceToken, Notification

logger = logging.getLogger(__name__)

_firebase_app = None


def get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        key_path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_KEY_PATH', None)
        if not key_path or not os.path.exists(key_path):
            firebase_dir = os.path.join(settings.BASE_DIR, 'firebase')
            if os.path.exists(firebase_dir):
                json_files = [f for f in os.listdir(firebase_dir) if f.endswith('.json')]
                if json_files:
                    key_path = os.path.join(firebase_dir, json_files[0])

        if not key_path or not os.path.exists(key_path):
            logger.warning(f"Firebase service account file not found at path: {key_path}")
            return None

        cred = credentials.Certificate(key_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully.")
        return _firebase_app
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        return None


def send_push_notification(tokens, title, body, data=None):
    """
    Sends FCM push notifications to a list of device tokens.
    Deactivates unregistered/invalid tokens automatically.
    """
    if not tokens:
        return 0

    if isinstance(tokens, str):
        tokens = [tokens]

    app = get_firebase_app()
    if not app:
        logger.warning("Push notification skipped: Firebase app is not initialized.")
        return 0

    try:
        from firebase_admin import messaging

        formatted_data = {}
        if data and isinstance(data, dict):
            for k, v in data.items():
                formatted_data[str(k)] = str(v)

        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=formatted_data,
            tokens=tokens,
        )

        if hasattr(messaging, 'send_each_for_multicast'):
            response = messaging.send_each_for_multicast(message)
        else:
            response = messaging.send_multicast(message)

        logger.info(f"FCM Multicast sent: {response.success_count} success, {response.failure_count} failures.")

        if response.failure_count > 0:
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    err = resp.exception
                    failed_token = tokens[idx]
                    logger.info(f"Deactivating failed FCM token ({err}): {failed_token}")
                    DeviceToken.objects.filter(token=failed_token).update(is_active=False)

        return response.success_count
    except Exception as e:
        logger.error(f"Error sending FCM push notification: {e}")
        return 0


def send_notification_to_user(user, title, body, data=None, notification_type="general"):
    """
    Persists notification in database and dispatches FCM push notification to active user tokens.
    """
    # 1. Create in-app notification record
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=body,
        notification_type=notification_type,
    )

    # 2. Fetch active FCM tokens for this user
    active_tokens = list(
        DeviceToken.objects.filter(user=user, is_active=True).values_list("token", flat=True)
    )

    # 3. Dispatch FCM push notification
    if active_tokens:
        send_push_notification(active_tokens, title, body, data)

    return notification


def send_notification_to_all_users(title, body, data=None, notification_type="general", role=None):
    """
    Dispatches in-app and FCM push notifications to all active users (or filtered by role).
    Handles FCM multicast batching (max 500 tokens per batch).
    """
    from accounts.models import User

    users = User.objects.filter(is_active=True)
    if role:
        users = users.filter(role=role)

    user_list = list(users)
    if not user_list:
        return 0

    # 1. Bulk create in-app notification records
    notifications = [
        Notification(
            user=user,
            title=title,
            message=body,
            notification_type=notification_type,
        )
        for user in user_list
    ]
    Notification.objects.bulk_create(notifications)

    # 2. Fetch all active FCM device tokens for these users
    active_tokens = list(
        DeviceToken.objects.filter(user__in=user_list, is_active=True).values_list("token", flat=True)
    )

    # 3. Dispatch FCM push notifications in batches (FCM limit: 500 tokens per call)
    if active_tokens:
        batch_size = 500
        for i in range(0, len(active_tokens), batch_size):
            batch = active_tokens[i : i + batch_size]
            send_push_notification(batch, title, body, data)

    return len(notifications)
