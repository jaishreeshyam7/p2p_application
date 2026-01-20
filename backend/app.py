import os
import time
import random
import threading
from collections import deque
from flask import Flask, send_from_directory, request
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
    print("💡 Using geometric emotion detection as fallback.")

# === AUDIO PIPELINE IMPORTS ===
try:
    from audio_pipeline.transcribe_whisper import transcribe_audio_stream
    from audio_pipeline.text_emotion_distilbert import analyze_text_emotion
    from audio_pipeline.objections_spacy import detect_objections
    AUDIO_PIPELINE_AVAILABLE = True
    print("✅ Audio pipeline modules loaded successfully.")
except ImportError as e:
    AUDIO_PIPELINE_AVAILABLE = False
    print(f"⚠️ Audio pipeline not available: {e}")
    print("💡 Using basic text processing as fallback.")

# --- CONFIGURATION ---
app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=60, ping_interval=25)

class RobustAnalyzer:
    def __init__(self):
        self.fs = 30
        self.buffer = deque(maxlen=self.fs * 10)
        self.signal_buffer = deque(maxlen=self.fs * 10)
        self.running = False
        self.use_deepface = DEEPFACE_AVAILABLE
        
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
                print(f"🎭 Emotion Detection: {'DeepFace (AI-powered)' if self.use_deepface else 'Geometric (Fallback)'}")
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
    
    def bandpass_filter(self, signal, fs=30, low=0.7, high=3.5):
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
                    roi = frame_rgb[y1:y2, x1:x2, 1]
                    if roi.size > 100:
                        signals.append(np.mean(roi))
            return np.mean(signals) if signals else None
        except:
            return None
    
    def analyze_emotions_deepface(self, frame_rgb):
        try:
            small_frame = cv2.resize(frame_rgb, (224, 224))
            result = DeepFace.analyze(small_frame, actions=['emotion'], enforce_detection=False, silent=True)
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
    
    def detect_emotions_geometric(self, frame, face_landmarks):
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
        try:
            left_eye = landmarks.landmark[33]
            right_eye = landmarks.landmark[263]
            gaze_x = ((left_eye.x + right_eye.x) / 2) * 100
            gaze_y = ((left_eye.y + right_eye.y) / 2) * 100
            return gaze_x, gaze_y
        except:
            return 50, 50
    
    def stream_webcam_analysis(self):
        print("🎥 Starting real-time webcam analysis...")
        self.running = True
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("⚠️ Camera not accessible, falling back to simulation")
            self.stream_simulation()
            return
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        frame_count = 0
        last_hr_time = time.time()
        
        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    break
                
                current_time = time.time()
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.face_mesh.process(frame_rgb)
                
                if results.multi_face_landmarks:
                    landmarks = results.multi_face_landmarks[0]
                    
                    if frame_count % 3 == 0:
                        if self.use_deepface and (current_time - self.last_deepface_time) >= self.deepface_interval:
                            emotions, dominant = self.analyze_emotions_deepface(frame_rgb)
                            if emotions is not None:
                                self.current_emotions = emotions
                                self.current_emotion = dominant
                                self.last_deepface_time = current_time
                            else:
                                emotions, dominant = self.detect_emotions_geometric(frame_rgb, landmarks)
                                self.current_emotions = emotions
                                self.current_emotion = dominant
                        else:
                            emotions, dominant = self.detect_emotions_geometric(frame_rgb, landmarks)
                            self.current_emotions = emotions
                            self.current_emotion = dominant
                    
                    if frame_count % 2 == 0:
                        roi_signal = self.extract_roi_signal(frame_rgb, landmarks)
                        if roi_signal is not None:
                            self.signal_buffer.append(roi_signal)
                    
                    if time.time() - last_hr_time >= 1.5 and len(self.signal_buffer) >= self.fs * 6:
                        hr = self.calculate_heart_rate(self.signal_buffer)
                        if hr is not None:
                            self.current_hr = hr
                        last_hr_time = time.time()
                    
                    self.gaze_x, self.gaze_y = self.calculate_gaze(landmarks)
                
                data = {
                    "hr": self.current_hr,
                    "dominant_emotion": self.current_emotion,
                    "emotions": self.current_emotions,
                    "gaze_x": self.gaze_x,
                    "gaze_y": self.gaze_y
                }
                socketio.emit('server_update', data)
                frame_count += 1
                time.sleep(0.033)
        except Exception as e:
            print(f"❌ Webcam analysis error: {e}")
        finally:
            cap.release()
            if self.face_mesh:
                self.face_mesh.close()
    
    def stream_simulation(self):
        print("🚀 SIMULATION STREAM STARTED")
        self.running = True
        while self.running:
            try:
                data = {
                    "hr": 70 + random.randint(-5, 10),
                    "dominant_emotion": random.choice(["Happiness/Joy", "Trust", "Neutral", "Surprise", "Anger"]),
                    "emotions": {
                        'Happiness/Joy': random.randint(30, 90),
                        'Trust': random.randint(40, 85),
                        'Fear/FOMO': random.randint(0, 30),
                        'Surprise': random.randint(10, 50),
                        'Anger': random.randint(0, 25)
                    },
                    "gaze_x": 50 + random.randint(-30, 30),
                    "gaze_y": 50 + random.randint(-10, 10)
                }
                socketio.emit('server_update', data)
                time.sleep(1.0)
            except Exception as e:
                print(f"❌ Error in simulation: {e}")
                time.sleep(1.0)
    
    def run(self):
        if LIBRARIES_AVAILABLE and self.face_mesh is not None:
            try:
                self.stream_webcam_analysis()
            except Exception as e:
                print(f"❌ Failed to start webcam: {e}")
                self.stream_simulation()
        else:
            self.stream_simulation()
    
    def stop(self):
        self.running = False

