from flask import Blueprint, request, jsonify
from database import get_collections
from auth_decorators import token_required, require_api_key
from datetime import datetime
from bson import ObjectId
import logging

chat_bp = Blueprint('chat_bp', __name__)
logger = logging.getLogger(__name__)

# Access collections
def get_chat_collections():
    cols = get_collections()
    return cols["topics"], cols["messages"]

@chat_bp.route("/api/chat/topics", methods=["POST"])
@token_required
@require_api_key
def create_chat_topic(current_user):
    logger.info(f"Create chat topic endpoint hit by user: {current_user.get('username')}")
    topics_collection, _ = get_chat_collections()
    data = request.get_json()
    topic_name = data.get('name')

    if not topic_name or not topic_name.strip():
        logger.warning("Topic name is empty for creation.")
        return jsonify({"status": "fail", "message": "Nama topik tidak boleh kosong"}), 400
    
    topic_id = topic_name.lower().replace(' ', '_').replace('.', '').replace(',', '').strip()
    
    if topics_collection.find_one({"_id": topic_id}):
        logger.warning(f"Topic with ID '{topic_id}' already exists.")
        return jsonify({"status": "fail", "message": "Topik dengan nama ini sudah ada, coba nama lain"}), 409

    try:
        topic_data = {
            "_id": topic_id,
            "name": topic_name,
            "createdAt": datetime.utcnow()
        }
        topics_collection.insert_one(topic_data)
        logger.info(f"New chat topic '{topic_name}' created by {current_user['username']}.")
        return jsonify({
            "status": "success",
            "message": "Topik berhasil dibuat",
            "topic": {"id": topic_id, "name": topic_name}
        }), 201
    except Exception as e:
        logger.error(f"Error creating chat topic for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Terjadi kesalahan saat membuat topik: {str(e)}"}), 500


@chat_bp.route("/api/chat/topics", methods=["GET"])
@token_required
@require_api_key
def get_chat_topics(current_user):
    logger.info(f"Get chat topics endpoint hit by user: {current_user.get('username')}")
    topics_collection, _ = get_chat_collections()
    try:
        topics = list(topics_collection.find({}, {"_id": 1, "name": 1}))
        # Tambahkan topik default jika belum ada
        if not topics_collection.find_one({"_id": "global_discussion"}):
            topics_collection.insert_one({"_id": "global_discussion", "name": "Global Discussion"})
            topics.append({"_id": "global_discussion", "name": "Global Discussion"})
        
        topics.sort(key=lambda x: (x['_id'] != "global_discussion", x['name'].lower()))

        formatted_topics = [{"id": str(t['_id']), "name": t['name']} for t in topics]
        logger.debug(f"Retrieved {len(formatted_topics)} chat topics.")
        return jsonify({"status": "success", "topics": formatted_topics}), 200
    except Exception as e:
        logger.error(f"Error getting chat topics for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Failed to load topics: {str(e)}"}), 500

@chat_bp.route("/api/chat/send_message", methods=["POST"])
@token_required
@require_api_key
def send_chat_message(current_user):
    logger.info(f"Send chat message endpoint hit by user: {current_user.get('username')}")
    _, messages_collection = get_chat_collections()
    data = request.get_json()
    message_content = data.get('message')
    room_id = data.get('room_id', 'global_discussion')
    
    replied_to_message_id = data.get('replied_to_message_id')
    replied_to_message_content = data.get('replied_to_message_content')
    replied_to_sender_username = data.get('replied_to_sender_username')

    if not message_content:
        logger.warning("Chat message content is empty.")
        return jsonify({"status": "fail", "message": "Message content cannot be empty"}), 400

    message_data = {
        'sender_id': str(current_user['_id']),
        'sender_username': current_user['username'],
        'content': message_content,
        'timestamp': datetime.utcnow(),
        'room_id': room_id,
    }

    if replied_to_message_id:
        message_data['replied_to_message_id'] = replied_to_message_id
        message_data['replied_to_message_content'] = replied_to_message_content
        message_data['replied_to_sender_username'] = replied_to_sender_username

    try:
        result = messages_collection.insert_one(message_data)
        logger.debug(f"Chat: Message from {current_user['username']} to room {room_id} saved.")
        return jsonify({
            "status": "success",
            "message": "Message sent",
            "sent_message": {
                'id': str(result.inserted_id),
                'sender_id': str(current_user['_id']),
                'sender_username': current_user['username'],
                'content': message_content,
                'timestamp': datetime.utcnow().isoformat(),
                'room_id': room_id,
                'replied_to_message_id': replied_to_message_id,
                'replied_to_message_content': replied_to_message_content,
                'replied_to_sender_username': replied_to_sender_username,
            }
        }), 201
    except Exception as e:
        logger.error(f"Chat: Error saving message for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Failed to send message: {str(e)}"}), 500

