import os
import time
import base64
import tempfile
import threading
from collections import deque
from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS

# ==========================================
# VOICE-ONLY MODE - AUDIO PIPELINE IMPORTS
# ==========================================

print("=" * 70)
print("🎙️  INSIGHTENGINE P2P - VOICE-ONLY MODE")
print("=" * 70)

# Import all audio processing modules
VOICE_MODULES_AVAILABLE = {
    'transcribe': False,
    'text_emotion': False,
    'sarcasm': False,
    'objections': False,
    'diarization': False,
    'confidence': False
}

# Transcription (Whisper)
try:
    from transcribe_whisper import WhisperTranscriber
    VOICE_MODULES_AVAILABLE['transcribe'] = True
    print("✅ Whisper Transcriber loaded")
except ImportError as e:
    WhisperTranscriber = None
    print(f"⚠️  Whisper not available: {e}")

# Text Emotion Analysis (DistilBERT)
try:
    from text_emotion_distilbert import TextEmotionClassifier
    VOICE_MODULES_AVAILABLE['text_emotion'] = True
    print("✅ Text Emotion Classifier loaded")
except ImportError as e:
    TextEmotionClassifier = None
    print(f"⚠️  Text Emotion not available: {e}")

# Sarcasm Detection (RoBERTa)
try:
    from sarcasm_roberta import SarcasmSentimentModel
    VOICE_MODULES_AVAILABLE['sarcasm'] = True
    print("✅ Sarcasm Detector loaded")
except ImportError as e:
    SarcasmSentimentModel = None
    print(f"⚠️  Sarcasm Detection not available: {e}")

# Objection Detection (spaCy)
try:
    from objections_spacy import ObjectionClassifier
    VOICE_MODULES_AVAILABLE['objections'] = True
    print("✅ Objection Classifier loaded")
except ImportError as e:
    ObjectionClassifier = None
    print(f"⚠️  Objection Detection not available: {e}")

# Speaker Diarization (pyannote)
try:
    from diarization_pyannote import Diarizer
    VOICE_MODULES_AVAILABLE['diarization'] = True
    print("✅ Speaker Diarization loaded")
except ImportError as e:
    Diarizer = None
    print(f"⚠️  Diarization not available: {e}")

# Confidence Analysis (Librosa)
try:
    from confidence_librosa import ConfidenceAnalyzer
    VOICE_MODULES_AVAILABLE['confidence'] = True
    print("✅ Confidence Analyzer loaded")
except ImportError as e:
    ConfidenceAnalyzer = None
    print(f"⚠️  Confidence Analysis not available: {e}")

print("=" * 70)

# ==========================================
# CAMERA/CV CODE - COMMENTED OUT FOR FUTURE USE
# ==========================================

# # === CV/ML IMPORTS (COMMENTED OUT - VOICE ONLY MODE) ===
# try:
#     import cv2
#     import numpy as np
#     import mediapipe as mp
#     from scipy.signal import butter, filtfilt, find_peaks
#     LIBRARIES_AVAILABLE = True
#     print("✅ CV/ML libraries loaded successfully.")
# except ImportError as e:
#     LIBRARIES_AVAILABLE = False
#     print(f"⚠️ CV/ML LIBRARY MISSING: {e}")
# 
# # === DEEPFACE IMPORT (OPTIONAL) ===
# try:
#     from deepface import DeepFace
#     DEEPFACE_AVAILABLE = True
#     print("✅ DeepFace loaded successfully.")
# except ImportError as e:
#     DEEPFACE_AVAILABLE = False
#     print(f"⚠️ DeepFace not available: {e}")

# ==========================================
# FLASK APP CONFIGURATION
# ==========================================

app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=60, ping_interval=25)

# ==========================================
# VOICE ANALYZER CLASS
# ==========================================

