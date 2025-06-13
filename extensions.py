# extensions.py
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_cors import CORS
from flask_login import LoginManager # <--- NEW
from database import get_collections # <--- NEW

bcrypt = Bcrypt()
mail = Mail()
cors = CORS()
login_manager = LoginManager() # <--- NEW

# Configure Flask-Login settings (optional, but good practice)
login_manager.login_view = 'web_auth_bp.web_login' # Redirect to this view if login_required fails
login_manager.login_message = "Harap login untuk mengakses halaman ini."
login_manager.login_message_category = "warning"

class User: # <--- NEW: User class for Flask-Login compatibility
    def __init__(self, user_data):
        self.user_data = user_data

    def is_authenticated(self):
        return True # Asumsi jika objek user ada, dia terautentikasi

    def is_active(self):
        return self.user_data.get('is_active', True) # Ambil dari DB, default true

    def is_anonymous(self):
        return False # Pengguna ini tidak anonim

    def get_id(self):
        # Flask-Login memerlukan ID pengguna sebagai string
        return str(self.user_data['_id'])

    @property
    def is_admin(self): # <--- NEW: Admin property
        return self.user_data.get('is_admin', False)

    # Anda bisa menambahkan properti lain untuk akses mudah
    @property
    def username(self):
        return self.user_data.get('username')

    @property
    def email(self):
        return self.user_data.get('email')


@login_manager.user_loader # <--- NEW: User loader for Flask-Login
def load_user(user_id):
    """
    Callback function that Flask-Login uses to reload the user object from the user ID stored in the session.
    """
    from bson import ObjectId # Import here to avoid circular dependency
    users_collection = get_collections()["users"]
    try:
        user_doc = users_collection.find_one({"_id": ObjectId(user_id)})
        if user_doc:
            return User(user_doc)
        return None
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error loading user {user_id}: {e}")
        return None


def init_extensions(app):
    """Initializes Flask extensions with the given app instance."""
    bcrypt.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app) # <--- NEW: Initialize Flask-Login
    # CORS is typically initialized with the app instance itself or a blueprint
    # app.py will handle CORS init directly.