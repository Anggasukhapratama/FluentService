# routes/ai_interview_routes.py
from flask import Blueprint, request, jsonify, current_app
from database import get_collections
from auth_decorators import token_required, require_api_key
import logging
from bson import ObjectId, errors
import datetime
import tempfile
import base64
import os
import json

# Import Gemini SDK
import google.generativeai as genai

# Import your custom detectors
from detectors.facial_expression_detector import detect_facial_expression
from detectors.mouth_detector import detect_mouth_status
from detectors.pose_detector import detect_pose_status

# Import interview topics from config
from config import INTERVIEW_TOPICS, GEMINI_API_KEY

ai_interview_bp = Blueprint('ai_interview_bp', __name__, url_prefix='/api/ai_interview')
logger = logging.getLogger(__name__)

# Configure Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("Google Gemini API configured.")
else:
    logger.error("GEMINI_API_KEY not found in config. Gemini functions will not work.")

def get_ai_interview_collections():
    cols = get_collections()
    return cols["interviews"]

def get_gemini_model():
    if not GEMINI_API_KEY:
        return None
    try:
        return genai.GenerativeModel('gemini-1.5-flash-latest')
    except Exception as e:
        logger.error(f"Error initializing Gemini model: {e}")
        return None

# ==============================================================================
# CONFIDENCE CALCULATION HELPER
# ==============================================================================
def calculate_confidence_score(pose_status, expression_status, real_time_gemini_feedback):
    score = 0
    feedback_points = []

    # Visual Cues
    if pose_status == "lurus":
        score += 30
        feedback_points.append("Postur tubuh Anda terlihat tegak.")
    elif pose_status in ["miring_kiri", "miring_kanan"]:
        score += 10
        feedback_points.append("Perhatikan postur tubuh Anda, hindari posisi miring.")
    else:
        feedback_points.append("Postur tubuh tidak terdeteksi.")

    if expression_status == "senang":
        score += 30
        feedback_points.append("Ekspresi Anda menunjukkan antusiasme dan positif.")
    elif expression_status == "netral":
        score += 20
        feedback_points.append("Ekspresi Anda menunjukkan ketenangan.")
    elif expression_status == "gugup":
        score += 5
        feedback_points.append("Ekspresi Anda sedikit tegang atau gugup.")
    elif expression_status in ["sedih", "marah", "terkejut"]:
        score -= 10
        feedback_points.append(f"Ekspresi Anda ({expression_status}) mungkin kurang sesuai untuk wawancara.")
    else:
        feedback_points.append("Ekspresi wajah tidak terdeteksi.")

    # Linguistic Cues (from Gemini feedback)
    feedback_lower = real_time_gemini_feedback.lower()
    
    if "jelas" in feedback_lower or "baik" in feedback_lower or "bagus" in feedback_lower:
        score += 20
        feedback_points.append("Jawaban Anda jelas dan terstruktur dengan baik.")
    if "terstruktur" in feedback_lower or "runtut" in feedback_lower:
        score += 10
        feedback_points.append("Struktur jawaban Anda terorganisir.")
    if "relevan" in feedback_lower:
        score += 10
        feedback_points.append("Jawaban Anda sangat relevan dengan pertanyaan.")
    
    # Penalties
    if "ragu" in feedback_lower or "kurang yakin" in feedback_lower:
        score -= 15
        feedback_points.append("Ada indikasi keraguan dalam jawaban Anda.")
    if "kata pengisi" in feedback_lower or "umm" in feedback_lower or "ehh" in feedback_lower:
        score -= 10
        feedback_points.append("Perhatikan penggunaan kata pengisi.")
    if "tidak relevan" in feedback_lower or "melenceng" in feedback_lower:
        score -= 15
        feedback_points.append("Jawaban kurang relevan dengan pertanyaan.")

    score = max(0, min(100, score))

    confidence_feedback_summary = ""
    if score >= 80:
        confidence_feedback_summary = "Tingkat kepercayaan diri Anda sangat baik. Pertahankan!"
    elif score >= 60:
        confidence_feedback_summary = "Anda menunjukkan kepercayaan diri yang cukup baik, namun ada ruang untuk peningkatan."
    elif score >= 40:
        confidence_feedback_summary = "Kepercayaan diri Anda perlu ditingkatkan. Cobalah untuk lebih yakin dengan diri sendiri."
    else:
        confidence_feedback_summary = "Tingkat kepercayaan diri Anda cukup rendah. Perbanyak latihan untuk membangun keyakinan."

    return {
        "score": score,
        "feedback_points": feedback_points,
        "summary": confidence_feedback_summary
    }