@chat_bp.route("/api/chat/messages", methods=["GET"])
@token_required
@require_api_key
def get_chat_messages(current_user):
    logger.info(f"Get chat messages endpoint hit by user: {current_user.get('username')}")
    _, messages_collection = get_chat_collections()
    topic_id = request.args.get('topic_id', 'global_discussion')
    limit = int(request.args.get('limit', 50))

    query = {'room_id': topic_id}

    try:
        messages_cursor = messages_collection.find(query).sort('timestamp', 1).limit(limit)

        formatted_messages = []
        for msg in messages_cursor:
            formatted_messages.append({
                'id': str(msg['_id']),
                'sender_id': msg['sender_id'],
                'sender_username': msg['sender_username'],
                'content': msg['content'],
                'timestamp': msg['timestamp'].isoformat(),
                'room_id': msg['room_id'],
                'replied_to_message_id': msg.get('replied_to_message_id'),
                'replied_to_message_content': msg.get('replied_to_message_content'),
                'replied_to_sender_username': msg.get('replied_to_sender_username'),
            })

        logger.debug(f"Chat: Loaded {len(formatted_messages)} messages for topic {topic_id} for user {current_user.get('username')}.")
        return jsonify({"status": "success", "messages": formatted_messages}), 200
    except Exception as e:
        logger.error(f"Chat: Error loading messages for user {current_user.get('username')}: {e}")
        return jsonify({"status": "error", "message": f"Failed to load messages: {str(e)}"}), 500

@chat_bp.route("/api/chat/messages/<message_id>",methods=["DELETE"])
@token_required
@require_api_key
def delete_chat_message(current_user, message_id):
    logger.info(f"Delete chat message endpoint hit for message {message_id} by user: {current_user.get('username')}")
    _, messages_collection = get_chat_collections()
    
    if not ObjectId.is_valid(message_id):
        logger.warning(f"Delete chat message failed: Invalid Message ID format '{message_id}'.")
        return jsonify({"status": "fail", "message": "Format ID Pesan tidak valid"}), 400

    try:
        message_obj_id = ObjectId(message_id)
        user_sender_id_str = str(current_user['_id'])

        logger.debug(f"Attempting to delete message_id: {message_obj_id} by user_id_str: {user_sender_id_str}")

        result = messages_collection.delete_one({
            "_id": message_obj_id,
            "sender_id": user_sender_id_str
        })

        if result.deleted_count > 0:
            logger.info(f"Chat: Message {message_id} deleted successfully by {current_user['username']}")
            return jsonify({"status": "success", "message": "Pesan berhasil dihapus"}), 200
        else:
            message_found_but_not_owned = messages_collection.find_one({"_id": message_obj_id})
            if message_found_but_not_owned:
                logger.warning(f"User {current_user['username']} unauthorized to delete message {message_id}. Message owner: {message_found_but_not_owned.get('sender_id')}, Requester: {user_sender_id_str}")
                return jsonify({"status": "fail", "message": "Anda tidak diizinkan menghapus pesan ini"}), 403
            else:
                logger.warning(f"Chat: Message {message_id} not found for deletion.")
                return jsonify({"status": "fail", "message": "Pesan tidak ditemukan"}), 404

    except Exception as e:
        logger.error(f"Chat: Error deleting message {message_id} for user {current_user.get('username')}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Terjadi kesalahan saat menghapus pesan: {str(e)}"}), 500
