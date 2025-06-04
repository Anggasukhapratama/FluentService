import contextlib
import io
import os
from flask import Flask, flash, redirect, render_template, request, jsonify, Blueprint, send_from_directory, session, url_for
from flask_cors import CORS
# from models import register_user, login_user, get_user_by_username # Ini sepertinya sudah di-inlin di app.py
import cv2
from speech_recognition import Recognizer, AudioFile
import tempfile
import base64
import numpy as np
from datetime import datetime, timedelta
import jwt
from functools import wraps
from pymongo import MongoClient
import random
import time
from flask_bcrypt import Bcrypt
from bson import ObjectId
from flask_swagger_ui import get_swaggerui_blueprint
from nltk.tokenize import word_tokenize
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import uuid
from flask_mail import Mail, Message
import secrets
import pymongo.errors
import logging # Tambahkan logging untuk debugging lebih baik

# Konfigurasi logging Flask
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Flask App
# Update CORS untuk mengizinkan header X-API-Key
app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {"origins": "*"},
    r"/*": {"origins": "*"}
}, headers=['Content-Type', 'Authorization', 'X-API-Key'])

bcrypt = Bcrypt(app)

# MongoDB Connection
client = MongoClient("mongodb://localhost:27017/")
db = client["flutterauth"]
users_collection = db["users"]
wawancara_collection = db["wawancara"]
sessions_collection = db["sessions"]
login_attempts_collection = db["login_attempts"]
messages_collection = db["messages"] #
password_reset_tokens_collection = db["password_reset_tokens"] # Sudah ada, pastikan tidak ganda
otp_tokens_collection = db["otp_tokens"] # <-- KOLEKSI BARU UNTUK OTP REGISTRASI
topics_collection = db["topics"] # NEW: Koleksi untuk topik diskusi


# JWT Configuration
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET', 'fluentendpoint')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'another-secret-key-for-sessions')
app.config['INACTIVITY_DAYS'] = 3  # Days before user is marked inactive
app.config['API_SECRET_KEY'] = os.environ.get('API_KEY', 'fluentendpoint')
GOOGLE_CLIENT_ID_WEB = os.environ.get('GOOGLE_CLIENT_ID_WEB', '757791586393-5jci80p25u6s81j1atbem043gitsegm7.apps.googleusercontent.com')

# forgot password
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER', 'edigitaldompet@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS', 'jyag nujw fwki njdl')
app.config['MAIL_DEFAULT_SENDER'] = ('Fluent', app.config['MAIL_USERNAME'])

mail = Mail(app)

# HRD Questions Database
hrd_question_details = {
    "Ceritakan pengalaman kerja Anda yang paling menantang": {
        "keywords": ["tantangan", "solusi", "belajar", "mengatasi", "proyek"],
        "ideal_length": 20
    },
    "Apa kelebihan dan kekurangan Anda?": {
        "keywords": ["kelebihan", "kekuatan", "kekurangan", "kelemahan", "mengembangkan"],
        "ideal_length": 15
    },
    "Mengapa kami harus mempekerjakan Anda?": {
        "keywords": ["kontribusi", "skill", "cocok", "nilai", "perusahaan"],
        "ideal_length": 18
    },
    "Apa motivasi Anda bekerja di perusahaan ini?": {
        "keywords": ["motivasi", "visi", "misi", "budaya", "perusahaan"],
        "ideal_length": 15
    },
    "Bagaimana Anda menghadapi tekanan di tempat kerja?": {
        "keywords": ["tekanan", "manajemen stres", "prioritas", "tenang", "solusi"],
        "ideal_length": 16
    },
    "Apa pencapaian terbesar Anda dalam karier?": {
        "keywords": ["pencapaian", "hasil", "usaha", "proyek", "target"],
        "ideal_length": 17
    },
    "Bagaimana Anda bekerja dalam tim?": {
        "keywords": ["kerja sama", "tim", "komunikasi", "kontribusi", "kolaborasi"],
        "ideal_length": 15
    },
    "Apa yang Anda ketahui tentang perusahaan ini?": {
        "keywords": ["informasi", "industri", "produk", "layanan", "nilai"],
        "ideal_length": 14
    },
    "Apa rencana karier Anda ke depan?": {
        "keywords": ["rencana", "karier", "tujuan", "pengembangan", "masa depan"],
        "ideal_length": 16
    },
    "Bagaimana Anda mengatasi konflik di tempat kerja?": {
        "keywords": ["konflik", "komunikasi", "solusi", "tenang", "kerja sama"],
        "ideal_length": 18
    },
    "Apakah Anda bersedia bekerja lembur atau di bawah tekanan?": {
        "keywords": ["komitmen", "fleksibilitas", "lembur", "dedikasi", "tanggung jawab"],
        "ideal_length": 14
    },
    "Apa yang Anda lakukan jika tidak setuju dengan atasan?": {
        "keywords": ["pendapat", "komunikasi", "respek", "diskusi", "solusi"],
        "ideal_length": 15
    },
    "Apa nilai-nilai kerja yang Anda pegang teguh?": {
        "keywords": ["integritas", "komitmen", "disiplin", "tanggung jawab", "etika"],
        "ideal_length": 14
    },
    "Bagaimana Anda menetapkan prioritas dalam pekerjaan?": {
        "keywords": ["prioritas", "manajemen waktu", "deadline", "efisiensi", "fokus"],
        "ideal_length": 15
    },
    "Apa alasan Anda ingin meninggalkan pekerjaan sebelumnya?": {
        "keywords": ["pengembangan", "tantangan baru", "karier", "motivasi", "tujuan"],
        "ideal_length": 16
    }
}

# Helper Functions
def analyze_audio(audio_data):
    """Mock audio analysis function"""
    # In production, integrate with real speech-to-text service
    return {
        'text': "Ini adalah contoh transkripsi",
        'confidence': 0.85,
        'filler_words': 3,
        'speech_rate': 120
    }

def generate_feedback(analysis):
    """Generate feedback based on analysis"""
    if analysis['confidence'] < 0.5:
        return "Jawaban kurang jelas, coba lebih percaya diri"
    elif analysis['filler_words'] > 5:
        return "Terlalu banyak kata pengisi 'umm', 'ahh'"
    return "Jawaban cukup baik"

def get_user_by_username(username):
    """Utility function to get user by username"""
    return users_collection.find_one({"username": username})

# JWT Token Required Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
                app.logger.debug(f"Received token: {token[:30]}...") # Log token
            except IndexError:
                app.logger.warning("Bearer token malformed")
                return jsonify({'message': 'Bearer token malformed'}), 401

        if not token:
            app.logger.warning("Token is missing!")
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            data = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            app.logger.debug(f"Decoded token data: {data}")

            # Change to get user by email
            current_user = users_collection.find_one({"email": data['email']})

            if not current_user:
                app.logger.warning(f"User not found for email in token: {data.get('email')}")
                return jsonify({'message': 'User not found!'}), 401

            app.logger.debug(f"Current user found: {current_user.get('username')}")
        except jwt.ExpiredSignatureError:
            app.logger.info("Token has expired!")
            return jsonify({'message': 'Token has expired!'}), 401
        except jwt.InvalidTokenError as e:
            app.logger.error(f"Invalid token: {str(e)}")
            return jsonify({'message': 'Token is invalid!', 'error': str(e)}), 401
        except Exception as e:
            app.logger.critical(f"Unexpected error in token_required: {str(e)}")
            return jsonify({'message': 'An unexpected error occurred during token verification.', 'error': str(e)}), 500

        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please login first', 'danger')
            return redirect(url_for('admin_login'))

        user = users_collection.find_one({"username": session['username']})
        if not user or not user.get('is_admin', False):
            flash('You do not have admin privileges', 'danger')
            return redirect(url_for('index'))

        return f(*args, **kwargs)
    return decorated_function

# Function to check and update inactive users
def check_inactive_users():
    inactive_threshold = datetime.utcnow() - timedelta(days=app.config['INACTIVITY_DAYS'])
    users_collection.update_many(
        {
            "last_login": {"$lt": inactive_threshold},
            "is_active": True
        },
        {"$set": {"is_active": False}}
    )

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != app.config['API_SECRET_KEY']:
            app.logger.warning(f"Invalid API Key attempt from {request.remote_addr}. Key: {api_key}")
            return jsonify({'status': 'fail', 'message': 'Invalid or missing API Key'}), 401
        return f(*args, **kwargs)
    return decorated


