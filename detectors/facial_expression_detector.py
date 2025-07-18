import os
import cv2
import mediapipe as mp
import numpy as np
import logging

logger = logging.getLogger(__name__)

mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# Inisialisasi MediaPipe FaceMesh sekali secara global
# Ini adalah kunci perbaikan untuk error "Packet timestamp mismatch"
_face_mesh_instance = mp_face_mesh.FaceMesh(
    static_image_mode=True,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5
)

def _get_distance(p1, p2, image_shape):
    """Calculate Euclidean distance between two landmarks in pixel coordinates."""
    x1 = p1.x * image_shape[1]
    y1 = p1.y * image_shape[0]
    x2 = p2.x * image_shape[1]
    y2 = p2.y * image_shape[0]
    return np.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def detect_facial_expression(image_path):
    """
    Detects a simplified facial expression (happy, sad, angry, surprised, nervous, neutral)
    based on MediaPipe Face Mesh landmarks.
    NOTE: This is a rule-based approximation and not as accurate as ML models.
    """
    image = cv2.imread(image_path)
    if image is None:
        logger.warning(f"Image not found at {image_path}")
        return "tidak terdeteksi"

    H, W, _ = image.shape
    
    # Gunakan instance global MediaPipe
    # Pastikan gambar dalam format RGB untuk MediaPipe
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = _face_mesh_instance.process(rgb_image)
    
    if not results or not results.multi_face_landmarks:
        logger.debug("No face landmarks detected for expression analysis.")
        return "tidak terdeteksi"
    
    landmarks = results.multi_face_landmarks[0].landmark

    # Mouth landmarks
    mouth_left_corner = landmarks[61]
    mouth_right_corner = landmarks[291]
    mouth_top = landmarks[13]
    mouth_bottom = landmarks[14]
    
    # Eye landmarks (for blinking/surprise) - these are not used in original logic, but are good to keep
    # left_eyelid_top = landmarks[159]
    # left_eyelid_bottom = landmarks[145]
    # right_eyelid_top = landmarks[386]
    # right_eyelid_bottom = landmarks[374]

    # Eyebrow landmarks (for anger/sadness)
    left_inner_brow = landmarks[107]
    right_inner_brow = landmarks[336]
    left_outer_brow = landmarks[66]
    right_outer_brow = landmarks[296]

    # Calculate distances
    mouth_height = _get_distance(mouth_top, mouth_bottom, image.shape)
    mouth_width = _get_distance(mouth_left_corner, mouth_right_corner, image.shape)
    
    # Normalize mouth height by face size (e.g., inter-eye distance)
    left_eye_outer = landmarks[133]
    right_eye_outer = landmarks[362]
    inter_eye_distance = _get_distance(left_eye_outer, right_eye_outer, image.shape)
    
    # Avoid division by zero
    mouth_aspect_ratio = mouth_height / (mouth_width + 1e-6)
    normalized_mouth_height = mouth_height / (inter_eye_distance + 1e-6)

    # Eye Aspect Ratio (EAR) for blinking/surprise
    try:
        left_eye_vert_dist = _get_distance(landmarks[159], landmarks[145], image.shape)
        left_eye_horz_dist = _get_distance(landmarks[33], landmarks[133], image.shape)
        ear_left = left_eye_vert_dist / (left_eye_horz_dist + 1e-6)

        right_eye_vert_dist = _get_distance(landmarks[386], landmarks[374], image.shape)
        right_eye_horz_dist = _get_distance(landmarks[263], landmarks[362], image.shape)
        ear_right = right_eye_vert_dist / (right_eye_horz_dist + 1e-6)
        avg_ear = (ear_left + ear_right) / 2
    except IndexError:
        logger.warning("Could not find all eye landmarks for EAR calculation. Skipping EAR-based detection.")
        avg_ear = 0.0 # Default to 0 if landmarks are missing

    # Eyebrow movement relative to eyes
    left_eye_mid_y = (landmarks[159].y + landmarks[145].y) / 2
    left_brow_mid_y = (landmarks[107].y + landmarks[66].y) / 2
    left_brow_raise = left_eye_mid_y - left_brow_mid_y

    right_eye_mid_y = (landmarks[386].y + landmarks[374].y) / 2
    right_brow_mid_y = (landmarks[336].y + landmarks[296].y) / 2
    right_brow_raise = right_eye_mid_y - right_brow_mid_y

    avg_brow_raise_normalized = (left_brow_raise + right_brow_raise) / (2 * (inter_eye_distance / H) + 1e-6)

    # --- Rule-based Expression Detection ---

    is_smiling_cues = False
    mouth_corner_y_avg = (landmarks[61].y + landmarks[291].y) / 2
    mouth_center_y = (landmarks[13].y + landmarks[14].y) / 2
    
    if (mouth_corner_y_avg < mouth_center_y - 0.01) and mouth_aspect_ratio > 0.3:
        is_smiling_cues = True

    if is_smiling_cues and normalized_mouth_height > 0.03:
        logger.debug("Detected: Happy (Smile - wide and upward corners)")
        return "senang"
    elif is_smiling_cues and normalized_mouth_height <= 0.03:
        logger.debug("Detected: Happy (Subtle Smile - upward corners, closed mouth)")
        return "senang"

    if avg_ear > 0.35 and normalized_mouth_height > 0.06:
        logger.debug("Detected: Terkejut (Surprised)")
        return "terkejut"

    if avg_brow_raise_normalized < -0.015 and normalized_mouth_height < 0.04: 
        logger.debug("Detected: Marah (Angry - lowered brows, closed mouth)")
        return "marah"
    
    if (mouth_corner_y_avg > mouth_center_y + 0.005) and normalized_mouth_height < 0.04:
        logger.debug("Detected: Sedih (Sad - downward mouth corners)")
        return "sedih"

    if normalized_mouth_height > 0.015 and normalized_mouth_height < 0.05 and not is_smiling_cues:
        logger.debug("Detected: Gugup (Nervous - slightly open mouth)")
        return "gugup"

    logger.debug("Detected: Netral (Neutral)")
    return "netral" # Default if no strong expression detected

# --- Contoh penggunaan (untuk pengujian):
if __name__ == '__main__':
    # Pastikan Anda memiliki folder 'test_images' dan gambar di dalamnya
    # Contoh: create dummy images for testing (optional)
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(dummy_img, "TEST", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    cv2.imwrite("test_image.jpg", dummy_img)

    print("Testing Facial Expression Detector:")
    expressions = [
        "test_images/happy.jpg", 
        "test_images/sad.jpg",
        "test_images/angry.jpg",
        "test_images/surprised.jpg",
        "test_images/gugup_example.jpg", 
        "test_images/neutral.jpg",
        "test_image.jpg" 
    ]
    
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

    for img_path in expressions:
        if os.path.exists(img_path):
            result = detect_facial_expression(img_path)
            print(f"Image: {img_path}, Detected Expression: {result}")
        else:
            print(f"Warning: {img_path} not found. Skipping.")

    if os.path.exists("test_image.jpg"):
        os.remove("test_image.jpg")
    
    # Penting: Tutup instance MediaPipe setelah selesai (ini hanya untuk skrip pengujian)
    _face_mesh_instance.close()