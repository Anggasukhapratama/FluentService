import cv2
import mediapipe as mp
import numpy as np

# Inisialisasi MediaPipe Face Mesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1,
                                   min_detection_confidence=0.5, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# Landmark IDs untuk mata (contoh, perlu disesuaikan dengan dokumentasi MediaPipe untuk presisi)
# Ini adalah landmark mata standar, perlu disesuaikan untuk kelopak mata atas/bawah yang lebih spesifik
# Untuk EAR, biasanya pakai 6 titik: P1, P2, P3, P4, P5, P6
# P1: (outer corner eye), P2:(inner corner eye), P3, P4 (upper eyelid), P5, P6 (lower eyelid)
# Contoh (ini tidak akurat, Anda harus mencari landmark ID yang benar dari MP Face Mesh)
# Landmark mata kiri dan kanan (perlu dicari ID yang tepat dari dokumentasi MediaPipe)
# Contoh saja:
LEFT_EYE_LANDMARKS = [
    33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246 # Ini adalah contoh yang lebih komprehensif, tapi untuk EAR biasanya cukup 6
]
RIGHT_EYE_LANDMARKS = [
    362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398 # Ini adalah contoh yang lebih komprehensif
]

# Ambil 6 titik kunci untuk EAR (ini hanya placeholder, cari ID landmark yang TEPAT!)
# P1 (outermost), P2 (innermost) P3, P4 (upper lid) P5, P6 (lower lid)
# Contoh untuk mata kiri:
L_EYE_P1 = 33
L_EYE_P2 = 133
L_EYE_P3 = 159
L_EYE_P4 = 145
L_EYE_P5 = 153
L_EYE_P6 = 154

# Contoh untuk mata kanan:
R_EYE_P1 = 362
R_EYE_P2 = 263
R_EYE_P3 = 386
R_EYE_P4 = 374
R_EYE_P5 = 382
R_EYE_P6 = 381

def calculate_ear(eye_landmarks, results_landmarks, img_w, img_h):
    # Dapatkan koordinat x,y dari landmark
    # Pastikan landmark_ids sesuai dengan P1-P6 untuk EAR
    p1 = results_landmarks.landmark[eye_landmarks[0]]
    p2 = results_landmarks.landmark[eye_landmarks[1]]
    p3 = results_landmarks.landmark[eye_landmarks[2]]
    p4 = results_landmarks.landmark[eye_landmarks[3]]
    p5 = results_landmarks.landmark[eye_landmarks[4]]
    p6 = results_landmarks.landmark[eye_landmarks[5]]

    # Konversi ke pixel
    p1 = np.array([p1.x * img_w, p1.y * img_h])
    p2 = np.array([p2.x * img_w, p2.y * img_h])
    p3 = np.array([p3.x * img_w, p3.y * img_h])
    p4 = np.array([p4.x * img_w, p4.y * img_h])
    p5 = np.array([p5.x * img_w, p5.y * img_h])
    p6 = np.array([p6.x * img_w, p6.y * img_h])

    # Hitung jarak Euclidean
    A = np.linalg.norm(p6 - p2) # Jarak vertikal dari P6 ke P2
    B = np.linalg.norm(p3 - p5) # Jarak vertikal dari P3 ke P5
    C = np.linalg.norm(p1 - p4) # Jarak horizontal dari P1 ke P4 (sudut luar ke sudut dalam)

    ear = (A + B) / (2.0 * C)
    return ear

cap = cv2.VideoCapture(0)

# Ambang batas eksperimental untuk deteksi asimetri EAR
# Ini sangat sensitif dan perlu diuji!
EAR_THRESHOLD_DIFFERENCE = 0.15 # Jika perbedaan EAR > ini saat mata tertutup