# Register User
@app.route("/register", methods=["POST"]) # Tetap gunakan /register atau ganti ke /register_with_otp
@require_api_key
def register_with_otp(): # Nama fungsi diubah
    app.logger.info("Register with OTP endpoint hit.")
    data = request.get_json()
    required_fields = ["email", "username", "password", "gender", "occupation", "otp"]
    if not all(field in data for field in required_fields):
        app.logger.warning(f"Incomplete registration data with OTP: {data}")
        return jsonify({"status": "fail", "message": "Data tidak lengkap"}), 400

    try:
        email = data["email"]
        username = data["username"]
        password = data["password"]
        gender = data["gender"]
        occupation = data["occupation"]
        otp_code = data["otp"]

        # 1. Verifikasi OTP
        otp_record = otp_tokens_collection.find_one({"email": email, "otp": otp_code})

        if not otp_record:
            app.logger.warning(f"Registration failed: Invalid OTP for email '{email}'.")
            return jsonify({"status": "fail", "message": "Kode OTP tidak valid"}), 400

        if otp_record['expires_at'] < datetime.utcnow():
            otp_tokens_collection.delete_one({"_id": otp_record['_id']}) # Hapus OTP kadaluwarsa
            app.logger.warning(f"Registration failed: Expired OTP for email '{email}'.")
            return jsonify({"status": "fail", "message": "Kode OTP sudah kedaluwarsa. Mohon minta kode baru."}), 400

        # 2. Cek duplikasi email/username lagi (penting untuk race conditions)
        if users_collection.find_one({"email": email}):
            app.logger.warning(f"Registration failed: Email '{email}' already exists AFTER OTP verification.")
            return jsonify({"status": "fail", "message": "Email sudah terdaftar"}), 409
        if users_collection.find_one({"username": username}):
            app.logger.warning(f"Registration failed: Username '{username}' already exists AFTER OTP verification.")
            return jsonify({"status": "fail", "message": "Username sudah terdaftar"}), 409

        # 3. Proses Registrasi
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user_data = {
            "email": email,
            "username": username,
            "password": hashed_password,
            "gender": gender,
            "occupation": occupation,
            "created_at": datetime.utcnow(),
            "last_login": None,
            "is_active": True,
            "is_admin": False
        }
        users_collection.insert_one(user_data)

        # 4. Hapus OTP setelah berhasil digunakan
        otp_tokens_collection.delete_one({"_id": otp_record['_id']})

        app.logger.info(f"User '{username}' registered successfully with OTP verification.")
        return jsonify({"status": "success", "message": "User registered successfully"}), 201

    except pymongo.errors.PyMongoError as e:
        app.logger.error(f"MongoDB error during OTP registration: {e}")
        return jsonify({"status": "error", "message": "Database error during registration"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error during OTP registration: {e}")
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}), 500


# --- NEW: Request OTP for Registration ---
@app.route("/request_otp_for_registration", methods=["POST"])
@require_api_key
def request_otp_for_registration():
    app.logger.info("Request OTP for registration endpoint hit.")
    data = request.get_json()
    email = data.get('email')
    username = data.get('username') # Mungkin diperlukan untuk pesan email personal

    if not email:
        app.logger.warning("OTP request: Email missing.")
        return jsonify({"status": "fail", "message": "Email is required"}), 400

    # Cek apakah email sudah terdaftar
    if users_collection.find_one({"email": email}):
        app.logger.warning(f"OTP request failed: Email '{email}' already exists.")
        return jsonify({"status": "fail", "message": "Email sudah terdaftar"}), 409
    # Cek apakah username sudah terdaftar
    if users_collection.find_one({"username": username}):
        app.logger.warning(f"OTP request failed: Username '{username}' already exists.")
        return jsonify({"status": "fail", "message": "Username sudah terdaftar"}), 409

    try:
        # Hapus OTP lama untuk email ini (untuk mencegah spam atau OTP kadaluwarsa)
        otp_tokens_collection.delete_many({"email": email})

        otp = str(random.randint(100000, 999999)) # 6 digit OTP
        expires_at = datetime.utcnow() + timedelta(minutes=5) # OTP berlaku 5 menit

        otp_tokens_collection.insert_one({
            "email": email,
            "otp": otp,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at
        })

        msg = Message(
            subject="Kode Verifikasi Registrasi Fluent Anda",
            recipients=[email],
            body=f"""Halo {username if username else 'Pengguna'},

Terima kasih telah mendaftar di Fluent!
Gunakan kode verifikasi berikut untuk menyelesaikan pendaftaran Anda:

Kode Verifikasi: {otp}

Kode ini akan kedaluwarsa dalam 5 menit. Jika Anda tidak mencoba mendaftar, abaikan email ini.

Terima kasih,
Tim Fluent
"""
        )
        mail.send(msg)
        app.logger.info(f"Registration OTP sent to {email}")

        return jsonify({
            "status": "success",
            "message": "Kode verifikasi telah dikirimkan ke email Anda. Cek folder spam jika tidak ditemukan."
        }), 200

    except Exception as e:
        app.logger.error(f"Error sending registration OTP to {email}: {e}")
        return jsonify({"status": "error", "message": "Terjadi kesalahan internal saat mengirim kode verifikasi. Mohon coba lagi nanti."}), 500


# Login User
@app.route("/login", methods=["POST"])
def login():
    app.logger.info("Login endpoint hit.")
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        app.logger.warning("Login attempt with incomplete data.")
        return jsonify({"status": "fail", "message": "Email and password are required"}), 400

    email = data["email"]
    password = data["password"]

    # Cek status blocking
    attempt_record = login_attempts_collection.find_one({"email": email})

    if attempt_record and attempt_record.get('blocked_until') and attempt_record['blocked_until'] > datetime.utcnow():
        remaining_time = (attempt_record['blocked_until'] - datetime.utcnow()).total_seconds()
        app.logger.warning(f"Blocked login attempt for email: {email}. Remaining time: {int(remaining_time)}s")
        return jsonify({
            "status": "fail",
            "message": "Terlalu banyak percobaan login",
            "blocked": True,
            "remaining_seconds": int(remaining_time),
            "attempts": attempt_record['attempts']
        }), 429

    user = users_collection.find_one({"email": email})
    if not user or not bcrypt.check_password_hash(user["password"], password):
        attempts = 1
        blocked_until = None
        if attempt_record:
            attempts = attempt_record['attempts'] + 1
            if attempts >= 5:
                blocked_until = datetime.utcnow() + timedelta(minutes=2)
            elif attempts >= 3:
                blocked_until = datetime.utcnow() + timedelta(seconds=30)

            login_attempts_collection.update_one(
                {"email": email},
                {"$set": {
                    "attempts": attempts,
                    "last_attempt": datetime.utcnow(),
                    "blocked_until": blocked_until
                }},
                upsert=True
            )
        else:
            login_attempts_collection.insert_one({
                "email": email,
                "attempts": 1,
                "last_attempt": datetime.utcnow(),
                "blocked_until": None
            })

        remaining_attempts = max(0, 5 - attempts)
        app.logger.warning(f"Invalid login attempt for email: {email}. Attempts: {attempts}")
        return jsonify({
            "status": "fail",
            "message": "Invalid email or password",
            "attempts": attempts,
            "remaining_attempts": remaining_attempts,
            "blocked": attempts >= 3 # True jika sudah 3 atau lebih
        }), 401

    # Reset attempt counter jika login berhasil
    login_attempts_collection.delete_one({"email": email})

    # Update last_login
    users_collection.update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow(), "is_active": True}})
    app.logger.info(f"User '{user.get('username')}' logged in successfully.")

    # Generate tokens
    access_token = jwt.encode({
        'user_id': str(user['_id']),
        'email': user['email'],
        'exp': datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
    }, app.config['JWT_SECRET_KEY'], algorithm="HS256")

    refresh_token = jwt.encode({
        'user_id': str(user['_id']),
        'email': user['email'],
        'exp': datetime.utcnow() + app.config['JWT_REFRESH_TOKEN_EXPIRES']
    }, app.config['JWT_SECRET_KEY'], algorithm="HS256")

    return jsonify({
        "status": "success",
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "username": user.get("username", ""),
            "gender": user.get("gender", ""),
            "occupation": user.get("occupation", "")
        }
    })

