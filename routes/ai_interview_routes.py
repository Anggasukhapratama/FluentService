import os
import cv2
import json
import base64
import logging
import datetime
import tempfile
from bson import ObjectId, errors
from flask import Blueprint, request, jsonify, current_app

# Import dependensi proyek Anda
from database import get_collections
from auth_decorators import token_required, require_api_key
from config import GEMINI_API_KEY
from detectors.facial_expression_detector import detect_facial_expression
from detectors.mouth_detector import detect_mouth_status
from detectors.pose_detector import detect_pose_status

# Import dan Konfigurasi Gemini SDK
import google.generativeai as genai

# Inisialisasi Blueprint dan Logger
ai_interview_bp = Blueprint('ai_interview_bp', __name__, url_prefix='/api/ai_interview')
logger = logging.getLogger(__name__)

# Konfigurasi Gemini API Key
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("Google Gemini API berhasil dikonfigurasi.")
else:
    logger.error("GEMINI_API_KEY tidak ditemukan. Fungsi AI tidak akan bekerja.")

# Helper untuk mendapatkan koleksi database
def get_ai_interview_collections():
    cols = get_collections()
    return cols["interviews"]

# Helper untuk mendapatkan model Gemini
def get_gemini_model():
    if not GEMINI_API_KEY:
        return None
    try:
        # Menggunakan model flash yang lebih cepat, cocok untuk interaksi real-time
        return genai.GenerativeModel('gemini-1.5-flash-latest')
    except Exception as e:
        logger.error(f"Gagal menginisialisasi model Gemini: {e}")
        return None

# ==============================================================================
# FUNGSI KALKULASI SKOR KEPERCAYAAN DIRI
# ==============================================================================
def calculate_confidence_score(pose_status, expression_status, real_time_gemini_feedback):
    score = 0
    feedback_points = []

    # 1. Poin dari Isyarat Visual
    if pose_status == "lurus":
        score += 30
        feedback_points.append("Postur tubuh Anda terlihat tegak dan profesional.")
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
        feedback_points.append("Ekspresi Anda terlihat sedikit tegang atau gugup.")
    elif expression_status in ["sedih", "marah", "terkejut"]:
        score -= 10
        feedback_points.append(f"Ekspresi Anda ({expression_status}) mungkin kurang sesuai untuk konteks wawancara.")
    else:
        feedback_points.append("Ekspresi wajah tidak terdeteksi.")

    # 2. Poin dari Isyarat Linguistik (Umpan Balik Gemini)
    feedback_lower = real_time_gemini_feedback.lower()
    
    if "jelas" in feedback_lower or "baik" in feedback_lower or "bagus" in feedback_lower or "terstruktur" in feedback_lower:
        score += 25
        feedback_points.append("Jawaban Anda terdengar jelas dan terstruktur dengan baik.")
    if "relevan" in feedback_lower:
        score += 15
        feedback_points.append("Jawaban Anda sangat relevan dengan pertanyaan yang diajukan.")
    
    # Penalti
    if "ragu" in feedback_lower or "kurang yakin" in feedback_lower:
        score -= 15
        feedback_points.append("Terdapat indikasi keraguan dalam cara Anda menjawab.")
    if "kata pengisi" in feedback_lower or "umm" in feedback_lower or "ehh" in feedback_lower:
        score -= 10
        feedback_points.append("Perhatikan penggunaan kata-kata pengisi (filler words).")
    if "tidak relevan" in feedback_lower or "melenceng" in feedback_lower:
        score -= 20
        feedback_points.append("Jawaban Anda kurang relevan dengan pertanyaan.")

    # Normalisasi skor antara 0 dan 100
    score = max(0, min(100, score))

    # Ringkasan umpan balik kepercayaan diri
    if score >= 80:
        summary = "Sangat Baik! Tingkat kepercayaan diri Anda sangat tinggi dan meyakinkan."
    elif score >= 60:
        summary = "Baik. Anda menunjukkan kepercayaan diri yang cukup, ada sedikit ruang untuk peningkatan."
    elif score >= 40:
        summary = "Cukup. Kepercayaan diri Anda perlu ditingkatkan. Cobalah untuk lebih yakin dengan jawaban Anda."
    else:
        summary = "Perlu Perbaikan. Tingkat kepercayaan diri Anda tampak rendah. Perbanyak latihan akan sangat membantu."

    return {"score": score, "feedback_points": feedback_points, "summary": summary}

