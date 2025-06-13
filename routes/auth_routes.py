from flask import Blueprint, request, jsonify, current_app
from database import get_collections # Import get_collections
from extensions import bcrypt, mail
from auth_decorators import require_api_key
from datetime import datetime, timedelta
import jwt
import uuid
import secrets
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import pymongo.errors
import logging
from flask_mail import Message # <-- TAMBAHKAN INI

auth_bp = Blueprint('auth_bp', __name__)
logger = logging.getLogger(__name__)

# Access collections
def get_auth_collections():
    cols = get_collections()
    # =====================================================================================
    # === PERBAIKAN 1: Tambahkan 'login_history' ke daftar koleksi yang dikembalikan ===
    return cols["users"], cols["otp_tokens"], cols["login_attempts"], cols["password_reset_tokens"], cols["login_history"]
    # =====================================================================================

@auth_bp.route("/register", methods=["POST"])
@require_api_key
def register_with_otp():
    logger.info("Register with OTP endpoint hit.")
    users_collection, otp_tokens_collection, _, _, _ = get_auth_collections() # Sesuaikan unpacking
    data = request.get_json()
    required_fields = ["email", "username", "password", "gender", "occupation", "otp"]
    if not all(field in data for field in required_fields):
        logger.warning(f"Incomplete registration data with OTP: {data}")
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
            logger.warning(f"Registration failed: Invalid OTP for email '{email}'.")
            return jsonify({"status": "fail", "message": "Kode OTP tidak valid"}), 400

        if otp_record['expires_at'] < datetime.utcnow():
            otp_tokens_collection.delete_one({"_id": otp_record['_id']})
            logger.warning(f"Registration failed: Expired OTP for email '{email}'.")
            return jsonify({"status": "fail", "message": "Kode OTP sudah kedaluwarsa. Mohon minta kode baru."}), 400

        # 2. Cek duplikasi email/username lagi (penting untuk race conditions)
        if users_collection.find_one({"email": email}):
            logger.warning(f"Registration failed: Email '{email}' already exists AFTER OTP verification.")
            return jsonify({"status": "fail", "message": "Email sudah terdaftar"}), 409
        if users_collection.find_one({"username": username}):
            logger.warning(f"Registration failed: Username '{username}' already exists AFTER OTP verification.")
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

        logger.info(f"User '{username}' registered successfully with OTP verification.")
        return jsonify({"status": "success", "message": "User registered successfully"}), 201

    except pymongo.errors.PyMongoError as e:
        logger.error(f"MongoDB error during OTP registration: {e}")
        return jsonify({"status": "error", "message": "Database error during registration"}), 500
    except Exception as e:
        logger.error(f"Unexpected error during OTP registration: {e}")
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}), 500


@auth_bp.route("/request_otp_for_registration", methods=["POST"])
@require_api_key
def request_otp_for_registration():
    logger.info("Request OTP for registration endpoint hit.")
    users_collection, otp_tokens_collection, _, _, _ = get_auth_collections() # Sesuaikan unpacking
    data = request.get_json()
    email = data.get('email')
    username = data.get('username')

    if not email:
        logger.warning("OTP request: Email missing.")
        return jsonify({"status": "fail", "message": "Email is required"}), 400

    # Cek apakah email sudah terdaftar
    if users_collection.find_one({"email": email}):
        logger.warning(f"OTP request failed: Email '{email}' already exists.")
        return jsonify({"status": "fail", "message": "Email sudah terdaftar"}), 409
    # Cek apakah username sudah terdaftar
    if users_collection.find_one({"username": username}):
        logger.warning(f"OTP request failed: Username '{username}' already exists.")
        return jsonify({"status": "fail", "message": "Username sudah terdaftar"}), 409

    try:
        otp_tokens_collection.delete_many({"email": email})

        otp = str(secrets.randbelow(900000) + 100000) # Ensure 6 digits
        expires_at = datetime.utcnow() + timedelta(minutes=5)

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
        logger.info(f"Registration OTP sent to {email}")

        return jsonify({
            "status": "success",
            "message": "Kode verifikasi telah dikirimkan ke email Anda. Cek folder spam jika tidak ditemukan."
        }), 200

    except Exception as e:
        logger.error(f"Error sending registration OTP to {email}: {e}")
        return jsonify({"status": "error", "message": "Terjadi kesalahan internal saat mengirim kode verifikasi. Mohon coba lagi nanti."}), 500