analyzer = RobustAnalyzer()

# === TEXT ANALYSIS ===
def analyze_text_with_pipeline(text):
    results = {'emotions': {}, 'objections': [], 'sentiment': 'neutral'}
    if AUDIO_PIPELINE_AVAILABLE:
        try:
            results['emotions'] = analyze_text_emotion(text)
            results['objections'] = detect_objections(text)
        except Exception as e:
            print(f"❌ Text analysis error: {e}")
    else:
        objection_keywords = ['expensive', 'costly', 'think about it', 'not sure', 'too much', 'budget']
        results['objections'] = [word for word in objection_keywords if word in text.lower()]
    return results

# === SOCKET EVENTS ===
@socketio.on('connect')
def handle_connect():
    try:
        print(f'✅ Client connected: {request.sid}')
        emit('connection_status', {'status': 'connected', 'sid': request.sid})
    except Exception as e:
        print(f'❌ Error in connect: {e}')

@socketio.on('disconnect')
def handle_disconnect():
    try:
        print(f'❌ Client disconnected: {request.sid}')
    except Exception as e:
        print(f'❌ Error in disconnect: {e}')

@socketio.on('identify')
def handle_identify(data):
    try:
        print(f'👤 User identified: {data}')
        user_type = data.get('type', 'user')
        time.sleep(2)
        room_id = f'room-{user_type}-{int(time.time())}'
        join_room(room_id)
        emit('match-found', {'roomId': room_id, 'timestamp': time.time(), 'status': 'success'})
        print(f'🎯 Match created: {room_id}')
    except Exception as e:
        print(f'❌ Error in identify: {e}')
        emit('error', {'message': 'Failed to identify user', 'error': str(e)})

@socketio.on('transcript')
def handle_transcript(data):
    try:
        print(f'📝 Transcript: {data}')
        speaker = data.get('speaker', 'unknown')
        text = data.get('text', '')
        
        analysis = analyze_text_with_pipeline(text)
        
        if analysis['objections']:
            objection_text = ', '.join(analysis['objections'])
            suggestion = f"💡 Objection detected: '{objection_text}'. Consider addressing value proposition."
            emit('ai-response', {
                'suggestion': suggestion, 
                'type': 'objection',
                'objections': analysis['objections'],
                'timestamp': time.time()
            })
        
        if analysis['emotions']:
            emit('text-emotion-update', {
                'emotions': analysis['emotions'],
                'text': text,
                'timestamp': time.time()
            })
    except Exception as e:
        print(f'❌ Error in transcript: {e}')
        emit('error', {'message': 'Failed to process transcript', 'error': str(e)})

