# routes/narration_routes.py
from flask import Blueprint, request, jsonify
from database import get_collections
from auth_decorators import token_required, require_api_key
from datetime import datetime
import cv2
import tempfile
import base64
import numpy as np
import os
import logging

# Assuming these are actual files in the detectors directory
from detectors.emotion_detector import detect_emotion_status
from detectors.mouth_detector import detect_mouth_status
from detectors.pose_detector import detect_pose_status

narration_bp = Blueprint('narration_bp', __name__)
logger = logging.getLogger(__name__)

# Access collections
def get_narration_collections():
    cols = get_collections()
    return cols["wawancara"]

@narration_bp.route("/analyze_realtime", methods=["POST"])
@token_required
@require_api_key
def analyze_realtime(current_user):
    logger.info(f"Analyze realtime endpoint hit by user: {current_user.get('username')}")
    data = request.get_json()

    if "frame" not in data:
        logger.warning("Frame not provided in analyze_realtime request.")
        return jsonify({"status": "fail", "message": "Frame not provided"}), 400

    try:
        img_data = base64.b64decode(data["frame"])
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            logger.warning("Invalid image data received in analyze_realtime.")
            return jsonify({"status": "fail", "message": "Invalid image data"}), 400

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            image_path = tmp_file.name
            cv2.imwrite(image_path, frame)

        emotion_result = detect_emotion_status(image_path)
        mouth_result = detect_mouth_status(image_path)
        pose_result = detect_pose_status(image_path)

        os.unlink(image_path) # Clean up temp file

        logger.debug(f"Realtime analysis results for user {current_user.get('username')}: Emotion={emotion_result}, Mouth={mouth_result}, Pose={pose_result}")
        return jsonify({
            "status": "success",
            "results": {
                "emotion": emotion_result,
                "mouth": mouth_result,
                "pose": pose_result
            }
        })

    except Exception as e:
        logger.error(f"Error analyzing realtime image for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@narration_bp.route("/save_wawancara", methods=["POST"])
@token_required
@require_api_key
def save_wawancara(current_user):
    logger.info(f"Save wawancara endpoint hit by user: {current_user.get('username')}")
    wawancara_collection = get_narration_collections()
    data = request.get_json()

    try:
        metrics_from_client = data.get("metrics", {})
        results_from_client = data.get("results", {})

        wawancara_data = {
            "user_id": current_user['_id'],
            "username": current_user['username'],
            "timestamp": datetime.utcnow(),
            "results": results_from_client,
            "metrics": {
                "accuracy": metrics_from_client.get("accuracy", 0),
                "wpm": metrics_from_client.get("wpm", 0),
                "fluency": metrics_from_client.get("fluency", 0),
                "filler_words": metrics_from_client.get("filler_words", 0),
                "overal_stt_confidence": metrics_from_client.get("overall_stt_confidence", 0),
            },
            "recording_duration": data.get("recording_duration", 0),
            "feedback": data.get("feedback", []),
            "difficulty": data.get("difficulty", "medium"),
            "type": "narration_practice"
        }

        wawancara_collection.insert_one(wawancara_data)
        logger.info(f"Wawancara data saved for user: {current_user.get('username')}")
        return jsonify({"status": "success", "message": "Data wawancara disimpan"})

    except Exception as e:
        logger.error(f"Error saving wawancara data for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@narration_bp.route("/get_wawancara", methods=["GET"])
@token_required
@require_api_key
def get_wawancara(current_user):
    logger.info(f"Get wawancara endpoint hit by user: {current_user.get('username')}")
    wawancara_collection = get_narration_collections()
    try:
        wawancaras = list(wawancara_collection.find(
            {"user_id": current_user['_id'], "type": "narration_practice"}
        ).sort("timestamp", -1).limit(10))

        for w in wawancaras:
            w['_id'] = str(w['_id'])
            w['timestamp'] = w['timestamp'].isoformat() if isinstance(w['timestamp'], datetime) else str(w['timestamp'])

        logger.debug(f"Retrieved {len(wawancaras)} narration practice sessions for user {current_user.get('username')}")
        return jsonify({"status": "success", "wawancaras": wawancaras})

    except Exception as e:
        logger.error(f"Error retrieving wawancara data for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@narration_bp.route('/progress', methods=['GET'])
@token_required
@require_api_key
def get_progress(current_user):
    logger.info(f"Get progress endpoint hit by user: {current_user.get('username')}")
    wawancara_collection = get_narration_collections()
    try:
        total_sessions = wawancara_collection.count_documents(
            {"user_id": current_user['_id'], "type": "narration_practice"}
        )

        raw_sessions = list(wawancara_collection.find(
            {"user_id": current_user['_id'], "type": "narration_practice"}
        ).sort("timestamp", -1).limit(10))

        sessions = []
        for s in raw_sessions:
            if not isinstance(s, dict):
                logger.warning(f"Found malformed session data (not a dict) for user {current_user.get('username')}: {s}. Skipping.")
                continue

            if 'metrics' in s and not isinstance(s['metrics'], dict):
                logger.warning(f"Session ID {s.get('_id', 'N/A')} for user {current_user.get('username')} has non-dict 'metrics' field: {s['metrics']}. Setting to empty dict.")
                s['metrics'] = {}
            elif 'metrics' not in s:
                s['metrics'] = {}

            if 'results' in s and not isinstance(s['results'], dict):
                logger.warning(f"Session ID {s.get('_id', 'N/A')} for user {current_user.get('username')} has non-dict 'results' field: {s['results']}. Setting to empty dict.")
                s['results'] = {}
            elif 'results' not in s:
                s['results'] = {}

            sessions.append(s)

        total_score = sum(session.get('metrics', {}).get('accuracy', 0) for session in sessions)
        average_score = total_score / len(sessions) if sessions else 0

        history = [{
            "timestamp": session.get('timestamp').isoformat() if isinstance(session.get('timestamp'), datetime) else str(session.get('timestamp', '')),
            "overall_score": session.get('metrics', {}).get('accuracy', 0)
        } for session in sessions]

        last_session = sessions[0] if sessions else {}
        metrics = last_session.get('metrics', {})

        expression_string = last_session.get('results', {}).get('emotion', '').lower()
        expression_score = 0.0

        if 'normal' in expression_string:
            expression_score = 80.0
        elif 'gugup' in expression_string:
            expression_score = 30.0
        else:
            expression_score = 0.0

        logger.debug(f"Calculated expression score from string '{expression_string}': {expression_score}")

        weaknesses = []
        if metrics.get('wpm', 0) > 0 and metrics.get('wpm', 0) < 100:
            weaknesses.append({
                "area": "Kecepatan Bicara",
                "description": "Kecepatan bicara Anda tergolong lambat (<100 WPM).",
                "progress": metrics.get('wpm', 0) / 150,
                "suggestion": "Cobalah berlatih bicara lebih cepat dan lancar."
            })
        elif metrics.get('wpm', 0) > 180:
             weaknesses.append({
                "area": "Kecepatan Bicara",
                "description": "Kecepatan bicara Anda tergolong terlalu cepat (>180 WPM).",
                "progress": 1.0,
                "suggestion": "Cobalah bicara lebih teratur dan beri jeda."
            })

        if metrics.get('fluency', 0) < 70 and metrics.get('fluency', 0) > 0:
            weaknesses.append({
                "area": "Kelancaran",
                "description": "Kelancaran bicara Anda perlu ditingkatkan (<70%).",
                "progress": metrics.get('fluency', 0) / 100,
                "suggestion": "Latihan membaca nyaring dan mengurangi jeda 'filler words'."
            })
        if metrics.get('filler_words', 0) > 5 and total_sessions > 0:
            weaknesses.append({
                "area": "Kata Pengisi",
                "description": f"Anda terlalu banyak menggunakan kata pengisi ({metrics.get('filler_words')} kali).",
                "progress": 1.0 - (min(metrics.get('filler_words', 0), 10) / 10.0),
                "suggestion": "Cobalah untuk lebih sadar dan mengurangi penggunaan 'umm', 'ahh'."
            })

        logger.debug(f"Narration progress for user {current_user.get('username')}: Total sessions={total_sessions}, Avg score={average_score}")
        return jsonify({
            "status": "success",
            "data": {
                "total_sessions": total_sessions,
                "average_score": average_score,
                "history": history,
                "metrics": {
                    "expression": expression_score,
                    "narrative": metrics.get('accuracy', 0),
                    "clarity": metrics.get('fluency', 0),
                    "confidence": metrics.get('overall_stt_confidence', 0),
                    "filler_words": metrics.get('filler_words', 0)
                },
                "weaknesses": weaknesses,
                "last_session": {
                    "timestamp": last_session.get('timestamp', '').isoformat() if last_session and isinstance(last_session.get('timestamp'), datetime) else None,
                    "overall_score": metrics.get('accuracy', 0)
                }
            }
        })

    except Exception as e:
        logger.error(f"Error getting narration progress for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500
