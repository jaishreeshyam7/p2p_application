import os
import time
import random
import threading
import queue
from collections import deque
from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# === AUDIO PIPELINE IMPORTS ===
try:
    # Import the audio pipeline modules
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), 'audio_pipeline'))
    
    from audio_pipeline.transcribe_whisper import WhisperTranscriber
    from audio_pipeline.text_emotion_distilbert import EmotionAnalyzer
    from audio_pipeline.objections_spacy import ObjectionDetector
    from audio_pipeline.sarcasm_roberta import SarcasmDetector
    from audio_pipeline.confidence_librosa import ConfidenceAnalyzer
    from audio_pipeline.diarization_pyannote import SpeakerDiarizer
    
    AUDIO_PIPELINE_AVAILABLE = True
    print("✅ Audio pipeline modules loaded successfully.")
except ImportError as e:
    AUDIO_PIPELINE_AVAILABLE = False
    print(f"⚠️ AUDIO PIPELINE MISSING: {e}")
    print("💡 Using simulation mode as fallback.")

# === OPTIONAL CV IMPORTS (Lightweight) ===
try:
    import cv2
    import numpy as np
    import mediapipe as mp
    CV_AVAILABLE = True
    print("✅ CV libraries available (optional).")
except ImportError:
    CV_AVAILABLE = False
    print("⚠️ CV libraries not available (optional feature disabled).")

# --- CONFIGURATION ---
app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10000000)