# ==============================================================================
# ENDPOINT API
# ==============================================================================

@ai_interview_bp.route("/start_session", methods=["POST"])
@token_required
@require_api_key
def start_ai_interview_session(current_user):
    """
    Memulai sesi wawancara AI baru berdasarkan topik yang diberikan pengguna.
    AI akan menghasilkan 5 pertanyaan di awal sesi.
    """
    logger.info(f"Permintaan memulai sesi wawancara AI oleh pengguna: {current_user.get('username')}")
    data = request.get_json()
    custom_topic = data.get('custom_topic')

    if not custom_topic or not isinstance(custom_topic, str) or len(custom_topic.strip()) < 5:
        return jsonify({"status": "fail", "message": "Topik wawancara tidak valid. Harap masukkan topik yang spesifik (minimal 5 karakter)."}), 400

    model = get_gemini_model()
    if not model:
        return jsonify({"status": "error", "message": "Layanan AI tidak terkonfigurasi dengan benar."}), 500

    try:
        # Prompt baru untuk menghasilkan 5 pertanyaan dalam format JSON
        generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
        prompt = f"""
        Anda adalah seorang ahli perekrutan HRD. Berdasarkan topik wawancara dari kandidat, buatlah 5 pertanyaan wawancara yang relevan dan mendalam.
        Topik dari kandidat: "{custom_topic}"
        
        Tugas Anda: Hasilkan sebuah array JSON yang valid berisi 5 string pertanyaan dalam Bahasa Indonesia.
        Pastikan output Anda HANYA berupa array JSON, tanpa teks atau format tambahan.
        """
        
        response = model.generate_content(prompt, generation_config=generation_config)
        questions_list = json.loads(response.text)

        if not isinstance(questions_list, list) or len(questions_list) == 0:
            raise ValueError("AI tidak mengembalikan daftar pertanyaan yang valid.")

        # Siapkan data pertanyaan untuk disimpan di database
        questions_to_store = [{"question": q} for q in questions_list]

        session_data = {
            "user_id": current_user['_id'],
            "username": current_user['username'],
            "timestamp": datetime.datetime.utcnow(),
            "category_name": custom_topic.strip(),
            "status": "in_progress",
            "questions_asked": questions_to_store,
            "overall_feedback": None,
            "total_duration_seconds": 0
        }
        insert_result = get_ai_interview_collections().insert_one(session_data)
        session_id = str(insert_result.inserted_id)

        logger.info(f"Sesi wawancara AI {session_id} dimulai untuk {current_user['username']} dengan topik '{custom_topic}'.")
        return jsonify({
            "status": "success",
            "message": "Sesi wawancara dimulai.",
            "session_id": session_id,
            "questions": questions_list  # Kirim semua pertanyaan ke frontend
        }), 201

    except json.JSONDecodeError:
        logger.error(f"Gagal mem-parsing JSON dari AI untuk topik '{custom_topic}'. Respons: {response.text}")
        return jsonify({"status": "error", "message": "Gagal menghasilkan pertanyaan. Format dari AI tidak valid. Coba topik lain."}), 500
    except Exception as e:
        logger.error(f"Error saat memulai sesi wawancara AI: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Terjadi kesalahan internal: {str(e)}"}), 500



