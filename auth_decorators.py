# auth_decorators.py
from functools import wraps # <--- PASTIKAN INI ADA
from flask import request, jsonify, current_app
import jwt
from datetime import datetime
from database import get_collections
from bson import ObjectId

import logging
logger = logging.getLogger(__name__)

def get_user_by_id(user_id):
    """Helper function to get user by ObjectId from the users_collection"""
    users_collection = get_collections()["users"]
    try:
        # Convert user_id string to ObjectId if it's not already
        obj_id = ObjectId(user_id)
        return users_collection.find_one({"_id": obj_id})
    except Exception as e:
        logger.error(f"Error converting user_id to ObjectId or finding user: {e}")
        return None

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            logger.warning("API Key missing from request.")
            return jsonify({"status": "fail", "message": "API Key is missing"}), 401
        if api_key != current_app.config.get('API_SECRET_KEY'):
            logger.warning(f"Invalid API Key: {api_key}")
            return jsonify({"status": "fail", "message": "Invalid API Key"}), 401
        return f(*args, **kwargs)
    return decorated_function

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]

        if not token:
            logger.warning("Token missing from Authorization header.")
            return jsonify({"status": "fail", "message": "Token is missing"}), 401

        try:
            data = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            user_id = data['user_id']
            current_user = get_user_by_id(user_id)
            if not current_user:
                logger.warning(f"User not found for token user_id: {user_id}")
                return jsonify({"status": "fail", "message": "User not found"}), 404
            current_user['_id'] = str(current_user['_id']) # Ensure _id is string for serialization
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired.")
            return jsonify({"status": "fail", "message": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            logger.warning("Invalid token.")
            return jsonify({"status": "fail", "message": "Invalid token"}), 401
        except Exception as e:
            logger.error(f"Error during token decoding or user retrieval: {e}")
            return jsonify({"status": "error", "message": "An unexpected error occurred during token validation."}), 500

        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f): # <--- PASTIKAN DEKORATOR INI ADA PERSIS SEPERTI INI
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]

        if not token:
            logger.warning("Admin access denied: Token missing.")
            return jsonify({"status": "fail", "message": "Token is missing"}), 401

        try:
            data = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            user_id = data['user_id']
            current_user = get_user_by_id(user_id)

            if not current_user:
                logger.warning(f"Admin access denied: User not found for token user_id: {user_id}")
                return jsonify({"status": "fail", "message": "User not found"}), 404

            if not current_user.get('is_admin', False):
                logger.warning(f"Admin access denied for user: {current_user.get('username')}. Not an admin.")
                return jsonify({"status": "fail", "message": "Admin access required"}), 403

            current_user['_id'] = str(current_user['_id']) # Ensure _id is string for serialization

        except jwt.ExpiredSignatureError:
            logger.warning("Admin access denied: Token has expired.")
            return jsonify({"status": "fail", "message": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            logger.warning("Admin access denied: Invalid token.")
            return jsonify({"status": "fail", "message": "Invalid token"}), 401
        except Exception as e:
            logger.error(f"Error during admin token decoding or user retrieval: {e}")
            return jsonify({"status": "error", "message": "An unexpected error occurred during admin validation."}), 500

        return f(current_user, *args, **kwargs)
    return decorated_function