class VoiceAnalyzer:
    """Main voice analysis engine using audio pipeline modules"""
    
    def __init__(self):
        self.running = False
        self.audio_queue = queue.Queue()
        
        # Initialize audio pipeline components
        if AUDIO_PIPELINE_AVAILABLE:
            try:
                print("🎤 Initializing audio pipeline components...")
                self.transcriber = WhisperTranscriber()
                self.emotion_analyzer = EmotionAnalyzer()
                self.objection_detector = ObjectionDetector()
                self.sarcasm_detector = SarcasmDetector()
                self.confidence_analyzer = ConfidenceAnalyzer()
                
                # Diarization is optional (requires HuggingFace token)
                try:
                    self.diarizer = SpeakerDiarizer()
                    print("✅ Speaker diarization enabled")
                except Exception as e:
                    self.diarizer = None
                    print(f"⚠️ Speaker diarization disabled: {e}")
                
                print("✅ Audio pipeline initialized successfully")
                self.use_audio_pipeline = True
            except Exception as e:
                print(f"❌ Failed to initialize audio pipeline: {e}")
                self.use_audio_pipeline = False
        else:
            self.use_audio_pipeline = False
        
        # Current state
        self.current_emotion = "Neutral"
        self.current_emotions = {
            'Happiness/Joy': 50,
            'Trust': 60,
            'Fear/FOMO': 10,
            'Surprise': 20,
            'Anger': 5
        }
        self.current_confidence = 75
        self.is_sarcastic = False
        self.has_objection = False
        self.objection_type = None
        
    def process_audio_chunk(self, audio_data):
        """Process incoming audio chunk through the pipeline"""
        if not self.use_audio_pipeline:
            return self.generate_mock_analysis()
        
        try:
            # 1. Transcribe audio using Whisper
            transcription = self.transcriber.transcribe(audio_data)
            
            if not transcription or transcription.strip() == "":
                return None
            
            # 2. Analyze emotions from text
            emotions = self.emotion_analyzer.analyze(transcription)
            
            # 3. Detect objections
            objection_result = self.objection_detector.detect(transcription)
            
            # 4. Detect sarcasm
            sarcasm_score = self.sarcasm_detector.detect(transcription)
            
            # 5. Analyze confidence from audio features
            confidence_score = self.confidence_analyzer.analyze(audio_data)
            
            # 6. Speaker diarization (if available)
            speaker_label = None
            if self.diarizer:
                speaker_label = self.diarizer.identify_speaker(audio_data)
            
            # Update current state
            self.current_emotions = self.map_emotions(emotions)
            self.current_emotion = self.get_dominant_emotion(self.current_emotions)
            self.current_confidence = int(confidence_score * 100)
            self.is_sarcastic = sarcasm_score > 0.6
            self.has_objection = objection_result['has_objection']
            self.objection_type = objection_result.get('type', None)
            
            return {
                'transcription': transcription,
                'emotions': self.current_emotions,
                'dominant_emotion': self.current_emotion,
                'confidence': self.current_confidence,
                'is_sarcastic': self.is_sarcastic,
                'has_objection': self.has_objection,
                'objection_type': self.objection_type,
                'speaker': speaker_label or 'Unknown'
            }
            
        except Exception as e:
            print(f"❌ Error processing audio: {e}")
            return None
    
    def map_emotions(self, raw_emotions):
        """Map emotion analyzer output to our 5 major feelings"""
        # Assuming emotion_analyzer returns dict with various emotions
        # Adapt this based on your actual emotion_analyzer output
        mapped = {
            'Happiness/Joy': int(raw_emotions.get('joy', 0) * 100),
            'Trust': int(raw_emotions.get('trust', 0.5) * 100),
            'Fear/FOMO': int(raw_emotions.get('fear', 0) * 100),
            'Surprise': int(raw_emotions.get('surprise', 0) * 100),
            'Anger': int(raw_emotions.get('anger', 0) * 100)
        }
        return mapped
    
    def get_dominant_emotion(self, emotions):
        """Get the dominant emotion from emotion dict"""
        if not emotions:
            return "Neutral"
        dominant = max(emotions.items(), key=lambda x: x[1])
        return dominant[0] if dominant[1] > 30 else "Neutral"
    
    def generate_mock_analysis(self):
        """Generate mock data when audio pipeline is not available"""
        return {
            'transcription': '[Simulation Mode - No real transcription]',
            'emotions': {
                'Happiness/Joy': random.randint(30, 80),
                'Trust': random.randint(40, 85),
                'Fear/FOMO': random.randint(0, 30),
                'Surprise': random.randint(10, 50),
                'Anger': random.randint(0, 25)
            },
            'dominant_emotion': random.choice(['Happiness/Joy', 'Trust', 'Neutral', 'Surprise']),
            'confidence': random.randint(60, 95),
            'is_sarcastic': random.random() > 0.8,
            'has_objection': random.random() > 0.7,
            'objection_type': random.choice(['price', 'timing', 'authority', None]),
            'speaker': 'User'
        }
    
    def stream_analysis(self):
        """Continuously send analysis updates to frontend"""
        print("🎙️ Voice analysis stream started...")
        self.running = True
        
        while self.running:
            try:
                # In simulation mode, generate periodic updates
                if not self.use_audio_pipeline:
                    time.sleep(2)
                    mock_data = self.generate_mock_analysis()
                    
                    # Send periodic updates
                    socketio.emit('voice_analysis', {
                        'emotions': mock_data['emotions'],
                        'dominant_emotion': mock_data['dominant_emotion'],
                        'confidence': mock_data['confidence'],
                        'is_sarcastic': mock_data['is_sarcastic'],
                        'timestamp': time.time()
                    })
                    
                    if mock_data['has_objection']:
                        socketio.emit('objection_detected', {
                            'type': mock_data['objection_type'],
                            'message': f"Objection detected: {mock_data['objection_type']}"
                        })
                else:
                    # Wait for audio data from queue
                    try:
                        audio_data = self.audio_queue.get(timeout=1)
                        result = self.process_audio_chunk(audio_data)
                        
                        if result:
                            # Send analysis to frontend
                            socketio.emit('voice_analysis', {
                                'emotions': result['emotions'],
                                'dominant_emotion': result['dominant_emotion'],
                                'confidence': result['confidence'],
                                'is_sarcastic': result['is_sarcastic'],
                                'timestamp': time.time()
                            })
                            
                            # Send transcription
                            socketio.emit('transcription', {
                                'text': result['transcription'],
                                'speaker': result['speaker'],
                                'timestamp': time.time()
                            })
                            
                            # Send objection alert if detected
                            if result['has_objection']:
                                socketio.emit('objection_detected', {
                                    'type': result['objection_type'],
                                    'message': f"Objection detected: {result['objection_type']}",
                                    'text': result['transcription']
                                })
                    except queue.Empty:
                        continue
                        
            except Exception as e:
                print(f"❌ Error in voice analysis stream: {e}")
                time.sleep(1)
    
    def stop(self):
        """Stop the analyzer"""
        self.running = False

# --- GLOBAL ANALYZER ---
analyzer = VoiceAnalyzer()

