from flask import Flask, render_template, Response, jsonify
import cv2
import mediapipe as mp
from deepface import DeepFace
import time
from collections import Counter

app = Flask(__name__)

# Inisialisasi MediaPipe Pose
mp_pose = mp.solutions.pose
pose = mp_pose.Pose()
mp_drawing = mp.solutions.drawing_utils

# Variabel global
emotion_list = []
pose_feedback_list = []
recording_done = False
result_analysis = {}

def analyze_emotion(emotion_counter):
    if not emotion_counter:
        return "Tidak ada wajah terdeteksi", 0
    dominant_emotion, count = emotion_counter.most_common(1)[0]
    emotion_score = 50  # Skor maksimal untuk emosi
    negative_emotions = ['sad', 'angry', 'disgust', 'fear']
    if dominant_emotion in negative_emotions:
        emotion_score -= 20
    elif dominant_emotion == 'neutral':
        emotion_score -= 10
    return dominant_emotion, max(emotion_score, 0)

def analyze_pose(pose_feedbacks):
    if not pose_feedbacks:
        return "Pose tidak terdeteksi", 0
    positive_feedback = pose_feedbacks.count("Postur tubuh tegak dan stabil.")
    pose_score = (positive_feedback / len(pose_feedbacks)) * 50  # Skor maksimal untuk pose
    return "Postur tubuh tegak dan stabil." if positive_feedback > len(pose_feedbacks) / 2 else "Perbaiki postur tubuh Anda.", int(pose_score)

def gen_frames():
    global emotion_list, pose_feedback_list, recording_done, result_analysis

    cap = cv2.VideoCapture(0)
    start_time = time.time()
    duration = 30  # Durasi evaluasi dalam detik

    while True:
        success, frame = cap.read()
        if not success:
            break

        frame = cv2.flip(frame, 1)
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Deteksi pose
        results = pose.process(img_rgb)
        pose_feedback = ""
        if results.pose_landmarks:
            mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
            # Analisis pose sederhana: periksa posisi kepala dan bahu
            left_shoulder = results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = results.pose_landmarks.landmark[mp_pose.PoseLandmark.RIGHT_SHOULDER]
            left_ear = results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_EAR]
            right_ear = results.pose_landmarks.landmark[mp_pose.PoseLandmark.RIGHT_EAR]

            shoulder_avg_y = (left_shoulder.y + right_shoulder.y) / 2
            ear_avg_y = (left_ear.y + right_ear.y) / 2

            if ear_avg_y < shoulder_avg_y:
                pose_feedback = "Postur tubuh tegak dan stabil."
            else:
                pose_feedback = "Perbaiki postur tubuh Anda."
            if not recording_done:
                pose_feedback_list.append(pose_feedback)
            cv2.putText(frame, pose_feedback, (10, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        # Deteksi emosi
        try:
            analysis = DeepFace.analyze(frame, actions=['emotion'], enforce_detection=False)
            emotion = analysis[0]['dominant_emotion']
            if not recording_done:
                emotion_list.append(emotion)
            cv2.putText(frame, f'Emosi: {emotion}', (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        except Exception as e:
            print("Wajah tidak terdeteksi")

        # Cek waktu
        elapsed = time.time() - start_time
        if elapsed > duration and not recording_done:
            cap.release()
            emotion_counter = Counter(emotion_list)
            dominant_emotion, emotion_score = analyze_emotion(emotion_counter)
            pose_feedback, pose_score = analyze_pose(pose_feedback_list)
            total_score = emotion_score + pose_score
            rekomendasi = "Pertahankan ekspresi positif dan postur tubuh yang baik." if total_score > 80 else "Perbaiki ekspresi wajah dan postur tubuh Anda untuk presentasi yang lebih baik."
            result_analysis = {
                "total_score": total_score,
                "emotion_score": emotion_score,
                "pose_score": pose_score,
                "dominant_emotion": dominant_emotion,
                "pose_feedback": pose_feedback,
                "rekomendasi": rekomendasi
            }
            recording_done = True
            break

        # Tampilkan frame
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    # Reset data jika user kembali ke halaman
    global emotion_list, pose_feedback_list, recording_done, result_analysis
    emotion_list = []
    pose_feedback_list = []
    recording_done = False
    result_analysis = {}
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_result')
def get_result():
    return jsonify(result_analysis)

if __name__ == '__main__':
    app.run(debug=True)
