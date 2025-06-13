
# routes/hrd_routes.py
from flask import Blueprint, request, jsonify
from database import get_collections
from auth_decorators import token_required, require_api_key
from config import hrd_question_details, hrd_questions_list
from datetime import datetime
from nltk.tokenize import word_tokenize
import random
import pymongo.errors
import logging

hrd_bp = Blueprint('hrd_bp', __name__)
logger = logging.getLogger(__name__)

# Access collections
def get_hrd_collections():
    cols = get_collections()
    return cols["wawancara"]

@hrd_bp.route("/api/hrd/questions", methods=["GET"])
@token_required
@require_api_key
def get_hrd_questions(current_user):
    logger.info(f"Get HRD questions endpoint hit by user: {current_user.get('username')}")
    try:
        if len(hrd_questions_list) < 5:
            selected_questions = random.sample(hrd_questions_list, len(hrd_questions_list))
        else:
            selected_questions = random.sample(hrd_questions_list, 5)
        logger.debug(f"Selected HRD questions: {selected_questions}")
        return jsonify({
            "status": "success",
            "questions": selected_questions
        })
    except Exception as e:
        logger.error(f"Error getting HRD questions for user {current_user.get('username')}: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@hrd_bp.route("/api/hrd/analyze_response", methods=["POST"])
@token_required
@require_api_key
def analyze_hrd_response(current_user):
    logger.info(f"Analyze HRD response endpoint hit by user: {current_user.get('username')}")
    data = request.get_json()

    required_fields = ["transcribed_text", "response_time", "question_index"]
    if not all(field in data for field in required_fields):
        logger.warning(f"Missing required fields for HRD response analysis: {data}")
        return jsonify({"status": "fail", "message": "Missing required fields"}), 400

    try:
        transcribed_text = data.get("transcribed_text", "").strip()
        response_time = data.get("response_time", 0)
        question_index = data.get("question_index", -1)

        current_question_text = ""
        if 0 <= question_index < len(hrd_questions_list):
            current_question_text = hrd_questions_list[question_index]
        else:
            logger.warning(f"Invalid question index {question_index} for HRD analysis.")
            return jsonify({
                "status": "fail",
                "message": "Invalid question index or missing question text.",
                "feedback": "Tidak dapat menemukan pertanyaan yang sesuai.",
                "expression": "confused",
                "score": 0
            }), 400

        score = 0
        feedback_message = ""
        expression = "neutral"

        logger.debug(f"HRD Analysis Input - Question: '{current_question_text}', Text: '{transcribed_text[:50]}...', Time: {response_time}s")

        if not transcribed_text or len(transcribed_text.split()) < 3:
            if response_time >= 29:
                feedback_message = "Waktu habis dan Anda tidak memberikan jawaban yang cukup."
                expression = "bored"
                score = 5
            else:
                feedback_message = "Jawaban Anda terlalu singkat. Mohon berikan jawaban yang lebih lengkap dan jelas."
                expression = "confused"
                score = 10

            logger.debug(f"HRD Analysis: Short/Empty answer. Score: {score}, Feedback: {feedback_message}")
            return jsonify({
                "status": "success",
                "feedback": feedback_message,
                "expression": expression,
                "score": score,
                "metrics": {"response_time": response_time, "word_count": len(transcribed_text.split()), "transcribed_text_received": transcribed_text}
            })

        words = word_tokenize(transcribed_text.lower())
        num_words = len(words)

        question_criteria = hrd_question_details.get(current_question_text, {})
        ideal_len = question_criteria.get("ideal_length", 15)
        keywords = question_criteria.get("keywords", [])

        base_score_length = 0
        if num_words < ideal_len * 0.4:
            feedback_message += "Jawaban Anda masih terlalu singkat. Coba elaborasi lebih lanjut. "
            base_score_length = 20
            expression = "confused"
        elif num_words < ideal_len * 0.7:
            feedback_message += "Jawaban Anda cukup baik, namun bisa lebih detail. "
            base_score_length = 40
            expression = "neutral"
        elif num_words < ideal_len * 1.5:
            feedback_message += "Panjang jawaban Anda sudah baik dan cukup komprehensif. "
            base_score_length = 60
            expression = "neutral"
        else:
            feedback_message += "Jawaban Anda sangat detail. Pastikan tetap fokus pada inti pertanyaan. "
            base_score_length = 50
            expression = "happy"

        score += base_score_length

        matched_keywords_count = 0
        if keywords:
            unique_answer_words = set(words)
            for kw in keywords:
                if kw in unique_answer_words:
                    matched_keywords_count += 1

            keyword_score_bonus = 0
            if matched_keywords_count == 0 and num_words > 5:
                feedback_message += "Namun, jawaban Anda sepertinya kurang menyentuh poin-poin kunci yang diharapkan. "
                score = max(15, score - 15)
                if expression == "happy": expression = "confused"
            elif matched_keywords_count > 0 and matched_keywords_count <= len(keywords) / 2:
                feedback_message += "Beberapa poin penting sudah Anda sebutkan. "
                keyword_score_bonus = 15
                if expression == "confused": expression = "neutral"
            elif matched_keywords_count > len(keywords) / 2:
                feedback_message += "Anda berhasil menyoroti banyak poin kunci dengan baik! "
                keyword_score_bonus = 30
                expression = "happy"

            score += keyword_score_bonus
        else:
            feedback_message += "Pertanyaan ini tidak memiliki kata kunci spesifik untuk dinilai. Penilaian berdasarkan kejelasan dan kelengkapan. "
            if score < 50 and num_words > ideal_len * 0.7 :
                score = max(score, 50)
                expression = "neutral" if expression == "confused" else expression

        if response_time < 3 and num_words < ideal_len * 0.5:
            feedback_message += "Anda menjawab sangat cepat, mungkin kurang dipertimbangkan. "
            score = max(10, score - 20)
            expression = "confused"

        score = min(max(0, score), 100)

        if expression == "neutral" or expression == "confused":
            if score >= 75:
                expression = "happy"
            elif score >= 50:
                expression = "neutral"
            else:
                expression = "confused"

        logger.debug(f"HRD Analysis Result - Score: {score}, Expression: {expression}, Feedback: {feedback_message.strip()}")
        return jsonify({
            "status": "success",
            "feedback": feedback_message.strip() if feedback_message else "Jawaban Anda telah diterima.",
            "expression": expression,
            "score": score,
            "metrics": {
                "response_time": response_time,
                "word_count": num_words,
                "transcribed_text_received": transcribed_text,
                "matched_keywords": matched_keywords_count if keywords else "N/A",
                "total_keywords_expected": len(keywords) if keywords else "N/A"
            }
        })

    except Exception as e:
        logger.error(f"Critical Error in analyze_hrd_response for user {current_user.get('username')}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Terjadi kesalahan internal server: {str(e)}"}), 500