class VoiceAnalyzer:
    """
    Voice-only analyzer using audio pipeline modules.
    Processes real-time audio streams from frontend.
    """
    
    def __init__(self):
        self.running = False
        self.audio_buffer = deque(maxlen=100)  # Store recent audio chunks
        
        # Initialize voice modules
        self.transcriber = WhisperTranscriber(model_size="base", device="cpu") if WhisperTranscriber else None
        self.emotion_classifier = TextEmotionClassifier() if TextEmotionClassifier else None
        self.sarcasm_detector = SarcasmSentimentModel() if SarcasmSentimentModel else None
        self.objection_classifier = ObjectionClassifier() if ObjectionClassifier else None
        self.confidence_analyzer = ConfidenceAnalyzer() if ConfidenceAnalyzer else None
        
        # Diarization requires HF token - will init on demand
        self.diarizer = None
        
        # Current state
        self.current_confidence = 75
        self.current_wpm = 0
        self.current_pauses = []
        self.speaker_stats = {}
        
        print(f"🎤 VoiceAnalyzer initialized with {sum(VOICE_MODULES_AVAILABLE.values())}/6 modules")
    
    def process_audio_chunk(self, audio_base64, sid):
        """
        Process incoming audio chunk from frontend.
        Saves to temp file and runs analysis.
        """
        try:
            # Decode base64 audio
            audio_bytes = base64.b64decode(audio_base64)
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_audio:
                temp_audio.write(audio_bytes)
                temp_path = temp_audio.name
            
            # Run transcription if available
            if self.transcriber:
                try:
                    result = self.transcriber.transcribe(temp_path, language="en", pause_threshold=1.0)
                    
                    # Extract transcription
                    full_text = result.get('full_text', '')
                    if full_text:
                        # Emit transcription
                        socketio.emit('transcription-result', {
                            'text': full_text,
                            'timestamp': time.time()
                        }, room=sid)
                        
                        # Update metrics
                        metrics = result.get('metrics', {})
                        self.current_wpm = metrics.get('wpm', 0)
                        self.current_pauses = result.get('pauses', [])
                        
                        # Emit metrics
                        socketio.emit('voice-metrics', {
                            'wpm': self.current_wpm,
                            'total_words': metrics.get('total_words', 0),
                            'duration': metrics.get('duration', 0),
                            'pauses_count': len(self.current_pauses),
                            'timestamp': time.time()
                        }, room=sid)
                        
                        # Process text through other modules
                        self.analyze_text(full_text, sid)
                        
                except Exception as e:
                    print(f"❌ Transcription error: {e}")
            
            # Run confidence analysis if available
            if self.confidence_analyzer:
                try:
                    confidence_result = self.confidence_analyzer.analyze(temp_path)
                    self.current_confidence = confidence_result.get('confidence_score', 75)
                    
                    socketio.emit('confidence-update', {
                        'confidence_score': self.current_confidence,
                        'pitch_stability': confidence_result.get('pitch_stability', 0),
                        'volume_stability': confidence_result.get('volume_stability', 0),
                        'avg_pitch_hz': confidence_result.get('avg_pitch_hz', 0),
                        'jitter': confidence_result.get('jitter', 0),
                        'shimmer': confidence_result.get('shimmer', 0),
                        'timestamp': time.time()
                    }, room=sid)
                    
                except Exception as e:
                    print(f"❌ Confidence analysis error: {e}")
            
            # Cleanup temp file
            try:
                os.unlink(temp_path)
            except:
                pass
                
        except Exception as e:
            print(f"❌ Audio processing error: {e}")
            socketio.emit('error', {
                'message': 'Audio processing failed',
                'error': str(e)
            }, room=sid)
    
    def analyze_text(self, text, sid):
        """
        Run text-based analysis: emotion, sarcasm, objections.
        """
        if not text or not text.strip():
            return
        
        results = {}
        
        # Emotion analysis
        if self.emotion_classifier:
            try:
                emotion_result = self.emotion_classifier.classify(text)
                results['emotions'] = emotion_result.get('raw', {})
                results['dominant_emotion'] = emotion_result.get('dominant', 'neutral')
                
                socketio.emit('emotion-update', {
                    'emotions': results['emotions'],
                    'dominant': results['dominant_emotion'],
                    'text': text[:100],  # Preview
                    'timestamp': time.time()
                }, room=sid)
                
            except Exception as e:
                print(f"❌ Emotion analysis error: {e}")
        
        # Sarcasm detection
        if self.sarcasm_detector:
            try:
                sarcasm_result = self.sarcasm_detector.analyze(text)
                sarcasm_info = sarcasm_result.get('sarcasm', {})
                
                if sarcasm_info.get('is_sarcastic', False):
                    socketio.emit('sarcasm-detected', {
                        'score': sarcasm_info.get('score', 0),
                        'text': text,
                        'sentiment': sarcasm_result.get('sentiment', {}),
                        'timestamp': time.time()
                    }, room=sid)
                    
            except Exception as e:
                print(f"❌ Sarcasm detection error: {e}")
        
        # Objection detection
        if self.objection_classifier:
            try:
                objection_result = self.objection_classifier.predict(text)
                label = objection_result.get('label', 'NO_OBJECTION')
                score = objection_result.get('score', 0)
                
                if label != 'NO_OBJECTION' and score > 50:
                    # Generate suggestion based on objection type
                    suggestions = {
                        'PRICE_OBJECTION': "💰 Price concern detected. Consider emphasizing ROI and value proposition.",
                        'TIMING_OBJECTION': "⏰ Timing objection. Explore urgency factors and current pain points.",
                        'AUTHORITY_OBJECTION': "👔 Authority concern. Identify decision-makers and stakeholders.",
                        'NEED_OBJECTION': "🎯 Need objection. Revisit problem discovery and pain points.",
                        'COMPETITION_OBJECTION': "🏆 Competitive mention. Highlight unique differentiators."
                    }
                    
                    socketio.emit('objection-detected', {
                        'type': label,
                        'score': score,
                        'text': text,
                        'suggestion': suggestions.get(label, "Consider addressing this concern."),
                        'all_scores': objection_result.get('all_scores', {}),
                        'timestamp': time.time()
                    }, room=sid)
                    
            except Exception as e:
                print(f"❌ Objection detection error: {e}")
    
    def start(self):
        """Start the voice analyzer (placeholder for future background tasks)"""
        self.running = True
        print("🎙️  VoiceAnalyzer started")
    
    def stop(self):
        """Stop the voice analyzer"""
        self.running = False
        print("🛑 VoiceAnalyzer stopped")

