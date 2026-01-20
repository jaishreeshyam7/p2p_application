"""
P2P Application Backend - Voice-Focused with Audio Pipeline Integration
Minimal video processing, maximum voice intelligence
"""

import os
import time
import threading
import numpy as np
from collections import deque
from flask import Flask, send_from_directory, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# === AUDIO PIPELINE IMPORTS ===
try:
    from audio_pipeline.transcribe_whisper import transcribe_audio_realtime
    WHISPER_AVAILABLE = True
    print("✅ Whisper transcription loaded")
except ImportError:
    WHISPER_AVAILABLE = False
    print("⚠️ Whisper not available")

try:
    from audio_pipeline.text_emotion_distilbert import analyze_emotion_from_text
    TEXT_EMOTION_AVAILABLE = True
    print("✅ DistilBERT emotion analysis loaded")
except ImportError:
    TEXT_EMOTION_AVAILABLE = False
    print("⚠️ DistilBERT emotion not available")

try:
    from audio_pipeline.confidence_librosa import analyze_voice_confidence
    CONFIDENCE_AVAILABLE = True
    print("✅ Librosa confidence analysis loaded")
except ImportError:
    CONFIDENCE_AVAILABLE = False
    print("⚠️ Librosa confidence not available")

try:
    from audio_pipeline.sarcasm_roberta import detect_sarcasm
    SARCASM_AVAILABLE = True
    print("✅ RoBERTa sarcasm detection loaded")
except ImportError:
    SARCASM_AVAILABLE = False
    print("⚠️ Sarcasm detection not available")

try:
    from audio_pipeline.objections_spacy import detect_objections
    OBJECTIONS_AVAILABLE = True
    print("✅ spaCy objection detection loaded")
except ImportError:
    OBJECTIONS_AVAILABLE = False
    print("⚠️ Objection detection not available")

try:
    from audio_pipeline.diarization_pyannote import diarize_speakers
    DIARIZATION_AVAILABLE = True
    print("✅ Pyannote speaker diarization loaded")
except ImportError:
    DIARIZATION_AVAILABLE = False
    print("⚠️ Speaker diarization not available")

# --- FLASK CONFIGURATION ---
app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10 * 1024 * 1024)

