import os
import sys
import time
import random
import threading
from collections import deque
from flask import Flask, send_from_directory, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS

# === SAFE IMPORTS FOR CV/ML ===
try:
    import cv2
    import numpy as np
    import mediapipe as mp
    from scipy.signal import butter, filtfilt, find_peaks
    LIBRARIES_AVAILABLE = True
    print("✅ CV/ML libraries loaded successfully.")
except ImportError as e:
    LIBRARIES_AVAILABLE = False
    print(f"⚠️ CV/ML LIBRARY MISSING: {e}")

# === DEEPFACE IMPORT (OPTIONAL) ===
try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
    print("✅ DeepFace loaded successfully.")
except ImportError as e:
    DEEPFACE_AVAILABLE = False
    print(f"⚠️ DeepFace not available: {e}")

# === AUDIO PIPELINE IMPORTS ===
AUDIO_PIPELINE_AVAILABLE = False
try:
    # Add audio_pipeline to path if it exists
    audio_pipeline_path = os.path.join(os.path.dirname(__file__), 'audio_pipeline')
    if os.path.exists(audio_pipeline_path):
        sys.path.insert(0, audio_pipeline_path)
        
        # Try importing audio pipeline modules
        from transcribe_whisper import WhisperTranscriber
        from text_emotion_distilbert import EmotionAnalyzer
        AUDIO_PIPELINE_AVAILABLE = True
        print("✅ Audio pipeline modules loaded successfully.")
except ImportError as e:
    print(f"⚠️ Audio pipeline not available: {e}")
    print("💡 Using basic transcription fallback")

# --- CONFIGURATION ---
app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    max_http_buffer_size=1e8  # 100MB for audio chunks
)

# === SESSION MANAGER ===
class SessionManager:
    def __init__(self):
        self.sessions = {}  # session_id -> {users: [], room_id: str, analyzer: RobustAnalyzer}
        self.waiting_users = []  # Users waiting for match
        
    def add_waiting_user(self, user_id, socket_id):
        self.waiting_users.append({'user_id': user_id, 'socket_id': socket_id})
        print(f"👤 User {user_id} added to waiting queue")
        
        # Try to match if 2+ users waiting
        if len(self.waiting_users) >= 2:
            self.create_session()
    
    def create_session(self):
        if len(self.waiting_users) < 2:
            return None
        
        user1 = self.waiting_users.pop(0)
        user2 = self.waiting_users.pop(0)
        
        room_id = f"room-{int(time.time())}-{random.randint(1000, 9999)}"
        
        session = {
            'users': [user1, user2],
            'room_id': room_id,
            'created_at': time.time(),
            'transcript': []
        }
        
        self.sessions[room_id] = session
        
        # Notify both users
        for user in [user1, user2]:
            socketio.emit('match-found', {
                'roomId': room_id,
                'timestamp': time.time()
            }, room=user['socket_id'])
        
        print(f"🎯 Session created: {room_id}")
        return room_id
    
    def get_session(self, room_id):
        return self.sessions.get(room_id)
    
    def remove_session(self, room_id):
        if room_id in self.sessions:
            del self.sessions[room_id]
            print(f"🗑️ Session removed: {room_id}")

session_manager = SessionManager()