# --- SOCKET EVENTS ---
@socketio.on('connect')
def handle_connect():
    try:
        print(f'✅ Client connected: {request.sid}')
        emit('connection_status', {
            'status': 'connected',
            'audio_pipeline_available': AUDIO_PIPELINE_AVAILABLE,
            'mode': 'Audio Pipeline' if AUDIO_PIPELINE_AVAILABLE else 'Simulation'
        })
    except Exception as e:
        print(f'❌ Error in connect handler: {e}')

@socketio.on('disconnect')
def handle_disconnect():
    try:
        print(f'❌ Client disconnected: {request.sid}')
    except Exception as e:
        print(f'❌ Error in disconnect handler: {e}')

@socketio.on('audio_data')
def handle_audio_data(data):
    """Handle incoming audio data from frontend"""
    try:
        # Convert base64 or binary audio data
        import base64
        audio_bytes = base64.b64decode(data['audio']) if isinstance(data.get('audio'), str) else data.get('audio')
        
        # Add to processing queue
        analyzer.audio_queue.put(audio_bytes)
        
    except Exception as e:
        print(f'❌ Error processing audio data: {e}')
        emit('error', {'message': 'Failed to process audio data'})

@socketio.on('identify')
def handle_identify(data):
    try:
        print(f'👤 User identified: {data}')
        time.sleep(1)
        emit('match-found', {
            'roomId': 'room-voice-' + str(int(time.time())),
            'timestamp': time.time(),
            'mode': 'voice_analysis'
        })
    except Exception as e:
        print(f'❌ Error in identify handler: {e}')
        emit('error', {'message': 'Failed to identify user'})

@socketio.on('text_input')
def handle_text_input(data):
    """Handle text input from frontend (manual typing or speech recognition)"""
    try:
        text = data.get('text', '')
        speaker = data.get('speaker', 'User')
        
        print(f'📝 Text input received from {speaker}: {text}')
        
        if not text:
            return
        
        # Process through audio pipeline (text-only features)
        if AUDIO_PIPELINE_AVAILABLE:
            try:
                # Emotion analysis
                emotions = analyzer.emotion_analyzer.analyze(text)
                mapped_emotions = analyzer.map_emotions(emotions)
                
                # Objection detection
                objection_result = analyzer.objection_detector.detect(text)
                
                # Sarcasm detection
                sarcasm_score = analyzer.sarcasm_detector.detect(text)
                
                # Send analysis
                emit('voice_analysis', {
                    'emotions': mapped_emotions,
                    'dominant_emotion': analyzer.get_dominant_emotion(mapped_emotions),
                    'confidence': 75,  # Default for text-only
                    'is_sarcastic': sarcasm_score > 0.6,
                    'timestamp': time.time()
                })
                
                # Objection alert
                if objection_result['has_objection']:
                    emit('objection_detected', {
                        'type': objection_result.get('type', 'general'),
                        'message': f"Objection detected: {objection_result.get('type', 'general')}",
                        'text': text,
                        'suggestion': generate_objection_response(objection_result.get('type'))
                    })
                
                # Sarcasm alert
                if sarcasm_score > 0.6:
                    emit('sarcasm_detected', {
                        'score': float(sarcasm_score),
                        'text': text,
                        'message': '⚠️ Sarcasm detected in prospect response'
                    })
                    
            except Exception as e:
                print(f'❌ Error in text analysis: {e}')
        
    except Exception as e:
        print(f'❌ Error in text input handler: {e}')
        emit('error', {'message': 'Failed to process text'})

def generate_objection_response(objection_type):
    """Generate AI coaching for different objection types"""
    responses = {
        'price': "💡 Price objection detected. Focus on ROI and value proposition. Ask: 'What would success look like for you?'",
        'timing': "💡 Timing objection detected. Create urgency with limited offers or upcoming changes. Ask: 'What's preventing you from moving forward now?'",
        'authority': "💡 Authority objection detected. Identify true decision-maker. Ask: 'Who else would need to be involved in this decision?'",
        'need': "💡 Need objection detected. Reinforce pain points and benefits. Ask: 'What challenges are you facing currently?'",
        'competitor': "💡 Competitor objection detected. Highlight unique differentiators. Ask: 'What's most important to you in a solution?'",
        'general': "💡 Objection detected. Use active listening and empathy. Ask clarifying questions to understand the real concern."
    }
    return responses.get(objection_type, responses['general'])

