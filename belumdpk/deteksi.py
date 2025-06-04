import cv2
import mediapipe as mp
import math

# Fungsi untuk hitung jarak
def distance(p1, p2): 
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)

# Inisialisasi Face Mesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True)
mp_drawing = mp.solutions.drawing_utils

# Buka Webcam
cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # Preprocess
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)

    label = ""

    if results.multi_face_landmarks:
        for landmarks in results.multi_face_landmarks:
            # Ambil titik-titik bibir untuk analisis
            left_lip = landmarks.landmark[61]
            right_lip = landmarks.landmark[291]
            top_lip = landmarks.landmark[13]
            bottom_lip = landmarks.landmark[14]

            # Deteksi Kedipan Mata (Eye Aspect Ratio)
            left_eye_top = landmarks.landmark[386]
            left_eye_bottom = landmarks.landmark[374]

            # Menghitung jarak mata kiri untuk kedipan
            eye_distance = distance(left_eye_top, left_eye_bottom)

            # Deteksi apakah mata kiri terpejam
            if eye_distance < 0.05:
                eye_state = "Mata Tertutup"
            else:
                eye_state = "Mata Terbuka"

            # Jarak horizontal dan vertikal bibir untuk membuka mulut
            mouth_open = distance(top_lip, bottom_lip)

            # Menentukan kondisi mulut terbuka atau tertutup
            if mouth_open > 0.05:
                mouth_state = "Mulut Terbuka"
            else:
                mouth_state = "Mulut Tertutup"

            # Gabungkan label berdasarkan kondisi mulut dan mata
            label_list = [mouth_state, eye_state]

            # Gabungkan label dengan separator " & "
            label = " & ".join(label_list)

            # Gambar landmark wajah pada frame
            mp_drawing.draw_landmarks(
                frame,
                landmarks,
                mp_face_mesh.FACEMESH_TESSELATION,
                landmark_drawing_spec=mp_drawing.DrawingSpec(color=(0,255,0), thickness=1, circle_radius=1),
                connection_drawing_spec=mp_drawing.DrawingSpec(color=(0,128,255), thickness=1)
            )


    # Tampilkan label prediksi
    cv2.putText(frame, f'Prediksi: {label}', (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    # Tampilkan frame
    cv2.imshow("Deteksi Ekspresi Real-time", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