class RobustAnalyzer:
    def __init__(self):
        self.fs = 30
        self.buffer = deque(maxlen=self.fs * 10)
        self.signal_buffer = deque(maxlen=self.fs * 10)
        self.running = False
        self.use_deepface = DEEPFACE_AVAILABLE
        
        # Audio transcription
        self.audio_transcriber = None
        self.emotion_analyzer = None
        
        if AUDIO_PIPELINE_AVAILABLE:
            try:
                self.audio_transcriber = WhisperTranscriber()
                self.emotion_analyzer = EmotionAnalyzer()
                print("✅ Audio transcriber and emotion analyzer initialized")
            except Exception as e:
                print(f"⚠️ Failed to initialize audio pipeline: {e}")
        
        # Initialize CV/ML components if available
        if LIBRARIES_AVAILABLE:
            try:
                self.mp_face_mesh = mp.solutions.face_mesh
                self.face_mesh = self.mp_face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=1,
                    refine_landmarks=False,
                    min_detection_confidence=0.6,
                    min_tracking_confidence=0.6
                )
                print(f"✅ MediaPipe Face Mesh initialized")
            except Exception as e:
                print(f"⚠️ MediaPipe initialization failed: {e}")
                self.face_mesh = None
        else:
            self.face_mesh = None
        
        # Current analysis values
        self.current_hr = 70
        self.current_emotion = "Neutral"
        self.current_emotions = {
            'Happiness/Joy': 0,
            'Trust': 50,
            'Fear/FOMO': 0,
            'Surprise': 0,
            'Anger': 0
        }
        self.gaze_x = 50
        self.gaze_y = 50
        
        # DeepFace processing optimization
        self.last_deepface_time = 0
        self.deepface_interval = 0.5
    
    # === AUDIO TRANSCRIPTION ===
    def transcribe_audio(self, audio_data):
        """Transcribe audio using Whisper"""
        if self.audio_transcriber:
            try:
                text = self.audio_transcriber.transcribe(audio_data)
                return text
            except Exception as e:
                print(f"Transcription error: {e}")
        return None
    
    def analyze_text_emotion(self, text):
        """Analyze emotion from text"""
        if self.emotion_analyzer:
            try:
                emotions = self.emotion_analyzer.analyze(text)
                return emotions
            except Exception as e:
                print(f"Text emotion analysis error: {e}")
        return None
    
    # === HEART RATE PROCESSING ===
    def bandpass_filter(self, signal, fs=30, low=0.7, high=3.5):
        """Bandpass filter for heart rate detection"""
        try:
            nyquist = fs / 2
            low_norm = low / nyquist
            high_norm = high / nyquist
            
            if low_norm >= 1 or high_norm >= 1:
                return signal
                
            b, a = butter(3, [low_norm, high_norm], btype="band")
            return filtfilt(b, a, signal)
        except:
            return signal
    
    def calculate_heart_rate(self, signal):
        """Calculate heart rate from signal buffer"""
        if len(signal) < self.fs * 6:
            return None
        
        try:
            sig_array = np.array(signal)
            sig_array = sig_array - np.mean(sig_array)
            std_val = np.std(sig_array)
            if std_val == 0:
                return None
            sig_array = sig_array / std_val
            
            filtered = self.bandpass_filter(sig_array, self.fs)
            prominence = np.std(filtered) * 0.3
            peaks, _ = find_peaks(filtered, distance=self.fs//2, prominence=prominence)
            
            if len(peaks) >= 4:
                intervals = np.diff(peaks) / self.fs
                q1, q3 = np.percentile(intervals, [25, 75])
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                valid_intervals = intervals[(intervals >= lower_bound) & (intervals <= upper_bound)]
                
                if len(valid_intervals) >= 2:
                    hr = 60.0 / np.mean(valid_intervals)
                    return int(hr) if 45 <= hr <= 160 else None
        except Exception as e:
            print(f"HR calculation error: {e}")
        
        return None
    
    def extract_roi_signal(self, frame_rgb, landmarks):
        """Extract HR signal from facial ROIs"""
        try:
            h, w = frame_rgb.shape[:2]
            rois = [
                (landmarks.landmark[10].x, landmarks.landmark[10].y - 0.04, 20),
                (landmarks.landmark[234].x, landmarks.landmark[234].y, 15),
                (landmarks.landmark[454].x, landmarks.landmark[454].y, 15)
            ]
            
            signals = []
            for x_norm, y_norm, size in rois:
                cx, cy = int(x_norm * w), int(y_norm * h)
                x1, y1 = max(0, cx - size), max(0, cy - size)
                x2, y2 = min(w, cx + size), min(h, cy + size)
                
                if x2 > x1 and y2 > y1:
                    roi = frame_rgb[y1:y2, x1:x2, 1]  # Green channel
                    if roi.size > 100:
                        signals.append(np.mean(roi))
            
            return np.mean(signals) if signals else None
        except:
            return None
    
    # === DEEPFACE EMOTION DETECTION ===
    def analyze_emotions_deepface(self, frame_rgb):
        """DeepFace emotion analysis"""
        try:
            small_frame = cv2.resize(frame_rgb, (224, 224))
            result = DeepFace.analyze(
                small_frame, 
                actions=['emotion'], 
                enforce_detection=False, 
                silent=True
            )
            
            deepface_emotions = result[0]['emotion']
            
            emotions = {
                'Happiness/Joy': int(deepface_emotions.get('happy', 0)),
                'Trust': 100 - int(deepface_emotions.get('fear', 0) + deepface_emotions.get('angry', 0)) // 2,
                'Fear/FOMO': int(deepface_emotions.get('fear', 0)),
                'Surprise': int(deepface_emotions.get('surprise', 0)),
                'Anger': int(deepface_emotions.get('angry', 0))
            }
            
            emotions['Trust'] = max(10, min(90, emotions['Trust']))
            dominant = max(emotions.items(), key=lambda x: x[1])
            dominant_name = dominant[0] if dominant[1] > 30 else "Neutral"
            
            return emotions, dominant_name
            
        except Exception as e:
            print(f"DeepFace error: {e}")
            return None, None
    
    # === GEOMETRIC EMOTION DETECTION ===
    def detect_emotions_geometric(self, frame, face_landmarks):
        """Lightweight geometric emotion detection"""
        emotions = {
            'Happiness/Joy': 0,
            'Trust': 50,
            'Fear/FOMO': 0,
            'Surprise': 0,
            'Anger': 0
        }
        
        try:
            h, w = frame.shape[:2]
            
            left_mouth = face_landmarks.landmark[61]
            right_mouth = face_landmarks.landmark[291]
            upper_lip = face_landmarks.landmark[13]
            lower_lip = face_landmarks.landmark[14]
            left_eye = face_landmarks.landmark[33]
            right_eye = face_landmarks.landmark[263]
            left_eyebrow = face_landmarks.landmark[70]
            right_eyebrow = face_landmarks.landmark[300]
            
            mouth_width = abs(right_mouth.x - left_mouth.x) * w
            mouth_height = abs(upper_lip.y - lower_lip.y) * h
            mouth_curve = (left_mouth.y + right_mouth.y) / 2 - upper_lip.y
            eye_openness = abs(left_eye.y - left_eyebrow.y) + abs(right_eye.y - right_eyebrow.y)
            
            if mouth_width > 25 and mouth_curve < -0.01:
                emotions['Happiness/Joy'] = min(100, int(mouth_width * 2))
                emotions['Trust'] = 70
                dominant = "Happiness/Joy"
            elif eye_openness > 0.06 and mouth_height > 8:
                emotions['Surprise'] = min(100, int(eye_openness * 1000))
                emotions['Trust'] = 30
                dominant = "Surprise"
            elif eye_openness < 0.03 and mouth_width < 15:
                if mouth_curve > 0.005:
                    emotions['Anger'] = 60
                    emotions['Trust'] = 10
                    dominant = "Anger"
                else:
                    emotions['Fear/FOMO'] = 50
                    emotions['Trust'] = 20
                    dominant = "Fear/FOMO"
            else:
                emotions['Trust'] = 60
                dominant = "Trust"
            
            return emotions, dominant
        except Exception as e:
            print(f"Emotion detection error: {e}")
            return emotions, "Neutral"
    
    def calculate_gaze(self, landmarks):
        """Calculate gaze position"""
        try:
            left_eye = landmarks.landmark[33]
            right_eye = landmarks.landmark[263]
            gaze_x = ((left_eye.x + right_eye.x) / 2) * 100
            gaze_y = ((left_eye.y + right_eye.y) / 2) * 100
            return gaze_x, gaze_y
        except:
            return 50, 50
    
    def stop(self):
        self.running = False

# --- GLOBAL ANALYZER ---
analyzer = RobustAnalyzer()

# --- SOCKET EVENTS ---
@socketio.on('connect')
def handle_connect():
    try:
        print(f'✅ Client connected: {request.sid}')
        emit('connection_status', {'status': 'connected', 'sid': request.sid})
    except Exception as e:
        print(f'❌ Error in connect handler: {e}')

@socketio.on('disconnect')
def handle_disconnect():
    try:
        print(f'❌ Client disconnected: {request.sid}')
        # Remove from waiting queue if present
        session_manager.waiting_users = [
            u for u in session_manager.waiting_users 
            if u['socket_id'] != request.sid
        ]
    except Exception as e:
        print(f'❌ Error in disconnect handler: {e}')

@socketio.on('identify')
def handle_identify(data):
    try:
        print(f'👤 User identified: {data}')
        user_id = data.get('user_id', request.sid)
        session_manager.add_waiting_user(user_id, request.sid)
    except Exception as e:
        print(f'❌ Error in identify handler: {e}')
        emit('error', {'message': 'Failed to identify user'})

@socketio.on('join-room')
def handle_join_room(data):
    try:
        room_id = data.get('roomId')
        print(f'🚪 User joining room: {room_id}')
        join_room(room_id)
        emit('joined-room', {'roomId': room_id})
    except Exception as e:
        print(f'❌ Error in join room handler: {e}')

@socketio.on('transcript')
def handle_transcript(data):
    try:
        print(f'📝 Transcript received: {data}')
        speaker = data.get('speaker', 'unknown')
        text = data.get('text', '')
        room_id = data.get('roomId')
        
        # Analyze text emotion if available
        if analyzer.emotion_analyzer and text:
            text_emotions = analyzer.analyze_text_emotion(text)
            if text_emotions:
                emit('text-emotion', {
                    'emotions': text_emotions,
                    'text': text
                }, room=room_id)
        
        # Simple objection detection
        objections = ['expensive', 'costly', 'think about it', 'not sure', 'too much', 'price']
        if any(word in text.lower() for word in objections):
            suggestion = f"💡 Objection detected: '{text}'. Consider addressing value proposition and ROI benefits."
            emit('ai-response', {
                'suggestion': suggestion, 
                'type': 'objection',
                'timestamp': time.time()
            }, room=room_id)
            
        # Broadcast transcript to room
        if room_id:
            emit('new-transcript', {
                'speaker': speaker,
                'text': text,
                'timestamp': time.time()
            }, room=room_id, include_self=False)
            
    except Exception as e:
        print(f'❌ Error in transcript handler: {e}')
        emit('error', {'message': 'Failed to process transcript'})

@socketio.on('audio-chunk')
def handle_audio_chunk(data):
    """Handle real-time audio for transcription"""
    try:
        audio_data = data.get('audio')
        room_id = data.get('roomId')
        
        if analyzer.audio_transcriber and audio_data:
            text = analyzer.transcribe_audio(audio_data)
            if text:
                emit('transcription-result', {
                    'text': text,
                    'timestamp': time.time()
                }, room=room_id)
                
    except Exception as e:
        print(f'❌ Error in audio chunk handler: {e}')

@socketio.on('analyze-context')
def handle_analysis(data):
    try:
        print(f'🔍 Analysis requested: {data}')
        transcript = data.get('transcript', '')
        emotions = data.get('emotions', {})
        hr = data.get('hr', 0)
        room_id = data.get('roomId')
        
        suggestions = []
        
        if hr > 80:
            suggestions.append("⚡ High heart rate detected. Prospect may be stressed or excited.")
        
        trust_level = emotions.get('Trust', 0)
        if trust_level > 60:
            suggestions.append("✅ Strong trust signals. Good time to move toward commitment.")
        elif trust_level < 30:
            suggestions.append("⚠️ Low trust detected. Focus on building rapport and credibility.")
        
        anger_level = emotions.get('Anger', 0)
        if anger_level > 40:
            suggestions.append("🚨 Frustration detected. Consider active listening and empathy.")
        
        if not suggestions:
            suggestions.append("📊 Conversation flow is normal. Continue with current approach.")
        
        emit('ai-response', {
            'suggestion': ' '.join(suggestions),
            'type': 'analysis',
            'timestamp': time.time()
        }, room=room_id if room_id else request.sid)
    except Exception as e:
        print(f'❌ Error in analysis handler: {e}')
        emit('error', {'message': 'Failed to analyze context'})

@socketio.on('session-started')
def handle_session_start(data):
    try:
        print(f'🎬 Session started: {data}')
        room_id = data.get('roomId')
        join_room(room_id)
    except Exception as e:
        print(f'❌ Error in session start handler: {e}')

@socketio.on('leave-room')
def handle_leave():
    try:
        print('👋 User left room')
        # Notify others in room
        emit('peer-disconnected', {'message': 'Peer has left the session'}, broadcast=True)
    except Exception as e:
        print(f'❌ Error in leave room handler: {e}')

@socketio.on('video-frame')
def handle_video_frame(data):
    """Process video frame for emotion/HR analysis"""
    try:
        frame_data = data.get('frame')
        room_id = data.get('roomId')
        
        if not LIBRARIES_AVAILABLE or not frame_data:
            return
        
        # Decode frame
        import base64
        frame_bytes = base64.b64decode(frame_data.split(',')[1])
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = analyzer.face_mesh.process(frame_rgb)
        
        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0]
            
            # Emotion detection
            if analyzer.use_deepface:
                emotions, dominant = analyzer.analyze_emotions_deepface(frame_rgb)
                if emotions is None:
                    emotions, dominant = analyzer.detect_emotions_geometric(frame_rgb, landmarks)
            else:
                emotions, dominant = analyzer.detect_emotions_geometric(frame_rgb, landmarks)
            
            # HR detection
            roi_signal = analyzer.extract_roi_signal(frame_rgb, landmarks)
            if roi_signal is not None:
                analyzer.signal_buffer.append(roi_signal)
            
            hr = None
            if len(analyzer.signal_buffer) >= analyzer.fs * 6:
                hr = analyzer.calculate_heart_rate(analyzer.signal_buffer)
                if hr:
                    analyzer.current_hr = hr
            
            # Gaze tracking
            gaze_x, gaze_y = analyzer.calculate_gaze(landmarks)
            
            # Send update
            analytics_data = {
                "hr": analyzer.current_hr,
                "dominant_emotion": dominant,
                "emotions": emotions,
                "gaze_x": gaze_x,
                "gaze_y": gaze_y
            }
            
            emit('server_update', analytics_data, room=room_id if room_id else request.sid)
            
    except Exception as e:
        print(f'❌ Error processing video frame: {e}')

