from db import users_collection
from flask_bcrypt import Bcrypt
from bson.objectid import ObjectId

bcrypt = Bcrypt()

def register_user(email, username, password, gender, occupation):
    if users_collection.find_one({"username": username}):
        return {"status": "fail", "message": "Username already exists"}
    if users_collection.find_one({"email": email}):
        return {"status": "fail", "message": "Email already registered"}

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    user_data = {
        "email": email,
        "username": username,
        "password": hashed_password,
        "gender": gender,
        "occupation": occupation,
        "api_keys": []
    }
    result = users_collection.insert_one(user_data)
    return {
        "status": "success",
        "message": "User registered",
        "user_id": str(result.inserted_id)
    }

def login_user(username, password):
    user = users_collection.find_one({"username": username})
    if user and bcrypt.check_password_hash(user["password"], password):
        return {"status": "success", "message": "Login successful", "user": user}
    return {"status": "fail", "message": "Invalid credentials"}

def get_user_by_username(username):
    user = users_collection.find_one({"username": username})
    if user:
        user["_id"] = str(user["_id"])  # Convert ObjectId to string
    return user

def verify_api_key(user_id, api_key):
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        return False
    return api_key in user.get("api_keys", [])