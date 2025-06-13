# routes/admin_routes.py
# (Ini adalah file untuk API admin yang diakses oleh Flutter)
from flask import Blueprint, request, jsonify
from database import get_collections
from auth_decorators import admin_required, require_api_key
import logging
from bson import ObjectId # Import ObjectId
import datetime # <--- TAMBAHKAN INI

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/api/admin')
logger = logging.getLogger(__name__)

# Access collections
def get_admin_collections():
    cols = get_collections()
    return cols["users"], cols["wawancara"], cols["messages"] # Tambahkan koleksi lain jika admin butuh akses

@admin_bp.route("/dashboard", methods=["GET"])
@admin_required
@require_api_key
def admin_dashboard(current_user):
    logger.info(f"Admin dashboard (API) accessed by: {current_user.get('username')} (ID: {current_user.get('id')})")
    users_collection, wawancara_collection, messages_collection = get_admin_collections()

    try:
        total_users = users_collection.count_documents({})
        total_narration_sessions = wawancara_collection.count_documents({"type": "narration_practice"})
        total_hrd_sessions = wawancara_collection.count_documents({"type": "hrd_simulation"})
        total_chat_messages = messages_collection.count_documents({})

        latest_registrations = list(users_collection.find({}, {"_id": 1, "username": 1, "email": 1, "created_at": 1}).sort("created_at", -1).limit(5))
        for user in latest_registrations:
            user['_id'] = str(user['_id'])
            # Pastikan tanggal diubah ke format string yang tepat untuk JSON
            if 'created_at' in user and isinstance(user['created_at'], datetime):
                user['created_at'] = user['created_at'].isoformat()


        logger.info(f"Admin dashboard (API) data retrieved for {current_user.get('username')}")
        return jsonify({
            "status": "success",
            "message": "Welcome to Admin Dashboard (API)!",
            "stats": {
                "total_users": total_users,
                "total_narration_sessions": total_narration_sessions,
                "total_hrd_sessions": total_hrd_sessions,
                "total_chat_messages": total_chat_messages
            },
            "latest_registrations": latest_registrations
        }), 200

    except Exception as e:
        logger.error(f"Error accessing admin dashboard (API) for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Failed to load admin data (API): {str(e)}"}), 500

@admin_bp.route("/users", methods=["GET"])
@admin_required
@require_api_key
def get_all_users(current_user):
    logger.info(f"Admin (API) is fetching all users. By: {current_user.get('username')}")
    users_collection, _, _ = get_admin_collections()

    try:
        users = list(users_collection.find({}, {"password": 0})) # Jangan kirim password
        for user in users:
            user['_id'] = str(user['_id'])
            if 'created_at' in user and isinstance(user['created_at'], datetime):
                user['created_at'] = user['created_at'].isoformat()
            if 'last_login' in user and isinstance(user.get('last_login'), datetime):
                user['last_login'] = user['last_login'].isoformat()

        logger.info(f"Admin (API) {current_user.get('username')} retrieved {len(users)} users.")
        return jsonify({"status": "success", "users": users}), 200
    except Exception as e:
        logger.error(f"Error fetching all users for admin (API) {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Failed to load users (API): {str(e)}"}), 500