# ==============================================================================

@ai_interview_bp.route("/get_categories", methods=["GET"])
@token_required
@require_api_key
def get_interview_categories(current_user):
    logger.info(f"Get interview categories hit by user: {current_user.get('username')}")
    categories = [{"id": key, "name": value["name"]} for key, value in INTERVIEW_TOPICS.items()]
    return jsonify({"status": "success", "categories": categories}), 200

@ai_interview_bp.route("/start_session", methods=["POST"])
@token_required
@require_api_key
def start_ai_interview_session(current_user):
    logger.info(f"Start AI interview session hit by user: {current_user.get('username')}")
    interviews_collection = get_ai_interview_collections()
    data = request.get_json()
    category_id = data.get('category_id')

    if not category_id or category_id not in INTERVIEW_TOPICS:
        logger.warning(f"Invalid or missing category_id: {category_id}")
        return jsonify({"status": "fail", "message": "Kategori wawancara tidak valid."}), 400

    topic_info = INTERVIEW_TOPICS[category_id]
    model = get_gemini_model()
    if not model:
        return jsonify({"status": "error", "message": "Gemini API tidak terkonfigurasi atau gagal diinisialisasi."}), 500

    try:
        # Prompt awal untuk memastikan format pertanyaan pertama jelas
        chat = model.start_chat(history=[
            {"role": "user", "parts": f"Anda adalah pewawancara HRD yang sangat profesional. Saya akan berperan sebagai kandidat. Berikan satu pertanyaan pertama yang relevan untuk memulai wawancara dengan konteks: {topic_info['prompt_context']}. Pertanyaan harus singkat, langsung ke inti, dan dalam bahasa Indonesia. Jangan berikan feedback, intro, atau nomor pada pertanyaan ini. Pastikan output Anda HANYA pertanyaan."}
        ])
        
        response = chat.send_message("Tanyakan pertanyaan pertama sekarang.")
        first_question = response.text.strip().replace('"', '').replace("'", "").replace("Pertanyaan:", "").strip()

        session_data = {
            "user_id": current_user['_id'],
            "username": current_user['username'],
            "timestamp": datetime.datetime.utcnow(),
            "category_id": category_id,
            "category_name": topic_info['name'],
            "status": "in_progress",
            "questions_asked": [
                {"question": first_question, "timestamp_asked": datetime.datetime.utcnow(), "response": None, "feedback_realtime": None, "visual_analysis": None, "confidence_score": None, "confidence_feedback": None, "mouth_detections": [], "pose_detections": []} # NEW: lists for detailed detections
            ],
            "overall_feedback": None,
            "total_duration_seconds": 0,
            "total_speaking_instances": 0,
            "total_leaning_instances": 0
        }
        insert_result = interviews_collection.insert_one(session_data)
        session_id = str(insert_result.inserted_id)

        logger.info(f"AI interview session started for user {current_user.get('username')} (ID: {session_id}) in category '{topic_info['name']}'.")
        return jsonify({
            "status": "success",
            "message": "Sesi wawancara dimulai.",
            "session_id": session_id,
            "first_question": first_question
        }), 201

    except Exception as e:
        logger.error(f"Error starting AI interview session for user {current_user.get('username')}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Gagal memulai sesi wawancara: {str(e)}"}), 500