# Initialize analyzer
voice_analyzer = VoiceAnalyzer()

# ==========================================
# SOCKET.IO EVENT HANDLERS
# ==========================================

@socketio.on('connect')
def handle_connect():
    try:
        print(f'✅ Client connected: {request.sid}')
        emit('connection_status', {
            'status': 'connected',
            'sid': request.sid,
            'mode': 'voice-only',
            'modules': VOICE_MODULES_AVAILABLE,
            'timestamp': time.time()
        })
    except Exception as e:
        print(f'❌ Error in connect: {e}')

@socketio.on('disconnect')
def handle_disconnect():
    try:
        print(f'👋 Client disconnected: {request.sid}')
    except Exception as e:
        print(f'❌ Error in disconnect: {e}')

@socketio.on('identify')
def handle_identify(data):
    try:
        print(f'👤 User identified: {data}')
        user_type = data.get('type', 'user')
        time.sleep(1)
        room_id = f'room-voice-{user_type}-{int(time.time())}'
        join_room(room_id)
        emit('match-found', {
            'roomId': room_id,
            'timestamp': time.time(),
            'status': 'success',
            'mode': 'voice-only'
        })
        print(f'🎯 Voice session created: {room_id}')
    except Exception as e:
        print(f'❌ Error in identify: {e}')
        emit('error', {'message': 'Failed to identify user', 'error': str(e)})

@socketio.on('audio-data')
def handle_audio_data(data):
    """
    Receive audio chunk from frontend and process it.
    """
    try:
        audio_base64 = data.get('audio')
        if audio_base64:
            # Process in background to avoid blocking
            threading.Thread(
                target=voice_analyzer.process_audio_chunk,
                args=(audio_base64, request.sid),
                daemon=True
            ).start()
        else:
            print("⚠️  Received empty audio data")
    except Exception as e:
        print(f'❌ Error processing audio data: {e}')
        emit('error', {'message': 'Audio processing failed', 'error': str(e)})

@socketio.on('transcript')
def handle_transcript(data):
    """
    Handle manual text input or pre-transcribed text.
    """
    try:
        print(f'📝 Manual transcript: {data}')
        speaker = data.get('speaker', 'user')
        text = data.get('text', '')
        
        if text:
            # Analyze text
            voice_analyzer.analyze_text(text, request.sid)
            
            # Echo back
            emit('transcription-result', {
                'text': text,
                'speaker': speaker,
                'source': 'manual',
                'timestamp': time.time()
            })
    except Exception as e:
        print(f'❌ Error in transcript: {e}')
        emit('error', {'message': 'Failed to process transcript', 'error': str(e)})