# === VOICE ANALYZER CLASS ===
class VoiceIntelligenceEngine:
    """Advanced voice analysis using audio_pipeline modules"""
    
    def __init__(self):
        self.transcript_buffer = deque(maxlen=100)
        self.audio_buffer = deque(maxlen=1000)  # Store audio chunks
        self.current_session = None
        self.running = False
        
        # Real-time analytics
        self.current_analytics = {
            'hr': 70,  # Simulated for now (can be replaced with actual HR detection)
            'dominant_emotion': 'Neutral',
            'emotions': {
                'Happiness/Joy': 20,
                'Trust': 50,
                'Fear/FOMO': 10,
                'Surprise': 10,
                'Anger': 10
            },
            'gaze_x': 50,
            'gaze_y': 50,
            'confidence': 50,
            'sarcasm_level': 0,
            'speaking_rate': 0,
            'energy': 0
        }
        
        # Conversation metrics
        self.conversation_metrics = {
            'user_word_count': 0,
            'prospect_word_count': 0,
            'objections_detected': [],
            'positive_moments': 0,
            'negative_moments': 0
        }
    
    # === AUDIO PROCESSING ===
    def process_audio_chunk(self, audio_data: bytes, sample_rate: int = 16000):
        """Process incoming audio chunk"""
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            self.audio_buffer.append(audio_array)
            
            # If we have enough audio (e.g., 3 seconds), process it
            if len(self.audio_buffer) >= 30:  # ~3 seconds at 10 chunks/sec
                self._analyze_audio_segment()
                
        except Exception as e:
            print(f"❌ Audio processing error: {e}")
    
    def _analyze_audio_segment(self):
        """Analyze accumulated audio segment"""
        try:
            # Combine audio chunks
            audio_segment = np.concatenate(list(self.audio_buffer))
            
            # Voice confidence analysis
            if CONFIDENCE_AVAILABLE:
                confidence_result = analyze_voice_confidence(audio_segment)
                self.current_analytics['confidence'] = confidence_result.get('confidence_score', 50)
                self.current_analytics['speaking_rate'] = confidence_result.get('speaking_rate', 0)
                self.current_analytics['energy'] = confidence_result.get('energy', 0)
            
            # Emit updated analytics
            socketio.emit('server_update', self.current_analytics)
            
        except Exception as e:
            print(f"❌ Audio segment analysis error: {e}")
    
    # === TEXT PROCESSING ===
    def process_transcript(self, text: str, speaker: str = 'user') -> dict:
        """Process transcribed text with full pipeline"""
        try:
            timestamp = time.time()
            word_count = len(text.split())
            
            # Update word count
            if speaker == 'user':
                self.conversation_metrics['user_word_count'] += word_count
            else:
                self.conversation_metrics['prospect_word_count'] += word_count
            
            # === EMOTION DETECTION ===
            emotions = self._analyze_emotion(text)
            
            # === SARCASM DETECTION ===
            sarcasm_score = self._detect_sarcasm(text)
            
            # === OBJECTION DETECTION ===
            objection = self._detect_objection(text, speaker)
            
            # Update current analytics
            self.current_analytics['emotions'] = emotions['emotions']
            self.current_analytics['dominant_emotion'] = emotions['dominant_emotion']
            self.current_analytics['sarcasm_level'] = sarcasm_score
            
            # Build response
            result = {
                'text': text,
                'speaker': speaker,
                'timestamp': timestamp,
                'word_count': word_count,
                'emotions': emotions,
                'sarcasm_score': sarcasm_score,
                'objection': objection,
                'analytics': self.current_analytics.copy()
            }
            
            # Store in buffer
            self.transcript_buffer.append(result)
            
            return result
            
        except Exception as e:
            print(f"❌ Transcript processing error: {e}")
            return {'error': str(e)}
    
    def _analyze_emotion(self, text: str) -> dict:
        """Emotion analysis using DistilBERT or fallback"""
        if TEXT_EMOTION_AVAILABLE:
            try:
                emotion_result = analyze_emotion_from_text(text)
                return {
                    'emotions': emotion_result.get('emotions', self._neutral_emotions()),
                    'dominant_emotion': emotion_result.get('dominant_emotion', 'Neutral')
                }
            except Exception as e:
                print(f"⚠️ DistilBERT emotion failed: {e}")
        
        # Fallback to keyword-based
        return self._keyword_emotion_analysis(text)
    
    def _keyword_emotion_analysis(self, text: str) -> dict:
        """Fallback keyword-based emotion detection"""
        emotion_keywords = {
            'Happiness/Joy': ['happy', 'great', 'excellent', 'wonderful', 'excited', 'love', 'perfect', 'amazing', 'fantastic'],
            'Trust': ['agree', 'confident', 'reliable', 'sure', 'believe', 'trust', 'yes', 'definitely', 'absolutely'],
            'Fear/FOMO': ['worried', 'concerned', 'anxious', 'scared', 'nervous', 'uncertain', 'doubt', 'risk'],
            'Surprise': ['wow', 'unexpected', 'amazing', 'surprised', 'shocked', 'really', 'incredible'],
            'Anger': ['angry', 'frustrated', 'annoyed', 'upset', 'irritated', 'disappointed', 'terrible'],
        }
        
        text_lower = text.lower()
        emotion_scores = {emotion: 0 for emotion in emotion_keywords}
        
        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    emotion_scores[emotion] += 25
        
        # Normalize
        total = sum(emotion_scores.values())
        if total > 0:
            emotion_scores = {k: min(100, v) for k, v in emotion_scores.items()}
        else:
            emotion_scores = self._neutral_emotions()
        
        dominant = max(emotion_scores.items(), key=lambda x: x[1])
        dominant_name = dominant[0] if dominant[1] > 30 else "Neutral"
        
        return {
            'emotions': emotion_scores,
            'dominant_emotion': dominant_name
        }
    
    def _neutral_emotions(self) -> dict:
        """Neutral emotion baseline"""
        return {
            'Happiness/Joy': 20,
            'Trust': 50,
            'Fear/FOMO': 10,
            'Surprise': 10,
            'Anger': 10
        }
    
    def _detect_sarcasm(self, text: str) -> int:
        """Sarcasm detection"""
        if SARCASM_AVAILABLE:
            try:
                result = detect_sarcasm(text)
                return result.get('sarcasm_score', 0)
            except Exception as e:
                print(f"⚠️ Sarcasm detection failed: {e}")
        
        # Fallback
        sarcasm_indicators = ['yeah right', 'sure thing', 'oh great', 'fantastic', 'obviously']
        return 60 if any(ind in text.lower() for ind in sarcasm_indicators) else 0
    
    def _detect_objection(self, text: str, speaker: str) -> dict:
        """Objection detection"""
        if OBJECTIONS_AVAILABLE:
            try:
                result = detect_objections(text)
                if result.get('detected'):
                    self.conversation_metrics['objections_detected'].append(result)
                    return result
            except Exception as e:
                print(f"⚠️ Objection detection failed: {e}")
        
        # Fallback
        objection_patterns = {
            'price': ['expensive', 'costly', 'price', 'afford', 'budget'],
            'timing': ['think about it', 'later', 'not now'],
            'need': ["don't need", 'not sure', 'not interested']
        }
        
        text_lower = text.lower()
        for obj_type, keywords in objection_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return {
                        'detected': True,
                        'type': obj_type,
                        'keyword': keyword,
                        'suggestion': f"💡 {obj_type.capitalize()} objection detected. Address it directly."
                    }
        
        return {'detected': False}
    
    # === CONVERSATION ANALYTICS ===
    def get_conversation_summary(self) -> dict:
        """Generate comprehensive conversation summary"""
        total_words = self.conversation_metrics['user_word_count'] + self.conversation_metrics['prospect_word_count']
        
        if total_words == 0:
            return {'error': 'No conversation data'}
        
        user_percentage = round((self.conversation_metrics['user_word_count'] / total_words) * 100, 1)
        prospect_percentage = 100 - user_percentage
        
        # Balance recommendation
        if user_percentage > 70:
            balance_recommendation = "🗣️ You're talking too much. Let the prospect speak more."
        elif user_percentage < 30:
            balance_recommendation = "🤫 Prospect is dominating. Ask more guiding questions."
        else:
            balance_recommendation = "✅ Good conversation balance!"
        
        return {
            'user_percentage': user_percentage,
            'prospect_percentage': prospect_percentage,
            'total_words': total_words,
            'objections_count': len(self.conversation_metrics['objections_detected']),
            'balance_recommendation': balance_recommendation,
            'transcript_entries': len(self.transcript_buffer)
        }
    
    def start(self):
        """Start the analyzer"""
        self.running = True
        print("🎤 Voice Intelligence Engine started")
    
    def stop(self):
        """Stop the analyzer"""
        self.running = False
        print("🛑 Voice Intelligence Engine stopped")