@socketio.on('analyze-context')
def handle_analysis(data):
    try:
        print(f'🔍 Context analysis requested: {data}')
        transcript = data.get('transcript', '')
        emotions = data.get('emotions', {})
        confidence = data.get('confidence', 75)
        
        suggestions = []
        
        # Confidence-based coaching
        if confidence < 50:
            suggestions.append("⚠️ Low confidence detected. Slow down, take deep breaths, and speak clearly.")
        elif confidence > 85:
            suggestions.append("✅ Strong confident delivery. Maintain this energy!")
        
        # Emotion-based coaching
        trust_level = emotions.get('Trust', 0)
        if trust_level > 60:
            suggestions.append("✅ Strong trust signals. Good time to move toward commitment.")
        elif trust_level < 30:
            suggestions.append("⚠️ Low trust detected. Focus on building rapport and credibility.")
        
        anger_level = emotions.get('Anger', 0)
        if anger_level > 40:
            suggestions.append("🚨 Frustration detected. Use active listening and empathy.")
        
        joy_level = emotions.get('Happiness/Joy', 0)
        if joy_level > 70:
            suggestions.append("😊 Prospect is engaged and positive. Great opportunity to close!")
        
        if not suggestions:
            suggestions.append("📊 Conversation flow is normal. Continue with current approach.")
        
        emit('ai-response', {
            'suggestion': ' '.join(suggestions),
            'type': 'analysis',
            'timestamp': time.time()
        })
    except Exception as e:
        print(f'❌ Error in analysis handler: {e}')
        emit('error', {'message': 'Failed to analyze context'})

@socketio.on('session-started')
def handle_session_start(data):
    try:
        print(f'🎬 Session started: {data}')
        emit('ai-response', {
            'suggestion': '🎙️ Voice analysis active. Speak naturally and the AI will provide real-time coaching.',
            'type': 'info'
        })
    except Exception as e:
        print(f'❌ Error in session start handler: {e}')

@socketio.on('leave-room')
def handle_leave():
    try:
        print('👋 User left room')
    except Exception as e:
        print(f'❌ Error in leave room handler: {e}')

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
        'analyzer_running': analyzer.running,
        'mode': 'Audio Pipeline' if AUDIO_PIPELINE_AVAILABLE else 'Simulation',
        'features': {
            'transcription': AUDIO_PIPELINE_AVAILABLE,
            'emotion_analysis': AUDIO_PIPELINE_AVAILABLE,
            'objection_detection': AUDIO_PIPELINE_AVAILABLE,
            'sarcasm_detection': AUDIO_PIPELINE_AVAILABLE,
            'confidence_analysis': AUDIO_PIPELINE_AVAILABLE,
            'speaker_diarization': AUDIO_PIPELINE_AVAILABLE and analyzer.diarizer is not None
        }
    }

@app.route('/api/test')
def test_api():
    """Test endpoint to verify backend is running"""
    return {
        'message': 'Backend is running',
        'audio_pipeline': AUDIO_PIPELINE_AVAILABLE,
        'timestamp': time.time()
    }

# --- STARTUP ---
def start_background_task():
    time.sleep(2)
    analyzer.stream_analysis()

if __name__ == '__main__':
    # Start voice analysis stream
    threading.Thread(target=start_background_task, daemon=True).start()
    
    print("=" * 70)
    print("🎙️  InsightEngine P2P Voice Analysis Backend")
    print("=" * 70)
    print(f"📡 Server: http://0.0.0.0:5000")
    print(f"🔬 Mode: {'Audio Pipeline (Real Analysis)' if AUDIO_PIPELINE_AVAILABLE else 'Simulation Mode'}")
    print(f"📝 Transcription: {'✅ Whisper Active' if AUDIO_PIPELINE_AVAILABLE else '❌ Simulated'}")
    print(f"😊 Emotions: {'✅ DistilBERT Active' if AUDIO_PIPELINE_AVAILABLE else '❌ Random'}")
    print(f"🚫 Objections: {'✅ SpaCy Active' if AUDIO_PIPELINE_AVAILABLE else '❌ Random'}")
    print(f"😏 Sarcasm: {'✅ RoBERTa Active' if AUDIO_PIPELINE_AVAILABLE else '❌ Random'}")
    print(f"💪 Confidence: {'✅ Librosa Active' if AUDIO_PIPELINE_AVAILABLE else '❌ Random'}")
    print(f"👥 Diarization: {'✅ Pyannote Active' if AUDIO_PIPELINE_AVAILABLE and analyzer.diarizer else '❌ Disabled'}")
    print("=" * 70)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