@hrd_bp.route("/api/hrd/save_session_summary", methods=["POST"])
@token_required
@require_api_key
def save_hrd_session_summary(current_user):
    logger.info(f"Save HRD session summary endpoint hit by user: {current_user.get('username')}")
    wawancara_collection = get_hrd_collections()
    data = request.get_json()

    try:
        if not all(key in data for key in ["overall_score", "responses_detail"]):
            logger.warning(f"Missing data for HRD session summary: {data}")
            return jsonify({"status": "fail", "message": "Missing overall_score or responses_detail"}), 400

        wawancara_doc = {
            "user_id": current_user['_id'],
            "username": current_user['username'],
            "timestamp": datetime.utcnow(),
            "type": "hrd_simulation",
            "results": {
                "overall_score": data.get("overall_score"),
                "individual_responses": data.get("responses_detail", [])
            },
            "metrics": {
                "average_score_hrd": data.get("overall_score"),
                "number_of_questions": len(data.get("responses_detail", [])),
                "total_duration_seconds": data.get("session_duration_seconds", 0)
            },
            "recording_duration": data.get("session_duration_seconds", 0),
            "feedback": data.get("final_feedback_summary", "Sesi HRD telah diselesaikan."),
            "difficulty": data.get("difficulty", "medium")
        }

        insert_result = wawancara_collection.insert_one(wawancara_doc)

        logger.info(f"HRD session summary saved successfully for user {current_user.get('username')}. ID: {insert_result.inserted_id}")
        return jsonify({
            "status": "success",
            "message": "HRD session summary saved successfully.",
            "inserted_id": str(insert_result.inserted_id)
            }), 201

    except Exception as e:
        logger.error(f"Error saving HRD session summary for user {current_user.get('username')}: {str(e)}")
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500

