# database.py

from pymongo import MongoClient
from config import MONGO_URI
import logging

logger = logging.getLogger(__name__)

client = None
db = None
users_collection = None
wawancara_collection = None         # TETAP ADA untuk fitur 'wawancara' lama
interviews_collection = None        # NEW: Koleksi khusus untuk "Simulasi Interview AI"
sessions_collection = None          # Sepertinya tidak digunakan, bisa dihapus
login_attempts_collection = None
messages_collection = None
password_reset_tokens_collection = None
otp_tokens_collection = None
topics_collection = None            # Koleksi untuk topik diskusi
login_history_collection = None     # <--- TAMBAHKAN INI: Deklarasi global untuk koleksi riwayat login
interviews_collection = None

def init_db():
    """Initializes the MongoDB client and collections."""
    global client, db, users_collection, wawancara_collection, \
           interviews_collection, \
           sessions_collection, \
           login_attempts_collection, messages_collection, password_reset_tokens_collection, \
           otp_tokens_collection, topics_collection, \
           login_history_collection

    try:
        client = MongoClient(MONGO_URI)
        db = client["flutterauth"]

        users_collection = db["users"]
        wawancara_collection = db["wawancara"]          # TETAP: Menggunakan koleksi "wawancara"
        interviews_collection = db["interviews"]        # NEW: Menggunakan koleksi "interviews" untuk fitur baru
        sessions_collection = db["sessions"]
        login_attempts_collection = db["login_attempts"]
        messages_collection = db["messages"]
        password_reset_tokens_collection = db["password_reset_tokens"]
        otp_tokens_collection = db["otp_tokens"]
        topics_collection = db["topics"]
        login_history_collection = db["login_history"]

        logger.info("MongoDB connected and collections initialized.")
    except Exception as e:
        logger.critical(f"Failed to connect to MongoDB: {e}")
        raise

def get_db():
    """Returns the database object."""
    if db is None:
        init_db()
    return db

def get_collections():
    """Returns a dictionary of all collections."""
    if db is None:
        init_db()
    return {
        "users": users_collection,
        "wawancara": wawancara_collection,          # TETAP: Termasuk koleksi 'wawancara'
        "interviews": interviews_collection,        # NEW: Termasuk koleksi 'interviews'
        "sessions": sessions_collection,
        "login_attempts": login_attempts_collection,
        "messages": messages_collection,
        "password_reset_tokens": password_reset_tokens_collection,
        "otp_tokens": otp_tokens_collection,
        "topics": topics_collection,
        "login_history": login_history_collection # <--- TAMBAHKAN INI: Termasuk koleksi riwayat login
    }