# --- GLOBAL ANALYZER ---
analyzer = VoiceIntelligenceEngine()

# === SOCKET EVENTS ===
@socketio.on('connect')
def handle_connect():
    try:
        print(f'✅ Client connected: {request.sid}')
        emit('connection_status', {'status': 'connected'})
        
        # Start analyzer if not running
        if not analyzer.running:
            analyzer.start()
            
    except Exception as e:
        print(f'❌ Error in connect handler: {e}')

@socketio.on('disconnect')
def handle_disconnect():
    try:
        print(f'❌ Client disconnected: {request.sid}')
    except Exception as e:
        print(f'❌ Error in disconnect handler: {e}')

@socketio.on('identify')
def handle_identify(data):
    try:
        print(f'👤 User identified: {data}')
        time.sleep(1)
        emit('match-found', {'roomId': 'room-voice-1', 'timestamp': time.time()})
    except Exception as e:
        print(f'❌ Error in identify handler: {e}')

@socketio.on('transcript')
def handle_transcript(data):
    """Handle transcript from frontend speech recognition"""
    try:
        text = data.get('text', '')
        speaker = data.get('speaker', 'user')
        
        print(f'📝 [{speaker}]: {text}')
        
        # Process with full pipeline
        result = analyzer.process_transcript(text, speaker)
        
        # Send analysis back
        emit('analysis_result', result)
        
        # Send objection alert if detected
        if result.get('objection', {}).get('detected'):
            emit('ai-response', {
                'suggestion': result['objection']['suggestion'],
                'type': 'objection'
            })
        
        # Update analytics display
        emit('server_update', analyzer.current_analytics)
        
    except Exception as e:
        print(f'❌ Error processing transcript: {e}')
        emit('error', {'message': str(e)})

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    """Handle raw audio chunks for real-time processing"""
    try:
        audio_data = data.get('audio')
        sample_rate = data.get('sample_rate', 16000)
        
        if audio_data:
            analyzer.process_audio_chunk(audio_data, sample_rate)
            
    except Exception as e:
        print(f'❌ Error processing audio chunk: {e}')

