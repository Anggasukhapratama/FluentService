# routes/web_admin_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_collections # Import get_collections
from datetime import datetime # Untuk formatting tanggal
import logging

web_admin_bp = Blueprint('web_admin_bp', __name__, url_prefix='/web/admin')
logger = logging.getLogger(__name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/web/admin') # <--- Nama variabelnya adalah admin_bp

# Custom decorator for admin access
def admin_required_web(f):
    @login_required
    @wraps(f) # Import wraps from functools
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Anda tidak memiliki akses sebagai Admin.', 'danger')
            return redirect(url_for('web_auth_bp.web_login')) # Or redirect to user home
        return f(*args, **kwargs)
    return decorated_function

# Import wraps
from functools import wraps

@web_admin_bp.route("/dashboard")
@admin_required_web # Gunakan dekorator kustom admin
def admin_dashboard():
    users_collection = get_collections()["users"]
    wawancara_collection = get_collections()["wawancara"]
    messages_collection = get_collections()["messages"]

    try:
        total_users = users_collection.count_documents({})
        total_narration_sessions = wawancara_collection.count_documents({"type": "narration_practice"})
        total_hrd_sessions = wawancara_collection.count_documents({"type": "hrd_simulation"})
        total_chat_messages = messages_collection.count_documents({})

        latest_registrations = list(users_collection.find({}, {"_id": 0, "username": 1, "email": 1, "created_at": 1}).sort("created_at", -1).limit(5))
        # Convert datetime to string for template
        for user in latest_registrations:
            if 'created_at' in user and isinstance(user['created_at'], datetime):
                user['created_at'] = user['created_at'].strftime('%Y-%m-%d %H:%M:%S')

        return render_template(
            "admin_dashboard.html",
            total_users=total_users,
            total_narration_sessions=total_narration_sessions,
            total_hrd_sessions=total_hrd_sessions,
            total_chat_messages=total_chat_messages,
            latest_registrations=latest_registrations
        )
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {e}")
        flash('Terjadi kesalahan saat memuat data dashboard.', 'danger')
        return render_template("admin_dashboard.html", error=str(e)) # Atau render error page


@web_admin_bp.route("/users")
@admin_required_web
def manage_users():
    users_collection = get_collections()["users"]
    try:
        users = list(users_collection.find({}, {"password": 0})) # Jangan kirim password
        for user in users:
            user['_id'] = str(user['_id']) # Convert ObjectId to string
            if 'created_at' in user and isinstance(user['created_at'], datetime):
                user['created_at'] = user['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            if 'last_login' in user and isinstance(user['last_login'], datetime):
                user['last_login'] = user['last_login'].strftime('%Y-%m-%d %H:%M:%S')

        return render_template("admin_users.html", users=users)
    except Exception as e:
        logger.error(f"Error loading users list for admin: {e}")
        flash('Terjadi kesalahan saat memuat daftar pengguna.', 'danger')
        return render_template("admin_users.html", users=[], error=str(e))

# Anda bisa menambahkan rute lain seperti edit/delete user di sini
# @web_admin_bp.route("/users/<user_id>/edit", methods=["GET", "POST"])
# @admin_required_web
# def edit_user(user_id):
#     # ...
#     pass