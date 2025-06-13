import logging

logger = logging.getLogger(__name__)

def analyze_audio(audio_data):
    """Mock audio analysis function"""
    # In a real application, this would integrate with a speech-to-text API
    # and perform more sophisticated analysis.
    logger.debug("Mock audio analysis performed.")
    return {
        'text': "Ini adalah contoh transkripsi",
        'confidence': 0.85,
        'filler_words': 3,
        'speech_rate': 120
    }

def generate_feedback(analysis):
    """Generate feedback based on analysis"""
    # In a real application, this would be more elaborate
    if analysis['confidence'] < 0.5:
        return "Jawaban kurang jelas, coba lebih percaya diri"
    elif analysis['filler_words'] > 5:
        return "Terlalu banyak kata pengisi 'umm', 'ahh'"
    logger.debug("Mock feedback generated.")
    return "Jawaban cukup baik"

def get_user_by_username(username, users_collection):
    """Utility function to get user by username from the users_collection"""
    return users_collection.find_one({"username": username})