while cap.isOpened():
    success, image = cap.read()
    if not success:
        print("Ignoring empty camera frame.")
        continue

    image.flags.writeable = False
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(image)

    image.flags.writeable = True
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    if results.multi_face_landmarks:
        for face_landmarks in results.multi_face_landmarks:
            # Gambar landmark (opsional, untuk visualisasi)
            mp_drawing.draw_landmarks(
                image,
                face_landmarks,
                mp_face_mesh.FACEMESH_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style())
            mp_drawing.draw_landmarks(
                image,
                face_landmarks,
                mp_face_mesh.FACEMESH_CONTOURS,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_contours_style())
            mp_drawing.draw_landmarks(
                image,
                face_landmarks,
                mp_face_mesh.FACEMESH_IRISES,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_iris_connections_style())

            img_h, img_w, _ = image.shape

            # Hitung EAR untuk mata kiri (pastikan landmark ID yang benar)
            # Anda perlu mencari 6 landmark ID yang tepat dari dokumentasi MediaPipe untuk mata kiri & kanan
            # Contoh (ini adalah contoh saja, bukan ID yang akurat)
            # Untuk demo, saya akan menggunakan koordinat dummy atau ambil dari landmark_list untuk demonstrasi konsep
            try:
                # Ini adalah *contoh* daftar landmark untuk EAR, Anda harus mencari ID yang tepat dari MediaPipe
                # Landmakr mata MediaPipe seringkali tidak langsung memberi 6 titik yang ideal untuk EAR
                # Anda mungkin perlu memilih titik-titik kelopak mata atas/bawah secara manual
                # Atau menggunakan libraries seperti dlib yang sudah punya model 68 landmark
                
                # Sebagai contoh, saya akan mengambil beberapa titik umum untuk demonstrasi saja
                # Ini TIDAK AKURAT untuk EAR sebenarnya, hanya untuk mengisi contoh
                # Untuk EAR yang benar, Anda butuh titik-titik spesifik di kelopak mata atas dan bawah
                
                # Titik sudut mata:
                left_eye_outer = face_landmarks.landmark[33]
                left_eye_inner = face_landmarks.landmark[133]
                right_eye_outer = face_landmarks.landmark[362]
                right_eye_inner = face_landmarks.landmark[263]

                # Titik kelopak mata (ini adalah perkiraan, bukan titik EAR sesungguhnya dari MP)
                # Anda perlu mencari titik-titik kelopak mata atas/bawah yang akurat dari MP
                left_eye_top1 = face_landmarks.landmark[159] # Contoh
                left_eye_top2 = face_landmarks.landmark[145] # Contoh
                left_eye_bottom1 = face_landmarks.landmark[153] # Contoh
                left_eye_bottom2 = face_landmarks.landmark[154] # Contoh

                right_eye_top1 = face_landmarks.landmark[386] # Contoh
                right_eye_top2 = face_landmarks.landmark[374] # Contoh
                right_eye_bottom1 = face_landmarks.landmark[382] # Contoh
                right_eye_bottom2 = face_landmarks.landmark[381] # Contoh

                # Pastikan Anda memiliki 6 titik untuk fungsi calculate_ear yang benar
                # Berikut adalah contoh set titik yang bisa digunakan, namun perlu dicek di dokumentasi MP
                # Saya akan membuat dummy points untuk demonstrasi
                
                # Fungsi calculate_ear butuh 6 titik (x,y)
                # Contoh: [[x1,y1],[x2,y2],...]
                # Untuk mengimplementasikan EAR, Anda perlu mengidentifikasi 6 landmark untuk setiap mata.
                # MediaPipe Face Mesh memiliki banyak landmark di sekitar mata.
                # Anda bisa menggunakan landmark ini:
                # Kiri: [130, 243, 144, 160, 158, 153] (inner, outer, top, bottom-outer, bottom-inner) - ini hanya contoh!
                # Kanan: [359, 463, 373, 387, 385, 380]

                # Sebagai contoh, kita akan menghitung jarak vertikal antara titik atas dan bawah kelopak mata
                # ini BUKAN EAR, tapi indikator pembukaan mata
                
                # Untuk mata kiri
                lp_top = face_landmarks.landmark[159] # Contoh titik atas
                lp_bottom = face_landmarks.landmark[154] # Contoh titik bawah
                left_eye_vertical_dist = np.linalg.norm(np.array([lp_top.x, lp_top.y]) - np.array([lp_bottom.x, lp_bottom.y])) * img_h
                
                # Untuk mata kanan
                rp_top = face_landmarks.landmark[386] # Contoh titik atas
                rp_bottom = face_landmarks.landmark[381] # Contoh titik bawah
                right_eye_vertical_dist = np.linalg.norm(np.array([rp_top.x, rp_top.y]) - np.array([rp_bottom.x, rp_bottom.y])) * img_h

                ear_left = left_eye_vertical_dist # ini bukan EAR, hanya jarak vertikal
                ear_right = right_eye_vertical_dist # ini bukan EAR, hanya jarak vertikal

                # Cek asimetri
                asymmetry_detected = False
                if abs(ear_left - ear_right) > EAR_THRESHOLD_DIFFERENCE * img_h: # Normalisasi ambang batas
                    if ear_left > ear_right and ear_left > (0.5 * img_h): # Mata kiri lebih terbuka saat diminta menutup
                        cv2.putText(image, "Potensi Bell's Palsy Kiri (Mata)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)
                        asymmetry_detected = True
                    elif ear_right > ear_left and ear_right > (0.5 * img_h): # Mata kanan lebih terbuka
                        cv2.putText(image, "Potensi Bell's Palsy Kanan (Mata)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)
                        asymmetry_detected = True
                
                if not asymmetry_detected:
                    cv2.putText(image, "Normal", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

            except Exception as e:
                cv2.putText(image, f"Error calculating: {e}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
                pass # Lanjutkan jika ada error landmark

    cv2.imshow('MediaPipe Bell''s Palsy Detector (Rule-Based)', image)
    if cv2.waitKey(5) & 0xFF == 27:
        break

face_mesh.close()
cap.release()
cv2.destroyAllWindows()