# Refresh Token
@app.route("/refresh", methods=["POST"])
def refresh():
    app.logger.info("Refresh token endpoint hit.")
    refresh_token = request.json.get('refresh_token')
    if not refresh_token:
        app.logger.warning("Refresh token missing from request.")
        return jsonify({"status": "fail", "message": "Refresh token is missing"}), 401

    try:
        data = jwt.decode(refresh_token, app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
        user = users_collection.find_one({"email": data['email']})

        if not user:
            app.logger.warning(f"User not found for refresh token email: {data.get('email')}")
            return jsonify({"status": "fail", "message": "User not found"}), 404

        new_access_token = jwt.encode({
            'user_id': str(user['_id']),
            'email': user['email'],
            'exp': datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
        }, app.config['JWT_SECRET_KEY'], algorithm="HS256")

        app.logger.info(f"Access token refreshed for user: {user.get('username')}")
        return jsonify({
            "status": "success",
            "access_token": new_access_token
        })
    except jwt.ExpiredSignatureError:
        app.logger.info("Refresh token has expired.")
        return jsonify({"status": "fail", "message": "Refresh token has expired"}), 401
    except jwt.InvalidTokenError:
        app.logger.error("Invalid refresh token.")
        return jsonify({"status": "fail", "message": "Invalid refresh token"}), 401
    except Exception as e:
        app.logger.critical(f"Unexpected error during token refresh: {str(e)}")
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}), 500

@app.route("/analyze_realtime", methods=["POST"])
@token_required
@require_api_key
def analyze_realtime(current_user):
    app.logger.info(f"Analyze realtime endpoint hit by user: {current_user.get('username')}")
    data = request.get_json()

    if "frame" not in data:
        app.logger.warning("Frame not provided in analyze_realtime request.")
        return jsonify({"status": "fail", "message": "Frame not provided"}), 400

    try:
        img_data = base64.b64decode(data["frame"])
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            app.logger.warning("Invalid image data received in analyze_realtime.")
            return jsonify({"status": "fail", "message": "Invalid image data"}), 400

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            image_path = tmp_file.name
            cv2.imwrite(image_path, frame)

        from detectors.emotion_detector import detect_emotion_status
        from detectors.mouth_detector import detect_mouth_status
        from detectors.pose_detector import detect_pose_status

        emotion_result = detect_emotion_status(image_path)
        mouth_result = detect_mouth_status(image_path)
        pose_result = detect_pose_status(image_path)

        os.unlink(image_path) # Clean up temp file

        app.logger.debug(f"Realtime analysis results for user {current_user.get('username')}: Emotion={emotion_result}, Mouth={mouth_result}, Pose={pose_result}")
        return jsonify({
            "status": "success",
            "results": {
                "emotion": emotion_result,
                "mouth": mouth_result,
                "pose": pose_result
            }
        })

    except Exception as e:
        app.logger.error(f"Error analyzing realtime image for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/save_wawancara", methods=["POST"])
@token_required
@require_api_key
def save_wawancara(current_user):
    app.logger.info(f"Save wawancara endpoint hit by user: {current_user.get('username')}")
    data = request.get_json()

    try:
        # Menambahkan 'overall_stt_confidence' dari data yang dikirim Flutter ke metrics
        metrics_from_client = data.get("metrics", {})
        # Pastikan 'expression' juga menyimpan dict dari ekspresi, bukan string
        results_from_client = data.get("results", {})

        wawancara_data = {
            "user_id": current_user['_id'],
            "username": current_user['username'],
            "timestamp": datetime.utcnow(),
            "results": results_from_client, # Pastikan ini menyimpan dict emotion
            "metrics": {
                "accuracy": metrics_from_client.get("accuracy", 0),
                "wpm": metrics_from_client.get("wpm", 0),
                "fluency": metrics_from_client.get("fluency", 0),
                "filler_words": metrics_from_client.get("filler_words", 0),
                "overal_stt_confidence": metrics_from_client.get("overall_stt_confidence", 0), # <--- PERBAIKAN: Menyimpan confidence dari client
                # ... metrik lainnya jika ada
            },
            "recording_duration": data.get("recording_duration", 0),
            "feedback": data.get("feedback", []),
            "difficulty": data.get("difficulty", "medium"),
            "type": "narration_practice"
        }

        wawancara_collection.insert_one(wawancara_data)
        app.logger.info(f"Wawancara data saved for user: {current_user.get('username')}")
        return jsonify({"status": "success", "message": "Data wawancara disimpan"})

    except Exception as e:
        app.logger.error(f"Error saving wawancara data for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get_wawancara", methods=["GET"])
