from datetime import datetime
from bson import ObjectId
from gtts import gTTS
import os
import tempfile
import base64
from textblob import TextBlob
from db import questions_collection, interview_sessions_collection

class InterviewService:
    @staticmethod
    def start_interview(user_id, category="general"):
        questions = list(questions_collection.aggregate([
            {"$match": {"category": category}},
            {"$sample": {"size": 5}}
        ]))
        
        if not questions:
            return None
        
        session_data = {
            "user_id": ObjectId(user_id),
            "start_time": datetime.now(),
            "status": "ongoing",
            "questions": [{
                "question_id": q["_id"],
                "question_text": q["question"],
                "ideal_keywords": q.get("ideal_answer_keywords", []),
                "user_answer": None,
                "evaluation": None
            } for q in questions],
            "current_question_index": 0,
            "category": category
        }
        
        session_id = interview_sessions_collection.insert_one(session_data).inserted_id
        return str(session_id), session_data
    
    @staticmethod
    def get_question_audio(question_id):
        question = questions_collection.find_one({"_id": ObjectId(question_id)})
        if not question:
            return None
        
        tts = gTTS(text=question["question"], lang='id')
        temp_path = os.path.join(tempfile.gettempdir(), f"q_{question_id}.mp3")
        tts.save(temp_path)
        
        with open(temp_path, 'rb') as f:
            audio_data = f.read()
        
        os.remove(temp_path)
        return base64.b64encode(audio_data).decode('utf-8')
    
    @staticmethod
    def submit_answer(session_id, answer_text):
        session = interview_sessions_collection.find_one({"_id": ObjectId(session_id)})
        if not session:
            return None
        
        current_idx = session["current_question_index"]
        if current_idx >= len(session["questions"]):
            return None
        
        evaluation = InterviewService._evaluate_answer(
            answer_text,
            session["questions"][current_idx]["ideal_keywords"]
        )
        
        update_data = {
            f"questions.{current_idx}.user_answer": answer_text,
            f"questions.{current_idx}.evaluation": evaluation,
            "current_question_index": current_idx + 1
        }
        
        if current_idx + 1 >= len(session["questions"]):
            update_data.update({
                "status": "completed",
                "end_time": datetime.now(),
                "overall_score": InterviewService._calculate_overall_score(session["questions"])
            })
        
        interview_sessions_collection.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": update_data}
        )
        
        return evaluation, update_data.get("overall_score")
    
    @staticmethod
    def _evaluate_answer(user_answer, ideal_keywords):
        user_answer_lower = user_answer.lower()
        matched_keywords = [kw for kw in ideal_keywords if kw.lower() in user_answer_lower]
        keyword_score = len(matched_keywords) / len(ideal_keywords) * 100 if ideal_keywords else 0
        
        blob = TextBlob(user_answer)
        sentiment_score = (blob.sentiment.polarity + 1) * 50
        
        final_score = (keyword_score * 0.7) + (sentiment_score * 0.3)
        
        return {
            "matched_keywords": matched_keywords,
            "keyword_score": round(keyword_score, 2),
            "sentiment_score": round(sentiment_score, 2),
            "overall_score": round(final_score, 2),
            "feedback": InterviewService._generate_feedback(final_score, matched_keywords, ideal_keywords)
        }
    
    @staticmethod
    def _generate_feedback(score, matched_keywords, ideal_keywords):
        if score >= 80:
            return "Jawaban sangat baik! Anda menyentuh hampir semua poin penting."
        elif score >= 60:
            missing = [kw for kw in ideal_keywords if kw not in matched_keywords]
            return f"Jawaban cukup baik. Pertimbangkan untuk menyertakan: {', '.join(missing)}"
        else:
            return "Jawaban perlu diperbaiki. Pastikan memahami pertanyaan dan menyertakan poin-poin kunci."
    
    @staticmethod
    def _calculate_overall_score(questions):
        total = sum(q.get("evaluation", {}).get("overall_score", 0) for q in questions)
        count = len([q for q in questions if q.get("evaluation")])
        return round(total / count, 2) if count > 0 else 0
    
    @staticmethod
    def get_results(session_id):
        session = interview_sessions_collection.find_one({"_id": ObjectId(session_id)})
        if not session or session["status"] != "completed":
            return None
        
        return {
            "session_id": str(session["_id"]),
            "user_id": str(session["user_id"]),
            "start_time": session["start_time"],
            "end_time": session.get("end_time"),
            "overall_score": session.get("overall_score", 0),
            "questions": session["questions"]
        }