@socketio.on('analyze-context')
def handle_analysis(data):
    """
    Provide comprehensive analysis based on recent conversation.
    """
    try:
        print(f'🔍 Context analysis requested')
        transcript = data.get('transcript', '')
        
        suggestions = []
        
        # Analyze recent conversation
        if transcript:
            voice_analyzer.analyze_text(transcript, request.sid)
            suggestions.append("📊 Analyzing conversation context and emotional tone...")
        
        # Add WPM insights
        if voice_analyzer.current_wpm > 0:
            if voice_analyzer.current_wpm > 160:
                suggestions.append("🚀 Speaking rate is high. Consider slowing down for better comprehension.")
            elif voice_analyzer.current_wpm < 120:
                suggestions.append("🐌 Speaking rate is slow. May indicate hesitation or uncertainty.")
            else:
                suggestions.append(f"✅ Speaking rate ({voice_analyzer.current_wpm} WPM) is in optimal range.")
        
        # Add pause analysis
        if len(voice_analyzer.current_pauses) > 5:
            suggestions.append(f"⏸️  Detected {len(voice_analyzer.current_pauses)} significant pauses. May indicate thinking or uncertainty.")
        
        # Add confidence insights
        if voice_analyzer.current_confidence < 50:
            suggestions.append("😰 Low vocal confidence detected. Focus on clear, steady speaking.")
        elif voice_analyzer.current_confidence > 75:
            suggestions.append("💪 Strong vocal confidence! Maintain this energy.")
        
        if not suggestions:
            suggestions.append("📊 Continue monitoring conversation dynamics.")
        
        emit('ai-response', {
            'suggestion': ' | '.join(suggestions),
            'type': 'context-analysis',
            'wpm': voice_analyzer.current_wpm,
            'confidence': voice_analyzer.current_confidence,
            'pauses': len(voice_analyzer.current_pauses),
            'timestamp': time.time()
        })
    except Exception as e:
        print(f'❌ Error in analysis: {e}')
        emit('error', {'message': 'Analysis failed', 'error': str(e)})

@socketio.on('session-started')
def handle_session_start(data):
    try:
        room_id = data.get('roomId')
        print(f'🎬 Voice session started: {room_id}')
        if room_id:
            join_room(room_id)
            emit('session-confirmed', {
                'status': 'active',
                'roomId': room_id,
                'mode': 'voice-only',
                'timestamp': time.time()
            })
    except Exception as e:
        print(f'❌ Error in session start: {e}')

@socketio.on('leave-room')
def handle_leave():
    try:
        print(f'👋 User leaving session: {request.sid}')
        emit('session-ended', {'status': 'ended', 'timestamp': time.time()})
    except Exception as e:
        print(f'❌ Error in leave: {e}')

# ==========================================
# HTTP ROUTES
# ==========================================

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
        'mode': 'voice-only',
        'analyzer_running': voice_analyzer.running,
        'modules': VOICE_MODULES_AVAILABLE,
        'active_modules': sum(VOICE_MODULES_AVAILABLE.values()),
        'timestamp': time.time()
    }

@app.route('/api/status')
def api_status():
    return {
        'mode': 'voice-only',
        'camera_available': False,  # Explicitly disabled
        'voice_modules': VOICE_MODULES_AVAILABLE,
        'transcription_available': VOICE_MODULES_AVAILABLE['transcribe'],
        'emotion_analysis_available': VOICE_MODULES_AVAILABLE['text_emotion'],
        'sarcasm_detection_available': VOICE_MODULES_AVAILABLE['sarcasm'],
        'objection_detection_available': VOICE_MODULES_AVAILABLE['objections'],
        'diarization_available': VOICE_MODULES_AVAILABLE['diarization'],
        'confidence_analysis_available': VOICE_MODULES_AVAILABLE['confidence'],
        'server_time': time.time()
    }

# ==========================================
# STARTUP
# ==========================================

def start_background_task():
    time.sleep(2)
    voice_analyzer.start()

if __name__ == '__main__':
    threading.Thread(target=start_background_task, daemon=True).start()
    
    print("=" * 70)
    print("🎙️  INSIGHTENGINE P2P - VOICE-ONLY MODE ACTIVE")
    print("=" * 70)
    print(f"📡 Server: http://0.0.0.0:5000")
    print(f"🎤 Voice Modules Active: {sum(VOICE_MODULES_AVAILABLE.values())}/6")
    print(f"   - Transcription (Whisper): {'✅' if VOICE_MODULES_AVAILABLE['transcribe'] else '❌'}")
    print(f"   - Emotion Analysis (DistilBERT): {'✅' if VOICE_MODULES_AVAILABLE['text_emotion'] else '❌'}")
    print(f"   - Sarcasm Detection (RoBERTa): {'✅' if VOICE_MODULES_AVAILABLE['sarcasm'] else '❌'}")
    print(f"   - Objection Detection (spaCy): {'✅' if VOICE_MODULES_AVAILABLE['objections'] else '❌'}")
    print(f"   - Speaker Diarization (pyannote): {'✅' if VOICE_MODULES_AVAILABLE['diarization'] else '❌'}")
    print(f"   - Confidence Analysis (Librosa): {'✅' if VOICE_MODULES_AVAILABLE['confidence'] else '❌'}")
    print(f"📹 Camera Mode: DISABLED (Voice-Only)")
    print("=" * 70)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
