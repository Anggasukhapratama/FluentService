import cv2
import mediapipe as mp
import base64
import numpy as np

mp_pose = mp.solutions.pose
mp_face = mp.solutions.face_mesh

def analyze_frames(image_list):
    pose_scores = []
    face_scores = []

    for image_base64 in image_list:
        nparr = np.frombuffer(base64.b64decode(image_base64), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        with mp_pose.Pose(static_image_mode=True) as pose:
            results = pose.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            pose_scores.append(1 if results.pose_landmarks else 0)

        with mp_face.FaceMesh(static_image_mode=True) as face:
            results = face.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            face_scores.append(1 if results.multi_face_landmarks else 0)

    pose_score = sum(pose_scores) / len(pose_scores)
    face_score = sum(face_scores) / len(face_scores)

    komentar = []
    if pose_score < 0.5:
        komentar.append("Postur tubuh kurang terlihat jelas.")
    else:
        komentar.append("Postur tubuh sudah cukup baik.")

    if face_score < 0.5:
        komentar.append("Ekspresi wajah kurang jelas atau tidak terdeteksi.")
    else:
        komentar.append("Ekspresi wajah terlihat jelas.")

    overall = "Presentasi cukup baik." if pose_score > 0.7 and face_score > 0.7 else "Perlu peningkatan postur dan ekspresi."

    return {
        "pose_score": pose_score,
        "face_score": face_score,
        "komentar": komentar,
        "kesimpulan": overall
    }