@ai_interview_bp.route("/process_response", methods=["POST"])
@token_required
@require_api_key
def process_ai_interview_response(current_user):
    logger.info(f"Process AI interview response hit by user: {current_user.get('username')}")
    interviews_collection = get_ai_interview_collections()
    data = request.get_json()

    session_id = data.get('session_id')
    response_text = data.get('response_text')
    frame_base64 = data.get('frame')
    question_index = data.get('question_index')

    if not all([session_id, response_text, frame_base64 is not None, question_index is not None]):
        logger.warning("Missing data for processing AI interview response.")
        return jsonify({"status": "fail", "message": "Data tidak lengkap: session_id, response_text, frame, dan question_index diperlukan."}), 400

    try:
        session_obj_id = ObjectId(session_id)
        session_doc = interviews_collection.find_one({"_id": session_obj_id, "user_id": current_user['_id']})

        if not session_doc:
            logger.warning(f"AI interview session {session_id} not found for user {current_user['_id']}.")
            return jsonify({"status": "fail", "message": "Sesi wawancara tidak ditemukan."}), 404
        
        if session_doc["status"] != "in_progress":
            logger.warning(f"Attempt to process response for non-in-progress session {session_id}.")
            return jsonify({"status": "fail", "message": "Sesi wawancara sudah berakhir atau belum dimulai."}), 400

        if question_index >= len(session_doc['questions_asked']) or question_index < 0:
            logger.warning(f"Invalid question_index {question_index} for session {session_id}.")
            return jsonify({"status": "fail", "message": "Indeks pertanyaan tidak valid."}), 400

        image_path = None
        visual_analysis = {
            "pose": "tidak terdeteksi",
            "mouth": "tidak terdeteksi",
            "expression": "tidak terdeteksi"
        }

        # Perbarui `mouth_detections` dan `pose_detections` di dokumen sesi
        current_mouth_detections = session_doc['questions_asked'][question_index].get('mouth_detections', [])
        current_pose_detections = session_doc['questions_asked'][question_index].get('pose_detections', [])

        if frame_base64: # Hanya proses frame jika tidak kosong
            try:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                    image_path = tmp_file.name
                    img_data = base64.b64decode(frame_base64)
                    with open(image_path, 'wb') as f:
                        f.write(img_data)
                
                pose_status = detect_pose_status(image_path)
                mouth_status = detect_mouth_status(image_path)
                expression_status = detect_facial_expression(image_path)
                
                visual_analysis = {
                    "pose": pose_status,
                    "mouth": mouth_status,
                    "expression": expression_status
                }
                
                current_mouth_detections.append(mouth_status) # Rekam deteksi mulut
                current_pose_detections.append(pose_status)   # Rekam deteksi pose

                logger.debug(f"Visual analysis for session {session_id}, Q{question_index}: {visual_analysis}")
            except Exception as e:
                logger.error(f"Error running visual detections on {image_path}: {e}", exc_info=True)
            finally:
                if image_path and os.path.exists(image_path):
                    os.unlink(image_path)

        model = get_gemini_model()
        if not model:
            return jsonify({"status": "error", "message": "Gemini API tidak terkonfigurasi atau gagal diinisialisasi."}), 500
        
        current_question_text = session_doc['questions_asked'][question_index]['question']
        topic_info = INTERVIEW_TOPICS[session_doc['category_id']]

        # Prompt yang lebih kuat untuk memastikan format output
        chat_history = [
            {"role": "user", "parts": f"Anda adalah pewawancara HRD yang sangat profesional dan konstruktif. Saya akan berperan sebagai kandidat. Berikan umpan balik real-time pada jawaban saya dan ajukan pertanyaan berikutnya. Konteks wawancara: {topic_info['prompt_context']}. Fokus pada relevansi, kelengkapan, kejelasan, dan kepercayaan diri. Batasi umpan balik real-time maksimal 2-3 kalimat. Setelah umpan balik, **SANGAT PENTING:** langsung ajukan pertanyaan berikutnya yang relevan dan singkat. Formatnya harus: 'UMPAN BALIK: [Umpan balik Anda]. PERTANYAAN: [Pertanyaan berikutnya Anda]'. Jika Anda merasa wawancara sudah cukup panjang (misal lebih dari 7-8 pertanyaan) atau saya mengatakan 'selesai', berikan umpan balik keseluruhan sebagai gantinya. Jika Anda memberikan umpan balik keseluruhan, formatnya harus: 'UMUMAN: Wawancara telah selesai. UMPAN BALIK KESELURUHAN: [Umpan balik keseluruhan Anda]. Jangan berikan pertanyaan berikutnya."}
        ]
        
        # Build history from previous Q&A
        for qa in session_doc['questions_asked']:
            if qa.get('question'):
                chat_history.append({"role": "user", "parts": qa['question']})
            if qa.get('feedback_realtime') and qa.get('next_question') is not None:
                # Reconstruct AI's previous turn based on expected format
                if "UMUMAN: Wawancara telah selesai." in qa['feedback_realtime']: # If previous was an end signal
                    chat_history.append({"role": "model", "parts": qa['feedback_realtime']})
                else:
                    chat_history.append({"role": "model", "parts": f"UMPAN BALIK: {qa['feedback_realtime']}. PERTANYAAN: {qa['next_question']}"})
            # Add user's previous response
            if qa.get('response'):
                chat_history.append({"role": "user", "parts": qa['response']})

        chat = model.start_chat(history=chat_history)
        
        response_from_gemini = chat.send_message(f"Jawaban saya untuk pertanyaan '{current_question_text}': '{response_text}'")
        gemini_output = response_from_gemini.text.strip()
        logger.debug(f"Gemini raw output: {gemini_output}")
        
        real_time_feedback = "Tidak ada umpan balik dari AI."
        next_question = ""
        is_session_completed_by_ai = False

        # Parse Gemini's output based on explicit markers
        if "UMUMAN: Wawancara telah selesai." in gemini_output:
            is_session_completed_by_ai = True
            real_time_feedback = "Wawancara telah selesai. Silakan tekan tombol 'Akhiri Wawancara' untuk melihat ringkasan."
            next_question = "Terima kasih atas partisipasi Anda. Wawancara telah selesai. Silakan tekan tombol 'Akhiri Wawancara'."
            # Optionally extract the full overall feedback here if needed for early display
            if "UMPAN BALIK KESELURUHAN:" in gemini_output:
                overall_feedback_start_idx = gemini_output.find("UMPAN BALIK KESELURUHAN:")
                # Store this somewhere if you want it early, but end_session is primary
                # self.temp_overall_feedback = gemini_output[overall_feedback_start_idx:].strip()
            logger.info("Gemini signaled session completion.")
        elif "UMPAN BALIK:" in gemini_output and "PERTANYAAN:" in gemini_output:
            try:
                feedback_part, question_part = gemini_output.split('PERTANYAAN:', 1)
                real_time_feedback = feedback_part.replace('UMPAN BALIK:', '').strip()
                next_question = question_part.strip()
                if not real_time_feedback: real_time_feedback = "Umpan balik: Cukup baik."
            except ValueError:
                logger.warning(f"Could not parse Gemini output with expected markers. Fallback to line split. Output: {gemini_output}")
                gemini_output_lines = gemini_output.split('\n', 1)
                real_time_feedback = gemini_output_lines[0].strip() if gemini_output_lines else "Tidak ada umpan balik dari AI."
                if len(gemini_output_lines) > 1:
                    next_question = gemini_output_lines[1].strip()
        else: # Fallback for unexpected formats
            logger.warning(f"Gemini output lacked expected markers. Defaulting feedback/question. Output: {gemini_output}")
            gemini_output_lines = gemini_output.split('\n', 1)
            real_time_feedback = gemini_output_lines[0].strip() if gemini_output_lines else "Tidak ada umpan balik dari AI."
            if len(gemini_output_lines) > 1:
                next_question = gemini_output_lines[1].strip()

        # Final check for empty next_question and session length
        if not next_question and not is_session_completed_by_ai:
            if len(session_doc['questions_asked']) >= 7: # If already many questions and no explicit next_question
                is_session_completed_by_ai = True
                real_time_feedback = "Wawancara telah mencapai batas pertanyaan. Silakan tekan tombol 'Akhiri Wawancara'."
                next_question = "Terima kasih. Anda dapat menekan 'Akhiri Wawancara'."
                logger.info("Session auto-completed due to question limit and no new question from AI.")
            else:
                next_question = "Maaf, saya tidak dapat merumuskan pertanyaan berikutnya dengan jelas. Bisakah Anda mengulang jawaban Anda atau saya ajukan pertanyaan lain?"
                logger.warning("Generated next_question was empty, defaulting to a retry prompt.")


        confidence = calculate_confidence_score(visual_analysis['pose'], visual_analysis['expression'], real_time_feedback)
        
        # Update current question's details in DB
        update_field = f"questions_asked.{question_index}"
        update_data_set = {
            f"{update_field}.response": response_text,
            f"{update_field}.timestamp_responded": datetime.datetime.utcnow(),
            f"{update_field}.feedback_realtime": real_time_feedback,
            f"{update_field}.visual_analysis": visual_analysis,
            f"{update_field}.confidence_score": confidence['score'],
            f"{update_field}.confidence_feedback": confidence['summary'],
            f"{update_field}.mouth_detections": current_mouth_detections, # Simpan list deteksi mulut
            f"{update_field}.pose_detections": current_pose_detections    # Simpan list deteksi pose
        }
        
        interviews_collection.update_one(
            {"_id": session_obj_id, "user_id": current_user['_id']},
            {"$set": update_data_set}
        )

        # Add next question to the array if not ending
        if not is_session_completed_by_ai and next_question:
            interviews_collection.update_one(
                {"_id": session_obj_id},
                {"$push": {"questions_asked": {"question": next_question, "timestamp_asked": datetime.datetime.utcnow(), "response": None, "feedback_realtime": None, "mouth_detections": [], "pose_detections": []}}}
            )
        
        logger.info(f"Response processed for session {session_id}, Q{question_index}. Next question: {next_question[:50]}... Is session completed by AI: {is_session_completed_by_ai}")
        return jsonify({
            "status": "success",
            "message": "Respon diproses.",
            "real_time_feedback": real_time_feedback,
            "next_question": next_question,
            "visual_analysis": visual_analysis,
            "confidence": confidence['score'],
            "confidence_feedback": confidence['summary'],
            "is_session_completed": is_session_completed_by_ai,
            "current_question_index": question_index + 1 # Frontend uses this to know the next question to prepare for
        }), 200

    except errors.InvalidId:
        logger.warning(f"Invalid session ID format: {session_id}")
        return jsonify({"status": "fail", "message": "ID sesi tidak valid."}), 400
    except Exception as e:
        logger.error(f"Error processing AI interview response for user {current_user.get('username')} (Session {session_id}): {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Gagal memproses respon: {str(e)}"}), 500


