from flask import Blueprint, render_template, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from database import get_collections
from datetime import datetime
import logging
from functools import wraps
import csv
import io # Diperlukan untuk menulis CSV di memori

# Inisialisasi Blueprint
web_admin_bp = Blueprint('web_admin_bp', __name__, url_prefix='/web/admin')
logger = logging.getLogger(__name__)

# Custom decorator untuk memastikan hanya admin yang bisa mengakses
def admin_required_web(f):
    @login_required
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Anda tidak memiliki akses sebagai Admin.', 'danger')
            return redirect(url_for('web_auth_bp.web_login'))
        return f(*args, **kwargs)
    return decorated_function

# Rute untuk Dashboard Admin
@web_admin_bp.route("/dashboard")
@admin_required_web
def admin_dashboard():
    # ... (logika dashboard tetap sama, tidak perlu diubah) ...
    users_collection = get_collections()["users"]
    wawancara_collection = get_collections()["wawancara"]
    messages_collection = get_collections()["messages"]
    try:
        total_users = users_collection.count_documents({})
        total_narration_sessions = wawancara_collection.count_documents({"type": "narration_practice"})
        total_hrd_sessions = wawancara_collection.count_documents({"type": "hrd_simulation"})
        total_chat_messages = messages_collection.count_documents({})
        latest_registrations = list(users_collection.find({}, {"_id": 0, "username": 1, "email": 1, "created_at": 1}).sort("created_at", -1).limit(5))
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
        return render_template("admin_dashboard.html", error=str(e))

# Rute untuk menampilkan tabel pengguna
@web_admin_bp.route("/users")
@admin_required_web
def manage_users():
    users_collection = get_collections()["users"]
    try:
        # PERINGATAN: Mengambil data password (hash) adalah risiko keamanan.
        # Baris ini sengaja mengambil semua kolom.
        users_list = list(users_collection.find({}))

        # Proses data untuk ditampilkan di template
        for user in users_list:
            user['_id'] = str(user['_id'])
            if 'created_at' in user and isinstance(user.get('created_at'), datetime):
                user['created_at'] = user['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            if 'last_login' in user and isinstance(user.get('last_login'), datetime):
                user['last_login'] = user['last_login'].strftime('%Y-%m-%d %H:%M:%S')
            else:
                user['last_login'] = 'Belum pernah' # Teks default jika belum pernah login

        return render_template("admin_users.html", users=users_list)
    except Exception as e:
        logger.error(f"Error loading users list for admin: {e}")
        flash('Terjadi kesalahan saat memuat daftar pengguna.', 'danger')
        return render_template("admin_users.html", users=[], error=str(e))


# --- FUNGSI BARU UNTUK GENERATE CSV ---
@web_admin_bp.route("/users/download_csv")
@admin_required_web
def download_users_csv():
    """
    Mengambil semua data pengguna dan mengembalikannya sebagai file CSV.
    """
    users_collection = get_collections()["users"]
    try:
        users = list(users_collection.find({}))
        
        # Menggunakan io.StringIO untuk menulis CSV ke string di memori
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Menulis header CSV
        header = [
            'ID', 'Username', 'Email', 'Password (Hashed)', 'Gender', 
            'Pekerjaan', 'Admin?', 'Terdaftar Sejak', 'Login Terakhir'
        ]
        writer.writerow(header)
        
        # Menulis data pengguna baris per baris
        for user in users:
            # Mengonversi data agar sesuai dengan format string
            is_admin = 'Ya' if user.get('is_admin') else 'Tidak'
            
            created_at_str = ''
            if isinstance(user.get('created_at'), datetime):
                created_at_str = user['created_at'].strftime('%Y-%m-%d %H:%M:%S')

            last_login_str = 'Belum pernah'
            if isinstance(user.get('last_login'), datetime):
                last_login_str = user['last_login'].strftime('%Y-%m-%d %H:%M:%S')

            row = [
                str(user.get('_id')),
                user.get('username'),
                user.get('email'),
                user.get('password'), # PERINGATAN: Mengekspor hash password sangat tidak aman!
                user.get('gender'),
                user.get('occupation'),
                is_admin,
                created_at_str,
                last_login_str
            ]
            writer.writerow(row)
        
        output.seek(0) # Kembali ke awal string buffer
        
        # Membuat response Flask untuk mengirim file
        return Response(
            output,
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment;filename=daftar_pengguna.csv"
            }
        )
    except Exception as e:
        logger.error(f"Error generating users CSV for download: {e}")
        flash('Gagal membuat file CSV. Silakan coba lagi.', 'danger')
        return redirect(url_for('web_admin_bp.manage_users'))