@ai_interview_bp.route("/analyze_frame", methods=["POST"])
@token_required
@require_api_key
def analyze_realtime_frame(current_user):
    """
    Endpoint ringan yang HANYA menerima satu frame gambar,
    melakukan deteksi visual, dan mengembalikan hasilnya.
    Didesain untuk dipanggil secara berulang oleh frontend.
    """
    data = request.get_json()
    frame_base64 = data.get('frame')

    if not frame_base64:
        return jsonify({"status": "fail", "message": "Frame gambar tidak ditemukan."}), 400

    image_path = None
    try:
        # Simpan frame ke file temporer untuk diproses
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            image_path = tmp.name
            tmp.write(base64.b64decode(frame_base64))
        
        # Jalankan semua detektor visual
        analysis_results = {
            "pose": detect_pose_status(image_path),
            "mouth": detect_mouth_status(image_path),
            "expression": detect_facial_expression(image_path)
        }
        
        # Tidak perlu logging di sini untuk menghindari spam log
        # logger.debug(f"Analisis frame real-time untuk {current_user['username']}: {analysis_results}")

        return jsonify({
            "status": "success",
            "analysis": analysis_results
        }), 200

    except Exception as e:
        # Hanya log error jika benar-benar terjadi masalah
        logger.error(f"Error pada analisis frame real-time: {e}", exc_info=False)
        return jsonify({"status": "error", "message": "Gagal menganalisis frame."}), 500
    finally:
        # Pastikan file temporer selalu dihapus
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

@ai_interview_bp.route("/process_response", methods=["POST"])
@token_required
@require_api_key
def process_ai_interview_response(current_user):
    """
    Memproses jawaban pengguna, melakukan analisis visual, dan mendapatkan umpan balik dari AI.
    """
    logger.info(f"Memproses respons wawancara dari pengguna: {current_user.get('username')}")
    data = request.get_json()
    session_id, response_text, frame_base64, question_index = (
        data.get('session_id'), data.get('response_text'),
        data.get('frame'), data.get('question_index')
    )

    if not all([session_id, response_text, frame_base64 is not None, question_index is not None]):
        return jsonify({"status": "fail", "message": "Data tidak lengkap untuk memproses respons."}), 400

    try:
        session_obj_id = ObjectId(session_id)
        session_doc = get_ai_interview_collections().find_one({"_id": session_obj_id, "user_id": current_user['_id']})

        if not session_doc:
            return jsonify({"status": "fail", "message": "Sesi wawancara tidak ditemukan."}), 404
        if session_doc["status"] != "in_progress":
            return jsonify({"status": "fail", "message": "Sesi wawancara ini sudah berakhir."}), 400
        if question_index >= len(session_doc.get('questions_asked', [])):
            return jsonify({"status": "fail", "message": "Indeks pertanyaan tidak valid."}), 400

        # --- 1. Analisis Visual ---
        image_path = None
        visual_analysis = {"pose": "tidak terdeteksi", "mouth": "tidak terdeteksi", "expression": "tidak terdeteksi"}
        
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                image_path = tmp.name
                tmp.write(base64.b64decode(frame_base64))
            
            visual_analysis = {
                "pose": detect_pose_status(image_path),
                "mouth": detect_mouth_status(image_path),
                "expression": detect_facial_expression(image_path)
            }
            logger.debug(f"Hasil analisis visual untuk sesi {session_id}: {visual_analysis}")
        except Exception as e:
            logger.error(f"Gagal melakukan analisis visual pada gambar: {e}", exc_info=True)
        finally:
            if image_path and os.path.exists(image_path):
                os.unlink(image_path)

        # --- 2. Analisis Jawaban dengan AI (Hanya untuk Umpan Balik) ---
        model = get_gemini_model()
        if not model:
            return jsonify({"status": "error", "message": "Layanan AI tidak tersedia."}), 500

        current_question_text = session_doc['questions_asked'][question_index]['question']
        feedback_prompt = f"""
        Anda adalah seorang HRD profesional. Berikan umpan balik singkat (1-2 kalimat) yang konstruktif untuk jawaban kandidat.
        Pertanyaan: "{current_question_text}"
        Jawaban Kandidat: "{response_text}"
        Fokus pada kejelasan, relevansi, dan struktur jawaban. Output HANYA teks umpan balik.
        """
        response_from_gemini = model.generate_content(feedback_prompt)
        real_time_feedback = response_from_gemini.text.strip()
        
        # --- 3. Kalkulasi Skor Kepercayaan Diri ---
        confidence = calculate_confidence_score(visual_analysis['pose'], visual_analysis['expression'], real_time_feedback)
        
        # --- 4. Update Database ---
        update_prefix = f"questions_asked.{question_index}"
        update_operation = {"$set": {
            f"{update_prefix}.response": response_text,
            f"{update_prefix}.timestamp_responded": datetime.datetime.utcnow(),
            f"{update_prefix}.feedback_realtime": real_time_feedback,
            f"{update_prefix}.visual_analysis": visual_analysis,
            f"{update_prefix}.confidence_score": confidence['score'],
            f"{update_prefix}.confidence_feedback": confidence['summary'],
            # Simpan deteksi individual jika diperlukan untuk analisis lebih lanjut
            f"{update_prefix}.pose_detection": visual_analysis['pose'],
            f"{update_prefix}.mouth_detection": visual_analysis['mouth']
        }}
        get_ai_interview_collections().update_one({"_id": session_obj_id}, update_operation)

        is_last_question = (question_index + 1) >= len(session_doc['questions_asked'])
        
        return jsonify({
            "status": "success",
            "message": "Respon berhasil diproses.",
            "real_time_feedback": real_time_feedback,
            "visual_analysis": visual_analysis,
            "confidence": confidence['score'],
            "confidence_feedback": confidence['summary'],
            "is_session_completed": is_last_question
        }), 200

    except errors.InvalidId:
        return jsonify({"status": "fail", "message": "Format ID sesi tidak valid."}), 400
    except Exception as e:
        logger.error(f"Error saat memproses respons wawancara: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Terjadi kesalahan internal saat memproses jawaban: {str(e)}"}), 500