@token_required
@require_api_key
def get_wawancara(current_user):
    app.logger.info(f"Get wawancara endpoint hit by user: {current_user.get('username')}")
    try:
        # Hanya ambil sesi dengan type "narration_practice"
        wawancaras = list(wawancara_collection.find(
            {"user_id": current_user['_id'], "type": "narration_practice"}
        ).sort("timestamp", -1).limit(10))

        # Convert ObjectId dan datetime
        for w in wawancaras:
            w['_id'] = str(w['_id'])
            w['timestamp'] = w['timestamp'].isoformat() if isinstance(w['timestamp'], datetime) else str(w['timestamp'])

        app.logger.debug(f"Retrieved {len(wawancaras)} narration practice sessions for user {current_user.get('username')}")
        return jsonify({"status": "success", "wawancaras": wawancaras})

    except Exception as e:
        app.logger.error(f"Error retrieving wawancara data for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/progress', methods=['GET'])
@token_required
@require_api_key
def get_progress(current_user):
    app.logger.info(f"Get progress endpoint hit by user: {current_user.get('username')}")
    try:
        # 1. Hitung total sesi pengguna (narration practice)
        total_sessions = wawancara_collection.count_documents(
            {"user_id": current_user['_id'], "type": "narration_practice"}
        )

        # 2. Ambil 10 sesi narration practice terbaru untuk histori
        raw_sessions = list(wawancara_collection.find(
            {"user_id": current_user['_id'], "type": "narration_practice"}
        ).sort("timestamp", -1).limit(10))

        # --- SANITIZE SESSIONS DATA ---
        sessions = []
        for s in raw_sessions:
            if not isinstance(s, dict):
                app.logger.warning(f"Found malformed session data (not a dict) for user {current_user.get('username')}: {s}. Skipping.")
                continue

            if 'metrics' in s and not isinstance(s['metrics'], dict):
                app.logger.warning(f"Session ID {s.get('_id', 'N/A')} for user {current_user.get('username')} has non-dict 'metrics' field: {s['metrics']}. Setting to empty dict.")
                s['metrics'] = {}
            elif 'metrics' not in s:
                s['metrics'] = {}

            if 'results' in s and not isinstance(s['results'], dict):
                app.logger.warning(f"Session ID {s.get('_id', 'N/A')} for user {current_user.get('username')} has non-dict 'results' field: {s['results']}. Setting to empty dict.")
                s['results'] = {}
            elif 'results' not in s:
                s['results'] = {}

            sessions.append(s)
        # --- END SANITIZE ---

        # 3. Hitung rata-rata skor dari sesi terbaru (max 10)
        total_score = sum(session.get('metrics', {}).get('accuracy', 0) for session in sessions)
        average_score = total_score / len(sessions) if sessions else 0

        # 4. Siapkan histori untuk grafik
        history = [{
            "timestamp": session.get('timestamp').isoformat() if isinstance(session.get('timestamp'), datetime) else str(session.get('timestamp', '')),
            "overall_score": session.get('metrics', {}).get('accuracy', 0)
        } for session in sessions]

        # 5. Ambil metrik dari sesi terbaru
        last_session = sessions[0] if sessions else {}
        metrics = last_session.get('metrics', {})

        # === PERBAIKAN DI SINI: Hitung skor 'Ekspresi Wajah' hanya berdasarkan "Normal" dan "Gugup" ===
        expression_string = last_session.get('results', {}).get('emotion', '').lower()
        expression_score = 0.0 # Default score jika tidak terdeteksi atau tidak dikenali

        if 'normal' in expression_string:
            expression_score = 80.0 # Skor tinggi untuk ekspresi normal/tenang
        elif 'gugup' in expression_string:
            expression_score = 30.0 # Skor rendah untuk ekspresi gugup
        else: # Jika tidak ada deteksi emosi sama sekali, atau stringnya kosong
            expression_score = 0.0 # Atau nilai default lain jika tidak terdeteksi

        app.logger.debug(f"Calculated expression score from string '{expression_string}': {expression_score}")
        # === AKHIR PERBAIKAN ===

        # 6. Identifikasi kelemahan (contoh untuk narasi)
        weaknesses = []
        if metrics.get('wpm', 0) > 0 and metrics.get('wpm', 0) < 100:
            weaknesses.append({
                "area": "Kecepatan Bicara",
                "description": "Kecepatan bicara Anda tergolong lambat (<100 WPM).",
                "progress": metrics.get('wpm', 0) / 150,
                "suggestion": "Cobalah berlatih bicara lebih cepat dan lancar."
            })
        elif metrics.get('wpm', 0) > 180:
             weaknesses.append({
                "area": "Kecepatan Bicara",
                "description": "Kecepatan bicara Anda tergolong terlalu cepat (>180 WPM).",
                "progress": 1.0,
                "suggestion": "Cobalah bicara lebih teratur dan beri jeda."
            })

        if metrics.get('fluency', 0) < 70 and metrics.get('fluency', 0) > 0:
            weaknesses.append({
                "area": "Kelancaran",
                "description": "Kelancaran bicara Anda perlu ditingkatkan (<70%).",
                "progress": metrics.get('fluency', 0) / 100,
                "suggestion": "Latihan membaca nyaring dan mengurangi jeda 'filler words'."
            })
        if metrics.get('filler_words', 0) > 5 and total_sessions > 0:
            weaknesses.append({
                "area": "Kata Pengisi",
                "description": f"Anda terlalu banyak menggunakan kata pengisi ({metrics.get('filler_words')} kali).",
                "progress": 1.0 - (min(metrics.get('filler_words', 0), 10) / 10.0),
                "suggestion": "Cobalah untuk lebih sadar dan mengurangi penggunaan 'umm', 'ahh'."
            })

        app.logger.debug(f"Narration progress for user {current_user.get('username')}: Total sessions={total_sessions}, Avg score={average_score}")
        return jsonify({
            "status": "success",
            "data": {
                "total_sessions": total_sessions,
                "average_score": average_score,
                "history": history,
                "metrics": {
                    "expression": expression_score, # Menggunakan skor ekspresi yang baru dihitung (hanya gugup/normal)
                    "narrative": metrics.get('accuracy', 0),
                    "clarity": metrics.get('fluency', 0),
                    "confidence": metrics.get('overall_stt_confidence', 0),
                    "filler_words": metrics.get('filler_words', 0)
                },
                "weaknesses": weaknesses,
                "last_session": {
                    "timestamp": last_session.get('timestamp', '').isoformat() if last_session and isinstance(last_session.get('timestamp'), datetime) else None,
                    "overall_score": metrics.get('accuracy', 0)
                }
            }
        })

    except Exception as e:
        app.logger.error(f"Error getting narration progress for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

hrd_questions_list = list(hrd_question_details.keys())




@app.route("/api/hrd/questions", methods=["GET"])
@token_required
@require_api_key
def get_hrd_questions(current_user):
    app.logger.info(f"Get HRD questions endpoint hit by user: {current_user.get('username')}")
    try:
        if len(hrd_questions_list) < 5:
            selected_questions = random.sample(hrd_questions_list, len(hrd_questions_list))
        else:
            selected_questions = random.sample(hrd_questions_list, 5)
        app.logger.debug(f"Selected HRD questions: {selected_questions}")
        return jsonify({
            "status": "success",
            "questions": selected_questions
        })
    except Exception as e:
        app.logger.error(f"Error getting HRD questions for user {current_user.get('username')}: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/hrd/analyze_response", methods=["POST"])
@token_required
@require_api_key
def analyze_hrd_response(current_user):
    app.logger.info(f"Analyze HRD response endpoint hit by user: {current_user.get('username')}")
    data = request.get_json()

    required_fields = ["transcribed_text", "response_time", "question_index"]
    if not all(field in data for field in required_fields):
        app.logger.warning(f"Missing required fields for HRD response analysis: {data}")
        return jsonify({"status": "fail", "message": "Missing required fields"}), 400

    try:
        transcribed_text = data.get("transcribed_text", "").strip()
        response_time = data.get("response_time", 0)
        question_index = data.get("question_index", -1)

        current_question_text = ""
        if 0 <= question_index < len(hrd_questions_list):
            current_question_text = hrd_questions_list[question_index]
        else:
            app.logger.warning(f"Invalid question index {question_index} for HRD analysis.")
            return jsonify({
                "status": "fail",
                "message": "Invalid question index or missing question text.",
                "feedback": "Tidak dapat menemukan pertanyaan yang sesuai.",
                "expression": "confused",
                "score": 0
            }), 400

        score = 0
        feedback_message = ""
        expression = "neutral"

        app.logger.debug(f"HRD Analysis Input - Question: '{current_question_text}', Text: '{transcribed_text[:50]}...', Time: {response_time}s")

        if not transcribed_text or len(transcribed_text.split()) < 3:
            if response_time >= 29:
                feedback_message = "Waktu habis dan Anda tidak memberikan jawaban yang cukup."
                expression = "bored"
                score = 5
            else:
                feedback_message = "Jawaban Anda terlalu singkat. Mohon berikan jawaban yang lebih lengkap dan jelas."
                expression = "confused"
                score = 10

            app.logger.debug(f"HRD Analysis: Short/Empty answer. Score: {score}, Feedback: {feedback_message}")
            return jsonify({
                "status": "success",
                "feedback": feedback_message,
                "expression": expression,
                "score": score,
                "metrics": {"response_time": response_time, "word_count": len(transcribed_text.split()), "transcribed_text_received": transcribed_text}
            })

        words = word_tokenize(transcribed_text.lower())
        num_words = len(words)

        question_criteria = hrd_question_details.get(current_question_text, {})
        ideal_len = question_criteria.get("ideal_length", 15)
        keywords = question_criteria.get("keywords", [])

        base_score_length = 0
        if num_words < ideal_len * 0.4:
            feedback_message += "Jawaban Anda masih terlalu singkat. Coba elaborasi lebih lanjut. "
            base_score_length = 20
            expression = "confused"
        elif num_words < ideal_len * 0.7:
            feedback_message += "Jawaban Anda cukup baik, namun bisa lebih detail. "
            base_score_length = 40
            expression = "neutral"
        elif num_words < ideal_len * 1.5:
            feedback_message += "Panjang jawaban Anda sudah baik dan cukup komprehensif. "
            base_score_length = 60
            expression = "neutral"
        else:
            feedback_message += "Jawaban Anda sangat detail. Pastikan tetap fokus pada inti pertanyaan. "
            base_score_length = 50
            expression = "happy"

        score += base_score_length

        matched_keywords_count = 0
        if keywords:
            unique_answer_words = set(words)
            for kw in keywords:
                if kw in unique_answer_words:
                    matched_keywords_count += 1

            keyword_score_bonus = 0
            if matched_keywords_count == 0 and num_words > 5:
                feedback_message += "Namun, jawaban Anda sepertinya kurang menyentuh poin-poin kunci yang diharapkan. "
                score = max(15, score - 15)
                if expression == "happy": expression = "confused"
            elif matched_keywords_count > 0 and matched_keywords_count <= len(keywords) / 2:
                feedback_message += "Beberapa poin penting sudah Anda sebutkan. "
                keyword_score_bonus = 15
                if expression == "confused": expression = "neutral"
            elif matched_keywords_count > len(keywords) / 2:
                feedback_message += "Anda berhasil menyoroti banyak poin kunci dengan baik! "
                keyword_score_bonus = 30
                expression = "happy"

            score += keyword_score_bonus
        else:
            feedback_message += "Pertanyaan ini tidak memiliki kata kunci spesifik untuk dinilai. Penilaian berdasarkan kejelasan dan kelengkapan. "
            if score < 50 and num_words > ideal_len * 0.7 :
                score = max(score, 50)
                expression = "neutral" if expression == "confused" else expression

        if response_time < 3 and num_words < ideal_len * 0.5:
            feedback_message += "Anda menjawab sangat cepat, mungkin kurang dipertimbangkan. "
            score = max(10, score - 20)
            expression = "confused"

        score = min(max(0, score), 100)

        if expression == "neutral" or expression == "confused":
            if score >= 75:
                expression = "happy"
            elif score >= 50:
                expression = "neutral"
            else:
                expression = "confused"

        app.logger.debug(f"HRD Analysis Result - Score: {score}, Expression: {expression}, Feedback: {feedback_message.strip()}")
        return jsonify({
            "status": "success",
            "feedback": feedback_message.strip() if feedback_message else "Jawaban Anda telah diterima.",
            "expression": expression,
            "score": score,
            "metrics": {
                "response_time": response_time,
                "word_count": num_words,
                "transcribed_text_received": transcribed_text,
                "matched_keywords": matched_keywords_count if keywords else "N/A",
                "total_keywords_expected": len(keywords) if keywords else "N/A"
            }
        })

    except Exception as e:
        app.logger.error(f"Critical Error in analyze_hrd_response for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Terjadi kesalahan internal server: {str(e)}"}), 500

@app.route("/api/hrd/save_session_summary", methods=["POST"])
@token_required
@require_api_key
def save_hrd_session_summary(current_user):
    app.logger.info(f"Save HRD session summary endpoint hit by user: {current_user.get('username')}")
    data = request.get_json()

    try:
        if not all(key in data for key in ["overall_score", "responses_detail"]):
            app.logger.warning(f"Missing data for HRD session summary: {data}")
            return jsonify({"status": "fail", "message": "Missing overall_score or responses_detail"}), 400

        wawancara_doc = {
            "user_id": current_user['_id'],
            "username": current_user['username'],
            "timestamp": datetime.utcnow(),
            "type": "hrd_simulation",
            "results": {
                "overall_score": data.get("overall_score"),
                "individual_responses": data.get("responses_detail", [])
            },
            "metrics": {
                "average_score_hrd": data.get("overall_score"),
                "number_of_questions": len(data.get("responses_detail", [])),
                "total_duration_seconds": data.get("session_duration_seconds", 0)
            },
            "recording_duration": data.get("session_duration_seconds", 0),
            "feedback": data.get("final_feedback_summary", "Sesi HRD telah diselesaikan."),
            "difficulty": data.get("difficulty", "medium")
        }

        # --- PERBAIKAN DI SINI ---
        insert_result = wawancara_collection.insert_one(wawancara_doc) # Menyimpan hasil insert
        # --- AKHIR PERBAIKAN ---

        app.logger.info(f"HRD session summary saved successfully for user {current_user.get('username')}. ID: {insert_result.inserted_id}")
        return jsonify({
            "status": "success",
            "message": "HRD session summary saved successfully.",
            "inserted_id": str(insert_result.inserted_id)
            }), 201

    except Exception as e:
        app.logger.error(f"Error saving HRD session summary for user {current_user.get('username')}: {str(e)}")
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500

@app.route("/api/hrd/history", methods=["GET"])
@token_required
@require_api_key
def get_hrd_history_route(current_user):
    app.logger.info(f"Get HRD history endpoint hit by user: {current_user.get('username')}")
    try:
        if wawancara_collection is None:
            app.logger.error("wawancara_collection is None in get_hrd_history_route")
            return jsonify({"status": "fail", "message": "Database service unavailable"}), 503

        hrd_sessions = list(wawancara_collection.find(
            {"user_id": current_user['_id'], "type": "hrd_simulation"}
        ).sort("timestamp", -1).limit(10))

        formatted_sessions = []
        for session in hrd_sessions:
            session_data = {
                "_id": str(session['_id']),
                "timestamp": session['timestamp'].isoformat() if isinstance(session.get('timestamp'), datetime) else str(session.get('timestamp')),
                "overall_score": session.get('results', {}).get('overall_score', 0),
                "difficulty": session.get('difficulty', 'N/A'),
                "number_of_questions": session.get('metrics', {}).get('number_of_questions', 0),
                "session_duration_seconds": session.get('metrics', {}).get('total_duration_seconds', 0)
            }
            formatted_sessions.append(session_data)

        all_hrd_sessions_for_user = list(wawancara_collection.find(
            {"user_id": current_user['_id'], "type": "hrd_simulation"}
        ))
        total_hrd_sessions_count = len(all_hrd_sessions_for_user)

        total_hrd_score = sum(s.get('results', {}).get('overall_score', 0) for s in all_hrd_sessions_for_user)
        average_hrd_score = total_hrd_score / total_hrd_sessions_count if total_hrd_sessions_count > 0 else 0.0

        last_hrd_session_data = {}
        if formatted_sessions:
            last_hrd_session_data = {
                'timestamp': formatted_sessions[0]['timestamp'],
                'overall_score': formatted_sessions[0]['overall_score'],
                'difficulty': formatted_sessions[0]['difficulty'],
                'session_duration_seconds': formatted_sessions[0]['session_duration_seconds']
            }

        weaknesses_hrd = []
        if average_hrd_score < 60 and total_hrd_sessions_count > 0:
            weaknesses_hrd.append({
                "area": "Skor Keseluruhan",
                "description": "Rata-rata skor simulasi HRD Anda masih rendah. Perbanyak latihan.",
                "progress": average_hrd_score / 100,
                "suggestion": "Fokus pada kelengkapan dan relevansi jawaban."
            })
        if total_hrd_sessions_count == 0:
             weaknesses_hrd.append({
                "area": "Sesi Latihan",
                "description": "Anda belum melakukan sesi latihan HRD. Mulailah berlatih untuk meningkatkan performa Anda.",
                "progress": 0,
                "suggestion": "Mulai sesi HRD pertama Anda untuk mendapatkan evaluasi."
            })

        app.logger.debug(f"HRD history for user {current_user.get('username')}: Total sessions={total_hrd_sessions_count}, Avg score={average_hrd_score}")
        return jsonify({
            "status": "success",
            "data": {
                "total_sessions": total_hrd_sessions_count,
                "average_score": average_hrd_score,
                "history": formatted_sessions,
                "last_session": last_hrd_session_data,
                "metrics": {
                    "average_hrd_score": average_hrd_score,
                },
                "weaknesses": weaknesses_hrd
            }
        })
    except pymongo.errors.PyMongoError as e:
        app.logger.error(f"DB error getting HRD history for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": "Database error while fetching HRD history."}), 500
    except Exception as e:
        app.logger.error(f"Error getting HRD history for user {current_user.get('username')}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}), 500

# Admin routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = users_collection.find_one({"username": username})
        if user and user.get('is_admin', False) and bcrypt.check_password_hash(user['password'], password):
            session['username'] = user['username']
            session['is_admin'] = True
            flash(f'Welcome, Admin {user["username"]}!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials or not an admin', 'danger')

    return render_template('admin_login.html')

@app.route('/api/docs')
def api_docs():
    """API Documentation Page"""
    return render_template('api_docs.html')

@app.route('/admin/sessions')
@admin_required
@require_api_key
def admin_sessions():
    """View all interview sessions"""
    sessions = list(wawancara_collection.find().sort("timestamp", -1)) # Menggunakan wawancara_collection
    # Konversi ObjectId dan datetime untuk tampilan
    for s in sessions:
        s['_id'] = str(s['_id'])
        s['user_id'] = str(s['user_id']) # Pastikan user_id juga string
        s['timestamp'] = s['timestamp'].isoformat() if isinstance(s['timestamp'], datetime) else str(s['timestamp'])
    return render_template('admin_sessions.html', sessions=sessions)

@app.route('/admin/dashboard')
@admin_required
@require_api_key
def admin_dashboard():
    # Check for inactive users first
    check_inactive_users()

    # Get stats for dashboard
    user_count = users_collection.count_documents({})
    # Hitung sesi untuk hari ini, dari semua jenis
    today_sessions = wawancara_collection.count_documents({
        "timestamp": {
            "$gte": datetime.combine(datetime.today(), datetime.min.time())
        }
    })

    # Get recent activities (assuming a separate activity_log collection)
    # Anda perlu membuat koleksi 'activity_log' jika ingin fitur ini bekerja
    # Contoh: db.activity_log.insert_one({"action": "User registered", "user_id": ..., "time": datetime.utcnow()})
    recent_activities = []
    if "activity_log" in db.list_collection_names():
        recent_activities = list(db.activity_log.find().sort("time", -1).limit(10))
        for act in recent_activities:
            act['_id'] = str(act['_id'])
            act['time'] = act['time'].isoformat() if isinstance(act['time'], datetime) else str(act['time'])


    # Get all users data
    all_users = list(users_collection.find({}, {
        "_id": 1,
        "username": 1,
        "email": 1,
        "gender": 1,
        "occupation": 1,
        "created_at": 1,
        "is_active": 1,
        "last_login": 1,
        "is_admin": 1 # Tambahkan ini
    }).sort("created_at", -1))

    # Konversi ObjectId dan datetime untuk users
    for user in all_users:
        user['_id'] = str(user['_id'])
        user['created_at'] = user['created_at'].isoformat() if isinstance(user['created_at'], datetime) else str(user['created_at'])
        user['last_login'] = user['last_login'].isoformat() if isinstance(user['last_login'], datetime) else None

    return render_template('admin_dashboard.html',
                         user_count=user_count,
                         today_sessions=today_sessions,
                         recent_activities=recent_activities,
                         all_users=all_users)

@app.route('/admin/users/toggle-status/<user_id>', methods=['POST'])
@admin_required
@require_api_key
def toggle_user_status(user_id):
    try:
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('admin_dashboard'))

        # Mencegah admin menonaktifkan dirinya sendiri (opsional)
        if user.get('username') == session.get('username') and user.get('is_admin', False):
            flash('Admin tidak bisa menonaktifkan akunnya sendiri.', 'warning')
            return redirect(url_for('admin_dashboard'))

        new_status = not user.get('is_active', False)
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_active": new_status}}
        )

        flash(f'User status changed to {"Active" if new_status else "Inactive"} for {user.get("username")}', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('admin_login'))