@socketio.on('analyze-context')
def handle_analysis(data):
    """Generate AI coaching based on context"""
    try:
        print(f'🔍 Context analysis requested')
        
        # Get recent transcript
        recent_entries = list(analyzer.transcript_buffer)[-5:] if analyzer.transcript_buffer else []
        
        suggestions = []
        
        # Analyze based on current analytics
        analytics = analyzer.current_analytics
        
        # Confidence check
        if analytics['confidence'] < 40:
            suggestions.append("🎯 Low confidence detected. Speak with more conviction.")
        
        # Emotion check
        dominant = analytics['dominant_emotion']
        if dominant == 'Anger':
            suggestions.append("🚨 Prospect seems frustrated. Use active listening and empathy.")
        elif dominant == 'Fear/FOMO':
            suggestions.append("⚠️ Prospect is uncertain. Build trust and provide reassurance.")
        elif dominant in ['Happiness/Joy', 'Trust']:
            suggestions.append("✅ Positive signals! Good time to move toward commitment.")
        
        # Sarcasm check
        if analytics['sarcasm_level'] > 50:
            suggestions.append("😏 Sarcasm detected. Address concerns seriously.")
        
        # Conversation balance
        summary = analyzer.get_conversation_summary()
        if 'balance_recommendation' in summary:
            suggestions.append(summary['balance_recommendation'])
        
        if not suggestions:
            suggestions.append("📊 Conversation flow is normal. Continue with current approach.")
        
        emit('ai-response', {
            'suggestion': ' '.join(suggestions),
            'type': 'analysis',
            'timestamp': time.time()
        })
        
    except Exception as e:
        print(f'❌ Error in analysis: {e}')
        emit('error', {'message': str(e)})

@socketio.on('get_summary')
def handle_get_summary():
    """Get conversation summary"""
    try:
        summary = analyzer.get_conversation_summary()
        emit('conversation_summary', summary)
    except Exception as e:
        print(f'❌ Error getting summary: {e}')
        emit('error', {'message': str(e)})

@socketio.on('session-started')
def handle_session_start(data):
    try:
        session_id = data.get('roomId', f'session_{int(time.time())}')
        analyzer.current_session = session_id
        analyzer.transcript_buffer.clear()
        analyzer.conversation_metrics = {
            'user_word_count': 0,
            'prospect_word_count': 0,
            'objections_detected': [],
            'positive_moments': 0,
            'negative_moments': 0
        }
        print(f'🎬 Session started: {session_id}')
    except Exception as e:
        print(f'❌ Error in session start: {e}')

@socketio.on('leave-room')
def handle_leave():
    try:
        print('👋 User left room')
        # Could save session data here
    except Exception as e:
        print(f'❌ Error in leave room: {e}')

# === HTTP ROUTES ===
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
        'mode': 'Voice Intelligence',
        'features': {
            'whisper_transcription': WHISPER_AVAILABLE,
            'emotion_analysis': TEXT_EMOTION_AVAILABLE,
            'confidence_analysis': CONFIDENCE_AVAILABLE,
            'sarcasm_detection': SARCASM_AVAILABLE,
            'objection_detection': OBJECTIONS_AVAILABLE,
            'speaker_diarization': DIARIZATION_AVAILABLE
        },
        'analyzer_running': analyzer.running
    }

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """REST API for text analysis"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        speaker = data.get('speaker', 'user')
        
        result = analyzer.process_transcript(text, speaker)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# === STARTUP ===
if __name__ == '__main__':
    print("=" * 70)
    print("🎤 InsightEngine P2P - Voice Intelligence Backend")
    print("=" * 70)
    print(f"📡 Server: http://0.0.0.0:5000")
    print(f"🎯 Mode: Voice-Focused Analysis")
    print(f"")
    print("📦 Audio Pipeline Modules:")
    print(f"  🎙️  Whisper Transcription: {'✅' if WHISPER_AVAILABLE else '❌'}")
    print(f"  😊 DistilBERT Emotion: {'✅' if TEXT_EMOTION_AVAILABLE else '❌'}")
    print(f"  🎵 Librosa Confidence: {'✅' if CONFIDENCE_AVAILABLE else '❌'}")
    print(f"  😏 RoBERTa Sarcasm: {'✅' if SARCASM_AVAILABLE else '❌'}")
    print(f"  💬 spaCy Objections: {'✅' if OBJECTIONS_AVAILABLE else '❌'}")
    print(f"  👥 Pyannote Diarization: {'✅' if DIARIZATION_AVAILABLE else '❌'}")
    print(f"")
    print("🚀 Starting server...")
    print("=" * 70)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