@ai_interview_bp.route("/end_session", methods=["POST"])
@token_required
@require_api_key
def end_ai_interview_session(current_user):
    """
    Mengakhiri sesi wawancara, menghasilkan umpan balik keseluruhan, dan menghitung metrik akhir.
    """
    logger.info(f"Permintaan mengakhiri sesi wawancara oleh pengguna: {current_user.get('username')}")
    data = request.get_json()
    session_id = data.get('session_id')

    if not session_id:
        return jsonify({"status": "fail", "message": "ID Sesi diperlukan."}), 400

    try:
        session_obj_id = ObjectId(session_id)
        session_doc = get_ai_interview_collections().find_one({"_id": session_obj_id, "user_id": current_user['_id']})

        if not session_doc:
            return jsonify({"status": "fail", "message": "Sesi wawancara tidak ditemukan."}), 404
        if session_doc.get("status") == "completed":
            return jsonify({"status": "info", "message": "Sesi ini sudah pernah diakhiri."}), 200

        # --- 1. Hasilkan Umpan Balik Keseluruhan dari AI ---
        model = get_gemini_model()
        if not model:
            return jsonify({"status": "error", "message": "Layanan AI tidak tersedia untuk memberikan ringkasan."}), 500

        conversation_history = []
        for qa in session_doc.get('questions_asked', []):
            if qa.get('question') and qa.get('response'):
                conversation_history.append(f"Pewawancara: {qa['question']}")
                conversation_history.append(f"Kandidat: {qa['response']}\n")
        
        full_conversation_text = "\n".join(conversation_history)
        
        overall_feedback_prompt = f"""
        Anda adalah seorang manajer HRD yang memberikan umpan balik akhir setelah wawancara.
        Analisis seluruh percakapan berikut:
        ---
        {full_conversation_text}
        ---
        Berikan umpan balik menyeluruh yang mencakup:
        1.  Kekuatan utama kandidat.
        2.  Area yang perlu ditingkatkan.
        3.  Saran konkret untuk perbaikan di masa depan.
        Buatlah dalam format paragraf yang mudah dibaca dan profesional.
        """
        
        overall_feedback_response = model.generate_content(overall_feedback_prompt)
        overall_feedback_text = overall_feedback_response.text.strip()

        # --- 2. Hitung Metrik Agregat ---
        all_confidence_scores = [qa['confidence_score'] for qa in session_doc.get('questions_asked', []) if qa.get('confidence_score') is not None]
        total_speaking_instances = sum(1 for qa in session_doc.get('questions_asked', []) if qa.get('mouth_detection') == 'bicara')
        total_leaning_instances = sum(1 for qa in session_doc.get('questions_asked', []) if qa.get('pose_detection') in ['miring_kiri', 'miring_kanan'])
        
        average_confidence = sum(all_confidence_scores) / len(all_confidence_scores) if all_confidence_scores else 0
        end_time = datetime.datetime.utcnow()
        total_duration_seconds = int((end_time - session_doc['timestamp']).total_seconds())

        # --- 3. Update Database ---
        get_ai_interview_collections().update_one(
            {"_id": session_obj_id},
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
        logger.info(f"Sesi wawancara AI {session_id} untuk {current_user['username']} telah selesai.")
        
        return jsonify({
            "status": "success",
            "message": "Sesi wawancara berhasil diakhiri.",
            "overall_feedback": overall_feedback_text,
            "average_confidence_score": average_confidence,
            "total_duration_seconds": total_duration_seconds,
            "total_speaking_instances": total_speaking_instances,
            "total_leaning_instances": total_leaning_instances
        }), 200

    except errors.InvalidId:
        return jsonify({"status": "fail", "message": "Format ID sesi tidak valid."}), 400
    except Exception as e:
        logger.error(f"Error saat mengakhiri sesi wawancara: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Terjadi kesalahan internal saat mengakhiri sesi: {str(e)}"}), 500