@auth_bp.route("/login", methods=["POST"])
@require_api_key
def login():
    logger.info("Login endpoint hit.")
    # =====================================================================================
    # === PERBAIKAN 2: Tambahkan login_history_collection ke unpacking koleksi ===
    users_collection, _, login_attempts_collection, _, login_history_collection = get_auth_collections()
    # =====================================================================================
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        logger.warning("Login attempt with incomplete data.")
        return jsonify({"status": "fail", "message": "Email and password are required"}), 400

    email = data["email"]
    password = data["password"]

    attempt_record = login_attempts_collection.find_one({"email": email})

    if attempt_record and attempt_record.get('blocked_until') and attempt_record['blocked_until'] > datetime.utcnow():
        remaining_time = (attempt_record['blocked_until'] - datetime.utcnow()).total_seconds()
        logger.warning(f"Blocked login attempt for email: {email}. Remaining time: {int(remaining_time)}s")
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
        logger.warning(f"Invalid login attempt for email: {email}. Attempts: {attempts}")
        return jsonify({
            "status": "fail",
            "message": "Invalid email or password",
            "attempts": attempts,
            "remaining_attempts": remaining_attempts,
            "blocked": attempts >= 3
        }), 401

    login_attempts_collection.delete_one({"email": email})

    users_collection.update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow(), "is_active": True}})
    logger.info(f"User '{user.get('username')}' logged in successfully.")

    # =====================================================================================
    # === PERBAIKAN 3: Tambahkan penyimpanan riwayat login untuk login manual ===
    try:
        login_history_collection.insert_one({
            "user_id": user['_id'],
            "timestamp": datetime.utcnow(),
            "method": "email_password", # Atau "manual"
            "ip_address": request.remote_addr # Menyimpan IP address pengguna
        })
        logger.info(f"Login history saved for user (manual login): {user.get('email')}")
    except Exception as e:
        logger.error(f"Failed to save login history for user (manual login) {user.get('email')}: {e}")
    # =====================================================================================


    access_token = jwt.encode({
        'user_id': str(user['_id']),
        'email': user['email'],
        'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    }, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")

    refresh_token = jwt.encode({
        'user_id': str(user['_id']),
        'email': user['email'],
        'exp': datetime.utcnow() + current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
    }, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")

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

@auth_bp.route("/refresh", methods=["POST"])
@require_api_key
def refresh():
    logger.info("Refresh token endpoint hit.")
    users_collection, _, _, _, _ = get_auth_collections() # Sesuaikan unpacking
    refresh_token = request.json.get('refresh_token')
    if not refresh_token:
        logger.warning("Refresh token missing from request.")
        return jsonify({"status": "fail", "message": "Refresh token is missing"}), 401

    try:
        data = jwt.decode(refresh_token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
        user = users_collection.find_one({"email": data['email']})

        if not user:
            logger.warning(f"User not found for refresh token email: {data.get('email')}")
            return jsonify({"status": "fail", "message": "User not found"}), 404

        new_access_token = jwt.encode({
            'user_id': str(user['_id']),
            'email': user['email'],
            'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
        }, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")

        logger.info(f"Access token refreshed for user: {user.get('username')}")
        return jsonify({
            "status": "success",
            "access_token": new_access_token
        })
    except jwt.ExpiredSignatureError:
        logger.info("Refresh token has expired.")
        return jsonify({"status": "fail", "message": "Refresh token has expired"}), 401
    except jwt.InvalidTokenError:
        logger.error("Invalid refresh token.")
        return jsonify({"status": "fail", "message": "Invalid refresh token"}), 401
    except Exception as e:
        logger.critical(f"Unexpected error during token refresh: {str(e)}")
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}), 500

@auth_bp.route("/login_google", methods=["POST"])
@require_api_key
def login_google():
      logger.info("Google login endpoint hit.")
      # =====================================================================================
      # === PERBAIKAN 4: Tambahkan login_history_collection ke unpacking koleksi ===
      users_collection, _, _, _, login_history_collection = get_auth_collections()
      # =====================================================================================
      data = request.get_json()
      token = data.get('id_token')

      if not token:
          logger.warning("Google ID token not found in request.")
          return jsonify({"status": "fail", "message": "ID token Google tidak ditemukan"}), 400

      try:
          idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), current_app.config['GOOGLE_CLIENT_ID_WEB'])

          user_email = idinfo.get('email')
          user_name_from_google = idinfo.get('name', '')

          if not user_email:
              logger.warning("Email not found in Google token.")
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
                  logger.error(f"Failed to create new user after Google verification for email: {user_email}")
                  return jsonify({"status": "fail", "message": "Gagal membuat pengguna baru setelah verifikasi Google."}), 500
              logger.info(f"New user created via Google login: {final_username}")
          else:
              users_collection.update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow(), "is_active": True}})
              logger.info(f"Existing user '{user.get('username')}' logged in via Google.")

          # =====================================================================================
          # === PERBAIKAN 5: Tambahkan penyimpanan riwayat login untuk login Google ===
          try:
              login_history_collection.insert_one({
                  "user_id": user['_id'],
                  "timestamp": datetime.utcnow(),
                  "method": "google_sso",
                  "ip_address": request.remote_addr # Menyimpan IP address pengguna
              })
              logger.info(f"Login history saved for user (Google login): {user.get('email')}")
          except Exception as e:
              logger.error(f"Failed to save login history for user (Google login) {user.get('email')}: {e}")
          # =====================================================================================

          access_token = jwt.encode({
              'user_id': str(user['_id']),
              'email': user['email'],
              'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
          }, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")

          refresh_token = jwt.encode({
              'user_id': str(user['_id']),
              'email': user['email'],
              'exp': datetime.utcnow() + current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
          }, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")

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
          logger.error(f"Google ID token verification failed: {e}")
          return jsonify({"status": "fail", "message": f"Verifikasi token Google gagal: {e}"}), 401
      except Exception as e:
          logger.critical(f"Error during Google login: {e}")
          import traceback
          traceback.print_exc()
          return jsonify({"status": "error", "message": f"Terjadi kesalahan internal: {e}"}), 500


@auth_bp.route("/forgot_password_request", methods=["POST"])
@require_api_key
def forgot_password_request():
    logger.info("Forgot password request endpoint hit.")
    users_collection, _, _, password_reset_tokens_collection, _ = get_auth_collections() # Sesuaikan unpacking
    data = request.get_json()
    email = data.get('email')

    if not email:
        logger.warning("Forgot password request: Email missing.")
        return jsonify({"status": "fail", "message": "Email is required"}), 400

    user = users_collection.find_one({"email": email})

    if not user:
        logger.info(f"Forgot password request for non-existent email: {email}")
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
        logger.info(f"Password reset email sent to {email}")

        return jsonify({
            "status": "success",
            "message": "Jika email Anda terdaftar, instruksi reset password telah dikirimkan ke email Anda. Cek folder spam jika tidak ditemukan."
        }), 200

    except Exception as e:
        logger.error(f"Error sending password reset email to {email}: {e}")
        return jsonify({"status": "error", "message": "Terjadi kesalahan internal saat mengirim email reset. Mohon coba lagi nanti."}), 500


@auth_bp.route("/reset_password", methods=["POST"])
@require_api_key
def reset_password():
    logger.info("Reset password endpoint hit.")
    # =====================================================================================
    # === PERBAIKAN 6: Tambahkan login_history_collection ke unpacking koleksi ===
    users_collection, _, _, password_reset_tokens_collection, login_history_collection = get_auth_collections()
    # =====================================================================================
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        logger.warning("Reset password request: Token or new password missing.")
        return jsonify({"status": "fail", "message": "Token and new password are required"}), 400

    reset_record = password_reset_tokens_collection.find_one({"token": token})

    if not reset_record:
        logger.warning(f"Reset password failed: Invalid or used token '{token}'.")
        return jsonify({"status": "fail", "message": "Token tidak valid atau sudah digunakan."}), 400

    if reset_record['expires_at'] < datetime.utcnow():
        password_reset_tokens_collection.delete_one({"_id": reset_record['_id']})
        logger.warning(f"Reset password failed: Expired token '{token}'.")
        return jsonify({"status": "fail", "message": "Token sudah kedaluwarsa. Mohon minta reset baru."}), 400

    user_email = reset_record['email']
    user = users_collection.find_one({"email": user_email})

    if not user:
        password_reset_tokens_collection.delete_one({"_id": reset_record['_id']})
        logger.error(f"User not found for valid reset token '{token}', email: {user_email}.")
        return jsonify({"status": "fail", "message": "Pengguna terkait token tidak ditemukan."}), 404

    hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    users_collection.update_one(
        {"_id": user['_id']},
        {"$set": {"password": hashed_password, "last_login": datetime.utcnow(), "is_active": True}}
    )

    password_reset_tokens_collection.delete_one({"_id": reset_record['_id']})

    # =====================================================================================
    # === PERBAIKAN 7: Tambahkan penyimpanan riwayat login untuk reset password ===
    try:
        login_history_collection.insert_one({
            "user_id": user['_id'],
            "timestamp": datetime.utcnow(),
            "method": "password_reset",
            "ip_address": request.remote_addr # Menyimpan IP address pengguna
        })
        logger.info(f"Login history saved for user (password reset): {user.get('email')}")
    except Exception as e:
        logger.error(f"Failed to save login history for user (password reset) {user.get('email')}: {e}")
    # =====================================================================================

    access_token = jwt.encode({
        'user_id': str(user['_id']),
        'email': user['email'],
        'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    }, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")

    refresh_token = jwt.encode({
        'user_id': str(user['_id']),
        'email': user['email'],
        'exp': datetime.utcnow() + current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
    }, current_app.config['JWT_SECRET_KEY'], algorithm="HS256")

    logger.info(f"Password successfully reset and user logged in: {user_email}")
    return jsonify({
        "status": "success",
        "message": "Kata sandi Anda berhasil direset. Anda telah otomatis login.",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "username": user.get("username", ""),
            "gender": user.get("gender", ""),
            "occupation": user.get("occupation", "")
        }
    }), 200