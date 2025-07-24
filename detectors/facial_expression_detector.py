# detectors/facial_expression_detector.py
import cv2
import mediapipe as mp
import numpy as np
import logging
import os

logger = logging.getLogger(__name__)

# Inisialisasi MediaPipe FaceMesh sekali secara global untuk efisiensi
# Ini penting untuk performa dan menghindari error inisialisasi berulang
try:
    mp_face_mesh = mp.solutions.face_mesh
    _face_mesh_instance = mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5
    )
    logger.info("MediaPipe FaceMesh initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize MediaPipe FaceMesh: {e}")
    _face_mesh_instance = None

def _get_distance(p1, p2, image_shape):
    """Menghitung jarak Euclidean antara dua landmark dalam koordinat piksel."""
    if not p1 or not p2:
        return 0
    x1 = p1.x * image_shape[1]
    y1 = p1.y * image_shape[0]
    x2 = p2.x * image_shape[1]
    y2 = p2.y * image_shape[0]
    return np.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def detect_facial_expression(image_path: str) -> str:
    """
    Mendeteksi ekspresi wajah sederhana (senang, sedih, marah, terkejut, gugup, netral)
    berdasarkan landmark MediaPipe Face Mesh.
    CATATAN: Ini adalah pendekatan berbasis aturan dan tidak seakurat model ML khusus.
    """
    if not _face_mesh_instance:
        logger.error("FaceMesh instance is not available. Cannot perform detection.")
        return "tidak terdeteksi"

    if not os.path.exists(image_path):
        logger.warning(f"Image not found at {image_path}, cannot detect expression.")
        return "tidak terdeteksi"
        
    image = cv2.imread(image_path)
    if image is None:
        logger.warning(f"Could not read image at {image_path}")
        return "tidak terdeteksi"

    # Pastikan gambar dalam format RGB untuk MediaPipe
    try:
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = _face_mesh_instance.process(rgb_image)
    except Exception as e:
        logger.error(f"Error processing image with MediaPipe: {e}")
        return "tidak terdeteksi"
    
    if not results or not results.multi_face_landmarks:
        logger.debug("No face landmarks detected for expression analysis.")
        return "tidak terdeteksi"
    
    landmarks = results.multi_face_landmarks[0].landmark
    H, W, _ = image.shape

    # --- Ekstraksi Fitur Wajah ---
    
    # Landmark Mulut
    mouth_left_corner = landmarks[61]
    mouth_right_corner = landmarks[291]
    mouth_top = landmarks[13]
    mouth_bottom = landmarks[14]
    
    # Landmark Alis
    left_inner_brow = landmarks[107]
    right_inner_brow = landmarks[336]

    # Normalisasi dengan jarak antar mata untuk konsistensi ukuran wajah
    left_eye_outer = landmarks[133]
    right_eye_outer = landmarks[362]
    inter_eye_distance = _get_distance(left_eye_outer, right_eye_outer, image.shape)
    if inter_eye_distance == 0: inter_eye_distance = 1 # Hindari pembagian nol

    # Fitur Mulut
    mouth_height = _get_distance(mouth_top, mouth_bottom, image.shape)
    mouth_width = _get_distance(mouth_left_corner, mouth_right_corner, image.shape)
    mouth_aspect_ratio = mouth_height / (mouth_width + 1e-6)
    
    # Posisi sudut bibir relatif terhadap pusat bibir (untuk senyum/cemberut)
    mouth_corner_y_avg = (mouth_left_corner.y + mouth_right_corner.y) / 2
    mouth_center_y = (mouth_top.y + mouth_bottom.y) / 2
    mouth_corner_lift = mouth_center_y - mouth_corner_y_avg # Positif jika terangkat

    # Fitur Mata (Eye Aspect Ratio untuk deteksi terkejut)
    try:
        left_eye_vert_dist = _get_distance(landmarks[159], landmarks[145], image.shape)
        left_eye_horz_dist = _get_distance(landmarks[33], landmarks[133], image.shape)
        ear_left = left_eye_vert_dist / (left_eye_horz_dist + 1e-6)

        right_eye_vert_dist = _get_distance(landmarks[386], landmarks[374], image.shape)
        right_eye_horz_dist = _get_distance(landmarks[263], landmarks[362], image.shape)
        ear_right = right_eye_vert_dist / (right_eye_horz_dist + 1e-6)
        avg_ear = (ear_left + ear_right) / 2
    except (IndexError, TypeError):
        avg_ear = 0.0

    # Fitur Alis (untuk marah/sedih)
    left_brow_height = (landmarks[159].y - left_inner_brow.y) * H
    right_brow_height = (landmarks[386].y - right_inner_brow.y) * H
    normalized_brow_height = ((left_brow_height + right_brow_height) / 2) / (inter_eye_distance + 1e-6)

    # --- Logika Deteksi Berbasis Aturan ---
    
    # 1. Terkejut (Mata terbuka lebar, mulut terbuka)
    if avg_ear > 0.35 and mouth_aspect_ratio > 0.5:
        logger.debug(f"Detected: Terkejut (EAR: {avg_ear:.2f}, MAR: {mouth_aspect_ratio:.2f})")
        return "terkejut"

    # 2. Senang (Sudut bibir terangkat)
    if mouth_corner_lift > 0.01: # 0.01 adalah nilai y normalisasi
        logger.debug(f"Detected: Senang (Corner Lift: {mouth_corner_lift:.3f})")
        return "senang"
    
    # 3. Marah (Alis turun/berkerut)
    if normalized_brow_height < 3.0: # Nilai ini mungkin perlu disesuaikan
        logger.debug(f"Detected: Marah (Brow Height: {normalized_brow_height:.2f})")
        return "marah"

    # 4. Sedih (Sudut bibir turun)
    if mouth_corner_lift < -0.005:
        logger.debug(f"Detected: Sedih (Corner Lift: {mouth_corner_lift:.3f})")
        return "sedih"

    # 5. Gugup (Mulut sedikit terbuka, tapi tidak ada tanda ekspresi lain)
    if 0.15 < mouth_aspect_ratio < 0.4:
         logger.debug(f"Detected: Gugup (MAR: {mouth_aspect_ratio:.2f})")
         return "gugup"

    # 6. Netral (Default)
    logger.debug("Detected: Netral (No other cues matched)")
    return "netral"