@ai_interview_bp.route("/history", methods=["GET"])
@token_required
@require_api_key
def get_ai_interview_history(current_user):
    """
    Mengambil riwayat sesi wawancara yang telah selesai untuk pengguna saat ini.
    """
    try:
        history_cursor = get_ai_interview_collections().find(
            {"user_id": current_user['_id'], "status": "completed"}
        ).sort("timestamp", -1).limit(20)

        formatted_history = []
        for session in history_cursor:
            summary = session.get('overall_feedback', '')
            formatted_history.append({
                "session_id": str(session['_id']),
                "category_name": session.get('category_name', 'N/A'),
                "timestamp": session['timestamp'].isoformat(),
                "total_questions": len(session.get('questions_asked', [])),
                "total_duration_seconds": session.get('total_duration_seconds', 0),
                "average_confidence_score": session.get('average_confidence_score', 0),
                "overall_feedback_summary": summary[:120] + '...' if len(summary) > 120 else summary
            })
        
        return jsonify({"status": "success", "history": formatted_history}), 200
    except Exception as e:
        logger.error(f"Error mengambil riwayat wawancara untuk {current_user['username']}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Gagal mengambil riwayat wawancara."}), 500


@ai_interview_bp.route("/session/<session_id>", methods=["GET"])
@token_required
@require_api_key
def get_ai_interview_session_details(current_user, session_id):
    """
    Mengambil detail lengkap dari satu sesi wawancara.
    """
    try:
        session_obj_id = ObjectId(session_id)
        session_doc = get_ai_interview_collections().find_one({"_id": session_obj_id, "user_id": current_user['_id']})

        if not session_doc:
            return jsonify({"status": "fail", "message": "Sesi wawancara tidak ditemukan."}), 404

        # Konversi ObjectId dan datetime ke string agar dapat di-serialisasi JSON
        session_doc['_id'] = str(session_doc['_id'])
        session_doc['user_id'] = str(session_doc['user_id'])
        if 'timestamp' in session_doc: session_doc['timestamp'] = session_doc['timestamp'].isoformat()
        if 'timestamp_ended' in session_doc: session_doc['timestamp_ended'] = session_doc['timestamp_ended'].isoformat()
        
        for qa in session_doc.get('questions_asked', []):
            if 'timestamp_responded' in qa and qa['timestamp_responded']:
                qa['timestamp_responded'] = qa['timestamp_responded'].isoformat()

        return jsonify({"status": "success", "session": session_doc}), 200
    except errors.InvalidId:
        return jsonify({"status": "fail", "message": "Format ID sesi tidak valid."}), 400
    except Exception as e:
        logger.error(f"Error mengambil detail sesi {session_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Gagal mengambil detail sesi."}), 500