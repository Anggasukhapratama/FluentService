# routes/web_auth_routes.py
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, current_user, login_required
from extensions import bcrypt, load_user # Import bcrypt and load_user from extensions
from database import get_collections
import logging

web_auth_bp = Blueprint('web_auth_bp', __name__, url_prefix='/web')
logger = logging.getLogger(__name__)

@web_auth_bp.route("/login", methods=["GET", "POST"])
def web_login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('web_admin_bp.admin_dashboard'))
        return redirect(url_for('home')) # Redirect to user home if already logged in

    if request.method == "POST":
        email = request.form.get('email')
        password = request.form.get('password')
        users_collection = get_collections()["users"]
        user_doc = users_collection.find_one({"email": email})

        if user_doc and bcrypt.check_password_hash(user_doc["password"], password):
            user = load_user(str(user_doc['_id'])) # Get User object compatible with Flask-Login
            login_user(user, remember=True) # "remember=True" to keep session even if browser closes
            
            logger.info(f"Web login successful for user: {user.username}")
            flash('Login berhasil!', 'success')
            
            # Redirect berdasarkan peran
            if user.is_admin:
                return redirect(url_for('web_admin_bp.admin_dashboard'))
            return redirect(url_for('home')) # Redirect ke halaman utama user

        flash('Email atau password salah.', 'danger')
    return render_template("admin_login.html")

@web_auth_bp.route("/logout")
@login_required # Hanya bisa logout jika sudah login
def web_logout():
    username = current_user.username # Simpan username sebelum logout
    logout_user()
    logger.info(f"User {username} logged out from web.")
    flash('Anda telah logout.', 'info')
    return redirect(url_for('web_auth_bp.web_login'))