# Website routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/features')
def features():
    return render_template('features.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route("/update_profile", methods=["PUT"])
@token_required
@require_api_key
def update_profile_route(current_user):
    app.logger.info(f"Update profile endpoint hit by user: {current_user.get('email')}")

    if users_collection is None:
        app.logger.error("users_collection is None in update_profile_route")
        return jsonify({"status": "fail", "message": "Database service unavailable"}), 503

    data = request.get_json()
    app.logger.debug(f"Received data for update_profile: {data}")

    if not data:
        return jsonify({"status": "fail", "message": "No data provided"}), 400

    username_new = data.get("username")
    gender_new = data.get("gender")
    occupation_new = data.get("occupation")

    update_fields = {}
    current_username_from_db = current_user.get("username")

    if username_new and username_new != current_username_from_db:
        if users_collection.find_one({"username": username_new, "_id": {"$ne": current_user["_id"]}}):
            app.logger.warning(f"Update profile failed: Username '{username_new}' already taken.")
            return jsonify({"status": "fail", "message": "Username already taken"}), 409
        update_fields["username"] = username_new

    if gender_new and gender_new != current_user.get("gender"):
        update_fields["gender"] = gender_new

    if occupation_new and occupation_new != current_user.get("occupation"):
        update_fields["occupation"] = occupation_new

    if not update_fields:
        app.logger.info("No changes detected or no updatable data provided for profile update.")
        return jsonify({"status": "info", "message": "No changes were made to the profile"}), 200

    try:
        result = users_collection.update_one(
            {"_id": current_user["_id"]},
            {"$set": update_fields}
        )

        if result.modified_count > 0:
            updated_user_data = users_collection.find_one(
                {"_id": current_user["_id"]},
                {"password": 0}
            )
            if updated_user_data:
                user_response = {
                    "id": str(updated_user_data["_id"]),
                    "email": updated_user_data["email"],
                    "username": updated_user_data.get("username", ""),
                    "gender": updated_user_data.get("gender", ""),
                    "occupation": updated_user_data.get("occupation", "")
                }
                app.logger.info(f"Profile updated successfully for user {current_user.get('email')}.")
                return jsonify({"status": "success", "message": "Profile updated successfully", "user": user_response}), 200
            else:
                app.logger.error(f"Failed to retrieve updated user data for user_id: {current_user['_id']}")
                return jsonify({"status": "fail", "message": "Profile updated, but failed to retrieve updated data"}), 500
        elif result.matched_count > 0 and result.modified_count == 0:
            app.logger.info(f"Profile update attempted for user {current_user.get('email')}, but no changes were made.")
            return jsonify({"status": "info", "message": "No changes were made to the profile"}), 200
        else:
            app.logger.warning(f"User not found during update attempt for user_id: {current_user['_id']}")
            return jsonify({"status": "fail", "message": "User not found or profile not updated"}), 404

    except pymongo.errors.PyMongoError as e:
        app.logger.error(f"DB error updating profile for user {current_user.get('email')}: {e}")
        return jsonify({"status": "error", "message": "Database error during profile update"}), 500
    except Exception as e:
        import traceback
        app.logger.error(f"Unexpected error updating profile for user {current_user.get('email')}: {e}\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}), 500

@app.route("/login_google", methods=["POST"])
@require_api_key
def login_google():
      app.logger.info("Google login endpoint hit.")
      data = request.get_json()
      token = data.get('id_token')

      if not token:
          app.logger.warning("Google ID token not found in request.")
          return jsonify({"status": "fail", "message": "ID token Google tidak ditemukan"}), 400

      try:
          idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID_WEB)

          user_email = idinfo.get('email')
          user_name_from_google = idinfo.get('name', '')

          if not user_email:
              app.logger.warning("Email not found in Google token.")
              return jsonify({"status": "fail", "message": "Email tidak ditemukan di token Google"}), 400

          user = users_collection.find_one({"email": user_email})
          is_new_user_flag = False

          if not user:
              random_password = bcrypt.generate_password_hash(str(uuid.uuid4())).decode('utf-8')
              username_parts = user_email.split('@')
              new_username_base = username_parts[0]
              temp_username = new_username_base
              counter = 1
              while users_collection.find_one({"username": temp_username}):
                  temp_username = f"{new_username_base}{counter}"
                  counter += 1
              final_username = user_name_from_google or temp_username

              new_user_data = {
                  "email": user_email,
                  "username": final_username,
                  "password": random_password,
                  "gender": "",
                  "occupation": "",
                  "created_at": datetime.utcnow(),
                  "last_login": datetime.utcnow(),
                  "is_active": True,
                  "login_provider": "google",
                  "is_admin": False
              }
              insert_result = users_collection.insert_one(new_user_data)
              user = users_collection.find_one({"_id": insert_result.inserted_id})
              is_new_user_flag = True

              if not user:
                  app.logger.error(f"Failed to create new user after Google verification for email: {user_email}")
                  return jsonify({"status": "fail", "message": "Gagal membuat pengguna baru setelah verifikasi Google."}), 500
              app.logger.info(f"New user created via Google login: {final_username}")
          else:
              users_collection.update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow(), "is_active": True}})
              app.logger.info(f"Existing user '{user.get('username')}' logged in via Google.")

          access_token = jwt.encode({
              'user_id': str(user['_id']),
              'email': user['email'],
              'exp': datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
          }, app.config['JWT_SECRET_KEY'], algorithm="HS256")

          refresh_token = jwt.encode({
              'user_id': str(user['_id']),
              'email': user['email'],
              'exp': datetime.utcnow() + app.config['JWT_REFRESH_TOKEN_EXPIRES']
          }, app.config['JWT_SECRET_KEY'], algorithm="HS256")

          return jsonify({
              "status": "success",
              "message": "Login dengan Google berhasil",
              "access_token": access_token,
              "refresh_token": refresh_token,
              "user": {
                  "id": str(user["_id"]),
                  "email": user["email"],
                  "username": user.get("username", ""),
                  "gender": user.get("gender", ""),
                  "occupation": user.get("occupation", ""),
              },
              "is_new_user": is_new_user_flag
          }), 200

      except ValueError as e:
          app.logger.error(f"Google ID token verification failed: {e}")
          return jsonify({"status": "fail", "message": f"Verifikasi token Google gagal: {e}"}), 401
      except Exception as e:
          app.logger.critical(f"Error during Google login: {e}")
          import traceback
          traceback.print_exc()
          return jsonify({"status": "error", "message": f"Terjadi kesalahan internal: {e}"}), 500