@ai_interview_bp.route("/end_session", methods=["POST"])
@token_required
@require_api_key
def end_ai_interview_session(current_user):
    logger.info(f"End AI interview session hit by user: {current_user.get('username')}")
    interviews_collection = get_ai_interview_collections()
    data = request.get_json()
    session_id = data.get('session_id')

    if not session_id:
        logger.warning("Missing session_id for ending AI interview session.")
        return jsonify({"status": "fail", "message": "Session ID diperlukan."}), 400

    try:
        session_obj_id = ObjectId(session_id)
        session_doc = interviews_collection.find_one({"_id": session_obj_id, "user_id": current_user['_id']})

        if not session_doc:
            logger.warning(f"AI interview session {session_id} not found for user {current_user['_id']}.")
            return jsonify({"status": "fail", "message": "Sesi wawancara tidak ditemukan."}), 404

        if session_doc["status"] == "completed":
            logger.warning(f"Attempt to end already completed session {session_id}.")
            return jsonify({"status": "info", "message": "Sesi wawancara sudah berakhir."}), 200

        model = get_gemini_model()
        if not model:
            return jsonify({"status": "error", "message": "Gemini API tidak terkonfigurasi atau gagal diinisialisasi."}), 500

        conversation_history_for_gemini = []
        for qa in session_doc['questions_asked']:
            if qa.get('question'):
                conversation_history_for_gemini.append(f"Pewawancara: {qa['question']}")
            if qa.get('response'):
                conversation_history_for_gemini.append(f"Kandidat: {qa['response']}")
        
        full_conversation_text = "\n".join(conversation_history_for_gemini)
        
        # Prompt untuk feedback keseluruhan
        system_prompt = f"Anda adalah pewawancara HRD yang memberikan umpan balik menyeluruh pada sesi wawancara. Analisis performa kandidat berdasarkan percakapan berikut: '{full_conversation_text}'. Sertakan kekuatan, kelemahan, dan saran konkrit untuk perbaikan (minimal 3 poin). Berikan feedback yang profesional dan konstruktif. Mulai respons Anda dengan 'UMPAN BALIK KESELURUHAN:'."
        
        gemini_chat = model.start_chat(history=[{"role": "user", "parts": system_prompt}])
        overall_feedback_response = gemini_chat.send_message("Berikan umpan balik sekarang.")
        overall_feedback_text = overall_feedback_response.text.strip()

        # Hitung metrik agregat dari semua deteksi yang disimpan
        total_speaking_instances = 0
        total_leaning_instances = 0
        all_confidence_scores = []

        for qa in session_doc.get('questions_asked', []):
            # Hanya hitung jika ada jawaban dari user (berarti visual_analysis dilakukan)
            if qa.get('response'): 
                # Count speaking instances from `mouth_detections` list
                for mouth_det in qa.get('mouth_detections', []):
                    if mouth_det == 'bicara':
                        total_speaking_instances += 1
                
                # Count leaning instances from `pose_detections` list
                for pose_det in qa.get('pose_detections', []):
                    if pose_det in ['miring_kiri', 'miring_kanan']:
                        total_leaning_instances += 1
                
                # Collect confidence scores (per pertanyaan)
                if qa.get('confidence_score') is not None:
                    all_confidence_scores.append(qa['confidence_score'])

        average_confidence = sum(all_confidence_scores) / len(all_confidence_scores) if all_confidence_scores else 0

        start_time = session_doc['timestamp']
        end_time = datetime.datetime.utcnow()
        total_duration_seconds = int((end_time - start_time).total_seconds())

        interviews_collection.update_one(
            {"_id": session_obj_id, "user_id": current_user['_id']},
            {"$set": {
                "status": "completed",
                "overall_feedback": overall_feedback_text,
                "total_duration_seconds": total_duration_seconds,
                "average_confidence_score": average_confidence,
                "total_speaking_instances": total_speaking_instances, 
                "total_leaning_instances": total_leaning_instances,   
                "timestamp_ended": end_time
            }}
        )
        logger.info(f"AI interview session {session_id} completed for user {current_user.get('username')}.")
        return jsonify({
            "status": "success",
            "message": "Sesi wawancara berakhir.",
            "overall_feedback": overall_feedback_text,
            "session_id": session_id,
            "average_confidence_score": average_confidence,
            "total_duration_seconds": total_duration_seconds,
            "total_speaking_instances": total_speaking_instances, 
            "total_leaning_instances": total_leaning_instances    
        }), 200

    except errors.InvalidId:
        logger.warning(f"Invalid session ID format: {session_id}")
        return jsonify({"status": "fail", "message": "ID sesi tidak valid."}), 400
    except Exception as e:
        logger.error(f"Error ending AI interview session for user {current_user.get('username')} (Session {session_id}): {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Gagal mengakhiri sesi wawancara: {str(e)}"}), 500