@socketio.on('analyze-context')
def handle_analysis(data):
    try:
        print(f'🔍 Analysis requested')
        transcript = data.get('transcript', '')
        emotions = data.get('emotions', {})
        hr = data.get('hr', 0)
        
        suggestions = []
        
        if hr > 80:
            suggestions.append("⚡ High heart rate detected. Prospect may be stressed or excited.")
        elif hr > 0 and hr < 60:
            suggestions.append("😌 Low heart rate. Prospect appears calm.")
        
        trust_level = emotions.get('Trust', 0)
        if trust_level > 60:
            suggestions.append("✅ Strong trust signals. Good time to move toward commitment.")
        elif trust_level < 30:
            suggestions.append("⚠️ Low trust. Focus on building rapport.")
        
        anger_level = emotions.get('Anger', 0)
        if anger_level > 40:
            suggestions.append("🚨 Frustration detected. Consider active listening.")
        
        fear_level = emotions.get('Fear/FOMO', 0)
        if fear_level > 40:
            suggestions.append("😰 Anxiety detected. Provide reassurance.")
        
        joy_level = emotions.get('Happiness/Joy', 0)
        if joy_level > 60:
            suggestions.append("😊 Positive engagement! Continue current approach.")
        
        if transcript:
            text_analysis = analyze_text_with_pipeline(transcript)
            if text_analysis['objections']:
                suggestions.append(f"📋 Concerns: {', '.join(text_analysis['objections'])}")
        
        if not suggestions:
            suggestions.append("📊 Conversation flow is normal.")
        
        emit('ai-response', {
            'suggestion': ' '.join(suggestions),
            'type': 'analysis',
            'timestamp': time.time()
        })
    except Exception as e:
        print(f'❌ Error in analysis: {e}')
        emit('error', {'message': 'Failed to analyze', 'error': str(e)})

@socketio.on('session-started')
def handle_session_start(data):
    try:
        room_id = data.get('roomId')
        print(f'🎬 Session started: {room_id}')
        if room_id:
            join_room(room_id)
            emit('session-confirmed', {'status': 'active', 'roomId': room_id, 'timestamp': time.time()})
    except Exception as e:
        print(f'❌ Error in session start: {e}')

@socketio.on('leave-room')
def handle_leave():
    try:
        print(f'👋 User left: {request.sid}')
        emit('session-ended', {'status': 'ended', 'timestamp': time.time()})
    except Exception as e:
        print(f'❌ Error in leave: {e}')

@socketio.on('audio-data')
def handle_audio_data(data):
    try:
        if AUDIO_PIPELINE_AVAILABLE:
            audio_bytes = data.get('audio')
            if audio_bytes:
                transcript = transcribe_audio_stream(audio_bytes)
                if transcript:
                    emit('transcription-result', {'text': transcript, 'timestamp': time.time()})
        else:
            print("⚠️ Audio pipeline not available")
    except Exception as e:
        print(f'❌ Error processing audio: {e}')

# === ROUTES ===
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
        'analyzer_running': analyzer.running,
        'mode': 'Real-time CV/ML' if LIBRARIES_AVAILABLE else 'Simulation',
        'emotion_detection': 'DeepFace' if DEEPFACE_AVAILABLE else 'Geometric' if LIBRARIES_AVAILABLE else 'Simulated',
        'audio_pipeline': 'Active' if AUDIO_PIPELINE_AVAILABLE else 'Disabled',
        'timestamp': time.time()
    }

@app.route('/api/status')
def api_status():
    return {
        'cv_ml_available': LIBRARIES_AVAILABLE,
        'deepface_available': DEEPFACE_AVAILABLE,
        'audio_pipeline_available': AUDIO_PIPELINE_AVAILABLE,
        'analyzer_running': analyzer.running,
        'server_time': time.time()
    }

def start_background_task():
    time.sleep(2)
    analyzer.run()

if __name__ == '__main__':
    threading.Thread(target=start_background_task, daemon=True).start()
    
    print("=" * 60)
    print("🌍 InsightEngine P2P Backend Server")
    print("=" * 60)
    print(f"📡 Server: http://0.0.0.0:5000")
    print(f"🔬 Mode: {'Real-time CV/ML' if LIBRARIES_AVAILABLE else 'Simulation'}")
    print(f"💓 Heart Rate: {'✅ Active' if LIBRARIES_AVAILABLE else '❌ Simulated'}")
    print(f"😊 Emotions: {'✅ DeepFace' if DEEPFACE_AVAILABLE else '✅ Geometric' if LIBRARIES_AVAILABLE else '❌ Random'}")
    print(f"👁️ Gaze: {'✅ Active' if LIBRARIES_AVAILABLE else '❌ Simulated'}")
    print(f"🎙️ Audio Pipeline: {'✅ Active' if AUDIO_PIPELINE_AVAILABLE else '❌ Disabled'}")
    print("=" * 60)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