# --- FORGOT PASSWORD & RESET PASSWORD ENDPOINTS ---

@app.route("/forgot_password_request", methods=["POST"])
@require_api_key
def forgot_password_request():
    app.logger.info("Forgot password request endpoint hit.")
    data = request.get_json()
    email = data.get('email')

    if not email:
        app.logger.warning("Forgot password request: Email missing.")
        return jsonify({"status": "fail", "message": "Email is required"}), 400

    user = users_collection.find_one({"email": email})

    if not user:
        app.logger.info(f"Forgot password request for non-existent email: {email}")
        return jsonify({
            "status": "success",
            "message": "Jika email Anda terdaftar, tautan reset password akan dikirimkan. Cek folder spam jika tidak ditemukan."
        }), 200

    try:
        password_reset_tokens_collection.delete_many({"email": email})

        token = secrets.token_urlsafe(64)
        expires_at = datetime.utcnow() + timedelta(minutes=30)

        password_reset_tokens_collection.insert_one({
            "email": email,
            "token": token,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at
        })

        msg = Message(
            subject="Reset Kata Sandi Fluent Anda",
            recipients=[email],
            body=f"""Halo,

Anda telah meminta reset kata sandi untuk akun Fluent Anda.
Gunakan kode berikut di aplikasi Fluent Anda untuk mereset kata sandi Anda:

Kode Reset: {token}

Kode ini akan kedaluwarsa dalam 30 menit. Jika Anda tidak meminta reset kata sandi, abaikan email ini.

Terima kasih,
Tim Fluent
"""
        )
        mail.send(msg)
        app.logger.info(f"Password reset email sent to {email}")

        return jsonify({
            "status": "success",
            "message": "Jika email Anda terdaftar, instruksi reset password telah dikirimkan ke email Anda. Cek folder spam jika tidak ditemukan."
        }), 200

    except Exception as e:
        app.logger.error(f"Error sending password reset email to {email}: {e}")
        return jsonify({"status": "error", "message": "Terjadi kesalahan internal saat mengirim email reset. Mohon coba lagi nanti."}), 500