@ai_interview_bp.route("/history", methods=["GET"])
@token_required
@require_api_key
def get_ai_interview_history(current_user):
    logger.info(f"Get AI interview history hit by user: {current_user.get('username')}")
    interviews_collection = get_ai_interview_collections()

    try:
        history = list(interviews_collection.find(
            {"user_id": current_user['_id'], "status": "completed"}
        ).sort("timestamp", -1).limit(10))

        formatted_history = []
        for session in history:
            formatted_history.append({
                "session_id": str(session['_id']),
                "category_name": session.get('category_name', 'N/A'),
                "timestamp": session['timestamp'].isoformat() if isinstance(session.get('timestamp'), datetime.datetime) else str(session.get('timestamp')),
                "total_questions": len(session.get('questions_asked', [])),
                "total_duration_seconds": session.get('total_duration_seconds', 0),
                "average_confidence_score": session.get('average_confidence_score', 0),
                "total_speaking_instances": session.get('total_speaking_instances', 0), 
                "total_leaning_instances": session.get('total_leaning_instances', 0),   
                "overall_feedback_summary": session.get('overall_feedback', '')[:100] + '...' if session.get('overall_feedback') else 'No feedback summary'
            })
        
        logger.debug(f"Retrieved {len(formatted_history)} AI interview sessions for user {current_user.get('username')}.")
        return jsonify({"status": "success", "history": formatted_history}), 200

    except Exception as e:
        logger.error(f"Error getting AI interview history for user {current_user.get('username')}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Gagal mengambil riwayat wawancara: {str(e)}"}), 500