# --- ROUTES ---
@app.route('/')
def serve_frontend():
    try:
        return send_from_directory(app.static_folder, 'index.html')
    except Exception as e:
        return {'error': 'Frontend not found', 'message': str(e)}, 404

@app.route('/health')
def health_check():
    return {
        'status': 'healthy',
        'mode': 'Real-time CV/ML' if LIBRARIES_AVAILABLE else 'Simulation',
        'emotion_detection': 'DeepFace' if DEEPFACE_AVAILABLE else 'Geometric' if LIBRARIES_AVAILABLE else 'None',
        'audio_pipeline': 'Active' if AUDIO_PIPELINE_AVAILABLE else 'Inactive',
        'active_sessions': len(session_manager.sessions),
        'waiting_users': len(session_manager.waiting_users)
    }

@app.route('/api/config', methods=['GET'])
def get_config():
    """Send configuration to frontend"""
    return jsonify({
        'socketUrl': request.host_url.replace('http://', 'ws://').replace('https://', 'wss://'),
        'features': {
            'videoAnalysis': LIBRARIES_AVAILABLE,
            'audioTranscription': AUDIO_PIPELINE_AVAILABLE,
            'emotionDetection': DEEPFACE_AVAILABLE or LIBRARIES_AVAILABLE
        }
    })

# --- STARTUP ---
if __name__ == '__main__':
    print("=" * 60)
    print("🌍 InsightEngine P2P Backend Server - INTEGRATED VERSION")
    print("=" * 60)
    print(f"📡 Server: http://0.0.0.0:5000")
    print(f"🔬 Video Analysis: {'✅ Active' if LIBRARIES_AVAILABLE else '❌ Disabled'}")
    print(f"💓 Heart Rate: {'✅ Active' if LIBRARIES_AVAILABLE else '❌ Disabled'}")
    print(f"😊 Emotion Detection: {'✅ DeepFace (AI)' if DEEPFACE_AVAILABLE else '✅ Geometric' if LIBRARIES_AVAILABLE else '❌ Disabled'}")
    print(f"🎙️ Audio Pipeline: {'✅ Active' if AUDIO_PIPELINE_AVAILABLE else '❌ Disabled'}")
    print(f"👁️ Gaze Tracking: {'✅ Active' if LIBRARIES_AVAILABLE else '❌ Disabled'}")
    print("=" * 60)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