@app.route("/reset_password", methods=["POST"])
@require_api_key
def reset_password():
    app.logger.info("Reset password endpoint hit.")
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        app.logger.warning("Reset password request: Token or new password missing.")
        return jsonify({"status": "fail", "message": "Token and new password are required"}), 400

    reset_record = password_reset_tokens_collection.find_one({"token": token})

    if not reset_record:
        app.logger.warning(f"Reset password failed: Invalid or used token '{token}'.")
        return jsonify({"status": "fail", "message": "Token tidak valid atau sudah digunakan."}), 400

    if reset_record['expires_at'] < datetime.utcnow():
        password_reset_tokens_collection.delete_one({"_id": reset_record['_id']})
        app.logger.warning(f"Reset password failed: Expired token '{token}'.")
        return jsonify({"status": "fail", "message": "Token sudah kedaluwarsa. Mohon minta reset baru."}), 400

    user_email = reset_record['email']
    user = users_collection.find_one({"email": user_email})

    if not user:
        password_reset_tokens_collection.delete_one({"_id": reset_record['_id']})
        app.logger.error(f"User not found for valid reset token '{token}', email: {user_email}.")
        return jsonify({"status": "fail", "message": "Pengguna terkait token tidak ditemukan."}), 404

    # Update password
    hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    users_collection.update_one(
        {"_id": user['_id']},
        {"$set": {"password": hashed_password, "last_login": datetime.utcnow(), "is_active": True}} # Juga update last_login
    )

    # Hapus token reset yang sudah digunakan
    password_reset_tokens_collection.delete_one({"_id": reset_record['_id']})

    # --- BAGIAN BARU: Generate token akses dan refresh baru ---
    access_token = jwt.encode({
        'user_id': str(user['_id']),
        'email': user['email'],
        'exp': datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
    }, app.config['JWT_SECRET_KEY'], algorithm="HS256")

    refresh_token = jwt.encode({
        'user_id': str(user['_id']),
        'email': user['email'],
        'exp': datetime.utcnow() + app.config['JWT_REFRESH_TOKEN_EXPIRES']
    }, app.config['JWT_SECRET_KEY'], algorithm="HS256")
    # --------------------------------------------------------

    app.logger.info(f"Password successfully reset and user logged in: {user_email}")
    return jsonify({
        "status": "success",
        "message": "Kata sandi Anda berhasil direset. Anda telah otomatis login.", # Pesan diubah
        "access_token": access_token, # Sertakan token baru
        "refresh_token": refresh_token, # Sertakan token baru
        "user": { # Sertakan data user
            "id": str(user["_id"]),
            "email": user["email"],
            "username": user.get("username", ""),
            "gender": user.get("gender", ""),
            "occupation": user.get("occupation", "")
        }
    }), 200

# --- REST API ENDPOINTS UNTUK FITUR DISKUSI ---
@app.route("/api/chat/topics", methods=["POST"])
@token_required
@require_api_key
def create_chat_topic(current_user):
    app.logger.info(f"Create chat topic endpoint hit by user: {current_user.get('username')}")
    data = request.get_json()
    topic_name = data.get('name')

    if not topic_name or not topic_name.strip():
        app.logger.warning("Topic name is empty for creation.")
        return jsonify({"status": "fail", "message": "Nama topik tidak boleh kosong"}), 400
    
    topic_id = topic_name.lower().replace(' ', '_').replace('.', '').replace(',', '').strip()
    
    if topics_collection.find_one({"_id": topic_id}):
        app.logger.warning(f"Topic with ID '{topic_id}' already exists.")
        return jsonify({"status": "fail", "message": "Topik dengan nama ini sudah ada, coba nama lain"}), 409

    try:
        topic_data = {
            "_id": topic_id,
            "name": topic_name,
            "createdAt": datetime.utcnow() # NEW: Tambahkan field createdAt untuk TTL
        }
        topics_collection.insert_one(topic_data)
        app.logger.info(f"New chat topic '{topic_name}' created by {current_user['username']}.")
        return jsonify({
            "status": "success",
            "message": "Topik berhasil dibuat",
            "topic": {"id": topic_id, "name": topic_name}
        }), 201
    except Exception as e:
        app.logger.error(f"Error creating chat topic for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Terjadi kesalahan saat membuat topik: {str(e)}"}), 500


@app.route("/api/chat/topics", methods=["GET"])
@token_required
@require_api_key
def get_chat_topics(current_user):
    app.logger.info(f"Get chat topics endpoint hit by user: {current_user.get('username')}")
    try:
        topics = list(topics_collection.find({}, {"_id": 1, "name": 1}))
        # Tambahkan topik default jika belum ada
        if not topics_collection.find_one({"_id": "global_discussion"}):
            topics_collection.insert_one({"_id": "global_discussion", "name": "Global Discussion"})
            topics.append({"_id": "global_discussion", "name": "Global Discussion"})
        
        # Urutkan berdasarkan nama, default di paling atas
        topics.sort(key=lambda x: (x['_id'] != "global_discussion", x['name'].lower()))

        formatted_topics = [{"id": str(t['_id']), "name": t['name']} for t in topics]
        app.logger.debug(f"Retrieved {len(formatted_topics)} chat topics.")
        return jsonify({"status": "success", "topics": formatted_topics}), 200
    except Exception as e:
        app.logger.error(f"Error getting chat topics for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Failed to load topics: {str(e)}"}), 500

