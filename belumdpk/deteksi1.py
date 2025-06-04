# Proses Dataset Berupa Video

import cv2
import mediapipe as mp
import csv

# Inisialisasi MediaPipe
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, refine_landmarks=True)

# Buka file video
video_path = "61299-498228517_tiny.mp4"
cap = cv2.VideoCapture(video_path)

# Siapkan file CSV
csv_file = open('video_landmark_output_video.csv', mode='w', newline='')
csv_writer = csv.writer(csv_file)

# Tulis header
header = []
for i in range(468):
    header += [f'x{i}', f'y{i}', f'z{i}']
header.append('label')
csv_writer.writerow(header)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)

    if results.multi_face_landmarks:
        for face_landmarks in results.multi_face_landmarks:
            row = []
            for lm in face_landmarks.landmark:
                row += [lm.x, lm.y, lm.z]
            row.append('senyum')  # contoh label manual dari nama video
            csv_writer.writerow(row)

cap.release()
csv_file.close()
