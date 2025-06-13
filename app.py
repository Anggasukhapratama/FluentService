# app.py
from flask import Flask, render_template, redirect, url_for, session
import logging
from extensions import bcrypt, mail, cors, init_extensions, login_manager
import datetime
from config import JWT_SECRET_KEY, JWT_ACCESS_TOKEN_EXPIRES, JWT_REFRESH_TOKEN_EXPIRES, \
                   API_SECRET_KEY, GOOGLE_CLIENT_ID_WEB, MAIL_SERVER, MAIL_PORT, \
                   MAIL_USE_TLS, MAIL_USE_SSL, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER
from database import init_db, get_collections

# Import Blueprints
from routes.auth_routes import auth_bp
from routes.profile_routes import profile_bp
from routes.narration_routes import narration_bp
from routes.hrd_routes import hrd_bp
from routes.chat_routes import chat_bp
from routes.admin_routes import admin_bp
from routes.web_auth_routes import web_auth_bp
from routes.web_admin_routes import web_admin_bp

# Konfigurasi logging Flask
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask App
app = Flask(__name__)

# NEW: Configure a secret key for Flask sessions (required by Flask-Login)
app.config['SECRET_KEY'] = 'your_super_secret_key_for_flask_session' # GANTI INI DENGAN KEY YANG KUAT
app.config['SESSION_COOKIE_SECURE'] = True # Untuk HTTPS di produksi
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(days=30)

# Configure Flask App
app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = JWT_ACCESS_TOKEN_EXPIRES
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = JWT_REFRESH_TOKEN_EXPIRES
app.config['API_SECRET_KEY'] = API_SECRET_KEY
app.config['GOOGLE_CLIENT_ID_WEB'] = GOOGLE_CLIENT_ID_WEB

# Mailer configuration
app.config['MAIL_SERVER'] = MAIL_SERVER
app.config['MAIL_PORT'] = MAIL_PORT
app.config['MAIL_USE_TLS'] = MAIL_USE_TLS
app.config['MAIL_USE_SSL'] = MAIL_USE_SSL
app.config['MAIL_USERNAME'] = MAIL_USERNAME
app.config['MAIL_PASSWORD'] = MAIL_PASSWORD
app.config['MAIL_DEFAULT_SENDER'] = MAIL_DEFAULT_SENDER

# Initialize extensions
init_extensions(app) # Initializes bcrypt, mail, and login_manager
cors.init_app(app, resources={
    r"/api/*": {"origins": "*"},
    r"/*": {"origins": "*"}
}, headers=['Content-Type', 'Authorization', 'X-API-Key'])


# Register Blueprints
app.register_blueprint(auth_bp) # For Flutter API
app.register_blueprint(profile_bp)
app.register_blueprint(narration_bp)
app.register_blueprint(hrd_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(admin_bp) # For Flutter API
app.register_blueprint(web_auth_bp) # <--- NEW REGISTRATION FOR WEB AUTH
app.register_blueprint(web_admin_bp) # <--- NEW REGISTRATION FOR WEB ADMIN


# Landing Page / Root route
@app.route("/")
def home():
    # Cek jika sudah login via web session
    from flask_login import current_user # Import here to avoid circular import issues with extensions
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('web_admin_bp.admin_dashboard'))
        return render_template("user_home.html", username=current_user.username)
    
    # Jika belum login, tampilkan landing page
    return render_template("landing_page.html") # <--- UBAH DI SINI

if __name__ == "__main__":
    with app.app_context():
        # Ensure DB is initialized
        init_db()
        
        # Initialize DB collections (called again here to ensure collections are ready)
        topics_collection = get_collections()["topics"]
        users_collection = get_collections()["users"]

        # Create default topic if not exists
        if not topics_collection.find_one({"_id": "global_discussion"}):
            topics_collection.insert_one({"_id": "global_discussion", "name": "Global Discussion"})
            logger.info("Default topic 'Global Discussion' added to DB.")
        
        # --- OPTIONAL: CREATE A DEFAULT ADMIN USER IF NONE EXISTS ---
        if not users_collection.find_one({"is_admin": True}):
            from extensions import bcrypt # Make sure bcrypt is imported here or accessible
            admin_email = "admin@example.com"
            admin_password = "adminpassword"
            hashed_admin_password = bcrypt.generate_password_hash(admin_password).decode('utf-8')
            
            users_collection.insert_one({
                "email": admin_email,
                "username": "admin_web_user",
                "password": hashed_admin_password,
                "gender": "Other",
                "occupation": "Administrator",
                "created_at": datetime.datetime.utcnow(),
                "last_login": None,
                "is_active": True,
                "is_admin": True
            })
            logger.info(f"Default web admin user '{admin_email}' created. Password: '{admin_password}'")
        # -----------------------------------------------------------

    app.run(host="0.0.0.0", port=5000, debug=True)