@app.route("/api/chat/send_message", methods=["POST"])
@token_required
@require_api_key
def send_chat_message(current_user):
    app.logger.info(f"Send chat message endpoint hit by user: {current_user.get('username')}")
    data = request.get_json()
    message_content = data.get('message')
    room_id = data.get('room_id', 'global_discussion')
    
    replied_to_message_id = data.get('replied_to_message_id')
    replied_to_message_content = data.get('replied_to_message_content')
    replied_to_sender_username = data.get('replied_to_sender_username')

    if not message_content:
        app.logger.warning("Chat message content is empty.")
        return jsonify({"status": "fail", "message": "Message content cannot be empty"}), 400

    message_data = {
        'sender_id': str(current_user['_id']), # Pastikan sender_id selalu string
        'sender_username': current_user['username'],
        'content': message_content,
        'timestamp': datetime.utcnow(),
        'room_id': room_id,
    }

    if replied_to_message_id:
        message_data['replied_to_message_id'] = replied_to_message_id
        message_data['replied_to_message_content'] = replied_to_message_content
        message_data['replied_to_sender_username'] = replied_to_sender_username

    try:
        result = messages_collection.insert_one(message_data)
        app.logger.debug(f"Chat: Message from {current_user['username']} to room {room_id} saved.")
        return jsonify({
            "status": "success",
            "message": "Message sent",
            "sent_message": {
                'id': str(result.inserted_id),
                'sender_id': str(current_user['_id']),
                'sender_username': current_user['username'],
                'content': message_content,
                'timestamp': datetime.utcnow().isoformat(),
                'room_id': room_id,
                'replied_to_message_id': replied_to_message_id,
                'replied_to_message_content': replied_to_message_content,
                'replied_to_sender_username': replied_to_sender_username,
            }
        }), 201
    except Exception as e:
        app.logger.error(f"Chat: Error saving message for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Failed to send message: {str(e)}"}), 500

@app.route("/api/chat/messages", methods=["GET"])
@token_required
@require_api_key
def get_chat_messages(current_user):
    app.logger.info(f"Get chat messages endpoint hit by user: {current_user.get('username')}")
    topic_id = request.args.get('topic_id', 'global_discussion')
    limit = int(request.args.get('limit', 50))

    query = {'room_id': topic_id}

    try:
        messages_cursor = messages_collection.find(query).sort('timestamp', 1).limit(limit)

        formatted_messages = []
        for msg in messages_cursor:
            formatted_messages.append({
                'id': str(msg['_id']),
                'sender_id': msg['sender_id'],
                'sender_username': msg['sender_username'],
                'content': msg['content'],
                'timestamp': msg['timestamp'].isoformat(),
                'room_id': msg['room_id'],
                'replied_to_message_id': msg.get('replied_to_message_id'),
                'replied_to_message_content': msg.get('replied_to_message_content'),
                'replied_to_sender_username': msg.get('replied_to_sender_username'),
            })

        app.logger.debug(f"Chat: Loaded {len(formatted_messages)} messages for topic {topic_id} for user {current_user.get('username')}.")
        return jsonify({"status": "success", "messages": formatted_messages}), 200
    except Exception as e:
        app.logger.error(f"Chat: Error loading messages for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Failed to load messages: {str(e)}"}), 500

@app.route("/api/chat/messages/<message_id>",methods=["DELETE"]) # message_id dari URL
@token_required
@require_api_key
def delete_chat_message(current_user, message_id):
    app.logger.info(f"Delete chat message endpoint hit for message {message_id} by user: {current_user.get('username')}")
    
    if not ObjectId.is_valid(message_id):
        app.logger.warning(f"Delete chat message failed: Invalid Message ID format '{message_id}'.")
        return jsonify({"status": "fail", "message": "Format ID Pesan tidak valid"}), 400

    try:
        message_obj_id = ObjectId(message_id)
        user_sender_id_str = str(current_user['_id']) # Konversi ObjectId user ke string

        app.logger.debug(f"Attempting to delete message_id: {message_obj_id} by user_id_str: {user_sender_id_str}")

        # Kueri untuk menghapus: cocokkan _id (sebagai ObjectId) DAN sender_id (sebagai string)
        result = messages_collection.delete_one({
            "_id": message_obj_id,
            "sender_id": user_sender_id_str
        })

        if result.deleted_count > 0:
            app.logger.info(f"Chat: Message {message_id} deleted successfully by {current_user['username']}")
            return jsonify({"status": "success", "message": "Pesan berhasil dihapus"}), 200
        else:
            message_found_but_not_owned = messages_collection.find_one({"_id": message_obj_id})
            if message_found_but_not_owned:
                app.logger.warning(f"User {current_user['username']} unauthorized to delete message {message_id}. Message owner: {message_found_but_not_owned.get('sender_id')}, Requester: {user_sender_id_str}")
                return jsonify({"status": "fail", "message": "Anda tidak diizinkan menghapus pesan ini"}), 403
            else:
                app.logger.warning(f"Chat: Message {message_id} not found for deletion.")
                return jsonify({"status": "fail", "message": "Pesan tidak ditemukan"}), 404

    except Exception as e:
        app.logger.error(f"Chat: Error deleting message {message_id} for user {current_user.get('username')}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Terjadi kesalahan saat menghapus pesan: {str(e)}"}), 500


# Admin routes for topics (NEW)
@app.route('/admin/topics', methods=['GET'])
@admin_required
@require_api_key
def admin_topics_list():
    """Admin view to list and manage topics."""
    topics = list(topics_collection.find().sort("name", 1))
    for t in topics:
        t['_id'] = str(t['_id']) # Ensure ID is string
    return render_template('admin_topics.html', topics=topics)

@app.route('/admin/topics/add', methods=['POST'])
@admin_required
@require_api_key
def admin_add_topic():
    """Admin endpoint to add a new topic."""
    topic_name = request.form.get('topic_name')
    if not topic_name or not topic_name.strip():
        flash('Nama topik tidak boleh kosong!', 'danger')
        return redirect(url_for('admin_topics_list'))
    
    topic_id = topic_name.lower().replace(' ', '_').replace('.', '').replace(',', '').strip()

    if topics_collection.find_one({"_id": topic_id}):
        flash(f"Topik '{topic_name}' sudah ada (ID: {topic_id}).", 'warning')
        return redirect(url_for('admin_topics_list'))

    try:
        topics_collection.insert_one({"_id": topic_id, "name": topic_name})
        flash(f"Topik '{topic_name}' berhasil ditambahkan!", 'success')
    except Exception as e:
        app.logger.error(f"Error adding topic: {e}")
        flash(f"Gagal menambahkan topik: {str(e)}", 'danger')

    return redirect(url_for('admin_topics_list'))

@app.route('/admin/topics/delete/<topic_id>', methods=['POST'])
@admin_required
@require_api_key
def admin_delete_topic(topic_id):
    """Admin endpoint to delete a topic."""
    if topic_id == "global_discussion":
        flash("Topik 'Global Discussion' tidak bisa dihapus!", 'danger')
        return redirect(url_for('admin_topics_list'))

    try:
        messages_collection.delete_many({"room_id": topic_id}) # Delete related messages
        
        result = topics_collection.delete_one({"_id": topic_id})
        if result.deleted_count > 0:
            flash(f"Topik '{topic_id}' dan pesannya berhasil dihapus!", 'success')
        else:
            flash(f"Topik '{topic_id}' tidak ditemukan!", 'warning')
    except Exception as e:
        app.logger.error(f"Error deleting topic: {e}")
        flash(f"Gagal menghapus topik: {str(e)}", 'danger')

    return redirect(url_for('admin_topics_list'))
# Run the App
# ... (Bagian __main__ di app.py)
if __name__ == "__main__":
    with app.app_context():
        # Tambahkan topik diskusi default saat startup jika belum ada
        # Catatan: Topik default ini tidak akan punya TTL jika tidak ada createdAt.
        # Jika ingin TTL berlaku untuknya, tambahkan createdAt di sini juga.
        if not topics_collection.find_one({"_id": "global_discussion"}):
            topics_collection.insert_one({"_id": "global_discussion", "name": "Global Discussion"})
            app.logger.info("Default topic 'Global Discussion' added to DB.")
        
        app.logger.info("Checking for inactive users on app startup...")
        check_inactive_users()
        app.logger.info("Inactive user check complete.")
    app.run(host="0.0.0.0", port=5000, debug=True)