@ai_interview_bp.route("/session/<session_id>", methods=["GET"])
@token_required
@require_api_key
def get_ai_interview_session_details(current_user, session_id):
    logger.info(f"Get AI interview session details hit for session {session_id} by user: {current_user.get('username')}")
    interviews_collection = get_ai_interview_collections()

    try:
        session_obj_id = ObjectId(session_id)
        session_doc = interviews_collection.find_one({"_id": session_obj_id, "user_id": current_user['_id']})

        if not session_doc:
            logger.warning(f"AI interview session {session_id} not found for user {current_user['_id']}.")
            return jsonify({"status": "fail", "message": "Sesi wawancara tidak ditemukan."}), 404

        session_doc['_id'] = str(session_doc['_id'])
        if 'timestamp' in session_doc and isinstance(session_doc['timestamp'], datetime.datetime):
            session_doc['timestamp'] = session_doc['timestamp'].isoformat()
        if 'timestamp_ended' in session_doc and isinstance(session_doc['timestamp_ended'], datetime.datetime):
            session_doc['timestamp_ended'] = session_doc['timestamp_ended'].isoformat()
        
        for q_idx, qa in enumerate(session_doc.get('questions_asked', [])):
            if 'timestamp_asked' in qa and isinstance(qa['timestamp_asked'], datetime.datetime):
                qa['timestamp_asked'] = qa['timestamp_asked'].isoformat()
            if 'timestamp_responded' in qa and isinstance(qa['timestamp_responded'], datetime.datetime):
                qa['timestamp_responded'] = qa['timestamp_responded'].isoformat()
        
        logger.debug(f"Retrieved details for AI interview session {session_id}.")
        return jsonify({"status": "success", "session": session_doc}), 200

    except errors.InvalidId:
        logger.warning(f"Invalid session ID format: {session_id}")
        return jsonify({"status": "fail", "message": "ID sesi tidak valid."}), 400
    except Exception as e:
        logger.error(f"Error getting AI interview session details for user {current_user.get('username')} (Session {session_id}): {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Gagal mengambil detail sesi: {str(e)}"}), 500