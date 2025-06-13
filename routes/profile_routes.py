from flask import Blueprint, request, jsonify
from database import get_collections
from auth_decorators import token_required, require_api_key
import pymongo.errors
import logging
import datetime
from bson import ObjectId, errors

profile_bp = Blueprint('profile_bp', __name__)
logger = logging.getLogger(__name__)

# Ambil koleksi dari helper
collections = get_collections()
users_collection = collections["users"]  # ✅ inisialisasi dengan benar

# =========================================================================
# === PERBAIKAN UTAMA: Tambahkan inisialisasi untuk login_history_collection ===
login_history_collection = collections["login_history"] # <--- TAMBAHKAN BARIS INI
# Pastikan nama "login_history" sesuai dengan nama koleksi di MongoDB Anda.
# =========================================================================

@profile_bp.route('/update_profile', methods=['PUT'])
@token_required
def update_profile(current_user):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "fail", "message": "Tidak ada data yang dikirim"}), 400

        # Ambil _id dari current_user dan konversi ke ObjectId
        user_id_raw = current_user.get("_id")

        try:
            user_id = ObjectId(user_id_raw)
        except (TypeError, errors.InvalidId): # Tambahkan TypeError dan InvalidId
            return jsonify({"status": "fail", "message": "ID user tidak valid"}), 400

        # Siapkan field yang akan di-update
        update_fields = {}
        for field in ["username", "gender", "occupation"]:
            if field in data and data[field].strip():
                update_fields[field] = data[field].strip()

        if not update_fields:
            return jsonify({"status": "info", "message": "Tidak ada data yang diubah."}), 200

        # Lakukan update di MongoDB
        result = users_collection.update_one(
            {"_id": user_id},
            {"$set": update_fields}
        )

        if result.matched_count == 0:
            return jsonify({"status": "fail", "message": "User tidak ditemukan."}), 404

        if result.modified_count == 0:
            return jsonify({"status": "info", "message": "Tidak ada perubahan yang diterapkan."}), 200

        updated_user = users_collection.find_one({"_id": user_id}, {"password": 0})
        # Pastikan _id dikonversi ke string agar bisa di-JSON-kan
        if updated_user: # Pastikan user ditemukan sebelum mencoba mengakses _id
            updated_user["_id"] = str(updated_user["_id"])

        return jsonify({
            "status": "success",
            "message": "Profil berhasil diperbarui.",
            "user": updated_user
        }), 200

    except Exception as e:
        logger.exception("Update profile failed")
        return jsonify({
            "status": "fail",
            "message": f"Terjadi kesalahan saat update profil: {str(e)}"
        }), 500

# =========================================================================
# === PERBAIKAN ENDPOINT DAN RESPON get_login_history ===
@profile_bp.route('/users/login-history', methods=['GET'])
@token_required
def get_login_history(current_user):
    try:
        user_id_raw = current_user.get('_id')
        try:
            user_id = ObjectId(user_id_raw)
        except (TypeError, errors.InvalidId):
            logger.error(f"Invalid user ID for login history: {user_id_raw}")
            return jsonify({"status": "fail", "message": "ID user tidak valid"}), 400

        history_cursor = login_history_collection.find(
            {"user_id": user_id}
        ).sort("timestamp", -1).limit(5) # Ambil 5 riwayat terbaru

        result = []
        for item in history_cursor:
            timestamp_obj = item.get("timestamp")
            formatted_timestamp = "N/A"
            if isinstance(timestamp_obj, datetime.datetime):
                # =====================================================================
                # === PERBAIKAN PENTING: Format datetime ke ISO 8601 dengan 'Z' ===
                # Menggunakan timespec='milliseconds' untuk presisi, dan 'Z' untuk UTC
                formatted_timestamp = timestamp_obj.isoformat(timespec='milliseconds') + 'Z'
                # =====================================================================
            
            result.append({
                "timestamp": formatted_timestamp,
                "method": item.get("method"),
                "ip_address": item.get("ip_address", "N/A")
            })

        return jsonify({
            "status": "success",
            "data": result # Pastikan ini 'data' bukan 'history'
        }), 200

    except pymongo.errors.PyMongoError as e:
        logger.exception(f"MongoDB error in get_login_history for user {current_user.get('email')}")
        return jsonify({
            "status": "fail",
            "message": f"Kesalahan database: {str(e)}"
        }), 500
    except Exception as e:
        logger.exception(f"Unexpected error in get_login_history for user {current_user.get('email')}")
        return jsonify({
            "status": "fail",
            "message": f"Terjadi kesalahan internal server: {str(e)}"
        }), 500