@hrd_bp.route("/api/hrd/history", methods=["GET"])
@token_required
@require_api_key
def get_hrd_history_route(current_user):
    logger.info(f"Get HRD history endpoint hit by user: {current_user.get('username')}")
    wawancara_collection = get_hrd_collections()
    try:
        if wawancara_collection is None:
            logger.error("wawancara_collection is None in get_hrd_history_route")
            return jsonify({"status": "fail", "message": "Database service unavailable"}), 503

        hrd_sessions = list(wawancara_collection.find(
            {"user_id": current_user['_id'], "type": "hrd_simulation"}
        ).sort("timestamp", -1).limit(10))

        formatted_sessions = []
        for session in hrd_sessions:
            session_data = {
                "_id": str(session['_id']),
                "timestamp": session['timestamp'].isoformat() if isinstance(session.get('timestamp'), datetime) else str(session.get('timestamp')),
                "overall_score": session.get('results', {}).get('overall_score', 0),
                "difficulty": session.get('difficulty', 'N/A'),
                "number_of_questions": session.get('metrics', {}).get('number_of_questions', 0),
                "session_duration_seconds": session.get('metrics', {}).get('total_duration_seconds', 0)
            }
            formatted_sessions.append(session_data)

        all_hrd_sessions_for_user = list(wawancara_collection.find(
            {"user_id": current_user['_id'], "type": "hrd_simulation"}
        ))
        total_hrd_sessions_count = len(all_hrd_sessions_for_user)

        total_hrd_score = sum(s.get('results', {}).get('overall_score', 0) for s in all_hrd_sessions_for_user)
        average_hrd_score = total_hrd_score / total_hrd_sessions_count if total_hrd_sessions_count > 0 else 0.0

        last_hrd_session_data = {}
        if formatted_sessions:
            last_hrd_session_data = {
                'timestamp': formatted_sessions[0]['timestamp'],
                'overall_score': formatted_sessions[0]['overall_score'],
                'difficulty': formatted_sessions[0]['difficulty'],
                'session_duration_seconds': formatted_sessions[0]['session_duration_seconds']
            }

        weaknesses_hrd = []
        if average_hrd_score < 60 and total_hrd_sessions_count > 0:
            weaknesses_hrd.append({
                "area": "Skor Keseluruhan",
                "description": "Rata-rata skor simulasi HRD Anda masih rendah. Perbanyak latihan.",
                "progress": average_hrd_score / 100,
                "suggestion": "Fokus pada kelengkapan dan relevansi jawaban."
            })
        if total_hrd_sessions_count == 0:
             weaknesses_hrd.append({
                "area": "Sesi Latihan",
                "description": "Anda belum melakukan sesi latihan HRD. Mulailah berlatih untuk meningkatkan performa Anda.",
                "progress": 0,
                "suggestion": "Mulai sesi HRD pertama Anda untuk mendapatkan evaluasi."
            })

        logger.debug(f"HRD history for user {current_user.get('username')}: Total sessions={total_hrd_sessions_count}, Avg score={average_hrd_score}")
        return jsonify({
            "status": "success",
            "data": {
                "total_sessions": total_hrd_sessions_count,
                "average_score": average_hrd_score,
                "history": formatted_sessions,
                "last_session": last_hrd_session_data,
                "metrics": {
                    "average_hrd_score": average_hrd_score,
                },
                "weaknesses": weaknesses_hrd
            }
        })
    except pymongo.errors.PyMongoError as e:
        logger.error(f"DB error getting HRD history for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": "Database error while fetching HRD history."}), 500
    except Exception as e:
        logger.error(f"Error getting HRD history for user {current_user.get('username')}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}), 500
