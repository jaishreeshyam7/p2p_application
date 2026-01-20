"""Voice-Focused P2P Backend with Audio Analysis"""

import os
import time
import base64
import threading
from collections import deque
from flask import Flask, send_from_directory, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# === AUDIO PIPELINE IMPORTS (Optional - with fallback) ===
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("⚠️ NumPy not available - some audio features disabled")

# Try importing audio processing libraries
try:
    import whisper
    WHISPER_AVAILABLE = True
    print("✅ Whisper loaded for speech-to-text")
except ImportError:
    WHISPER_AVAILABLE = False
    print("⚠️ Whisper not available - using browser speech recognition")

# --- CONFIGURATION ---
app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10000000)

# --- VOICE ANALYZER CLASS ---
class VoiceAnalyzer:
    """Analyzes voice conversations with emotion detection and coaching"""
    
    def __init__(self):
        self.transcript_buffer = deque(maxlen=100)
        self.session_data = {}
        self.current_session = None
        self.audio_buffer = deque(maxlen=30)  # Store recent audio chunks
        
        # Load Whisper model if available
        if WHISPER_AVAILABLE:
            try:
                self.whisper_model = whisper.load_model("base")
                print("✅ Whisper model loaded (base)")
            except Exception as e:
                self.whisper_model = None
                print(f"⚠️ Whisper model loading failed: {e}")
        else:
            self.whisper_model = None
        
        # Emotion keywords for text-based emotion detection
        self.emotion_keywords = {
            'Happiness/Joy': ['happy', 'great', 'excellent', 'wonderful', 'excited', 'love', 'perfect', 'amazing', 'fantastic', 'glad'],
            'Trust': ['agree', 'confident', 'reliable', 'sure', 'believe', 'trust', 'yes', 'definitely', 'absolutely', 'certain'],
            'Fear/FOMO': ['worried', 'concerned', 'anxious', 'scared', 'nervous', 'uncertain', 'doubt', 'afraid', 'risky'],
            'Surprise': ['wow', 'unexpected', 'amazing', 'surprised', 'shocked', 'really', 'incredible', 'unbelievable'],
            'Anger': ['angry', 'frustrated', 'annoyed', 'upset', 'irritated', 'disappointed', 'furious', 'mad'],
        }
        
        # Objection detection patterns
        self.objection_patterns = {
            'price': ['expensive', 'costly', 'price', 'afford', 'budget', 'too much', 'money', 'cost'],
            'timing': ['think about it', 'later', 'not now', 'maybe next time', 'get back to you', 'need time'],
            'authority': ['need to check', 'ask my boss', 'discuss with team', 'talk to', 'consult'],
            'need': ["don't need", 'not sure', 'not interested', 'no thanks', 'not necessary', 'already have'],
            'competition': ['competitor', 'other options', 'looking at others', 'comparing', 'alternative']
        }
        
        # Sarcasm indicators
        self.sarcasm_indicators = [
            'yeah right', 'sure thing', 'oh great', 'fantastic', 'wonderful',
            'obviously', 'clearly', 'of course'
        ]
        
        # Hesitation words
        self.hesitation_words = [
            'um', 'uh', 'hmm', 'well', 'actually', 'basically', 'kind of',
            'sort of', 'i guess', 'maybe', 'perhaps', 'you know'
        ]
    
    # === AUDIO PROCESSING ===
    def process_audio_chunk(self, audio_data):
        """Process incoming audio chunk with Whisper"""
        if not self.whisper_model or not NUMPY_AVAILABLE:
            return None
        
        try:
            # Convert base64 to numpy array if needed
            if isinstance(audio_data, str):
                audio_bytes = base64.b64decode(audio_data)
                audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
            else:
                audio_array = audio_data
            
            # Store in buffer
            self.audio_buffer.append(audio_array)
            
            # Transcribe with Whisper
            result = self.whisper_model.transcribe(audio_array)
            return result['text']
            
        except Exception as e:
            print(f"⚠️ Audio processing error: {e}")
            return None
    
    # === EMOTION ANALYSIS FROM TEXT ===
    def analyze_emotions_from_text(self, text: str) -> dict:
        """Detect emotions from transcript text"""
        if not text:
            return self._neutral_emotions()
        
        text_lower = text.lower()
        emotion_scores = {emotion: 0 for emotion in self.emotion_keywords}
        
        # Count emotion keywords
        for emotion, keywords in self.emotion_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    emotion_scores[emotion] += 10
        
        # Normalize scores to 0-100
        total = sum(emotion_scores.values())
        if total > 0:
            emotion_scores = {k: min(100, int((v / total) * 100)) for k, v in emotion_scores.items()}
        else:
            emotion_scores = self._neutral_emotions()
        
        # Ensure Trust baseline
        if all(v < 20 for v in emotion_scores.values()):
            emotion_scores['Trust'] = 50
        
        # Find dominant emotion
        dominant = max(emotion_scores.items(), key=lambda x: x[1])
        dominant_name = dominant[0] if dominant[1] > 30 else "Trust"
        
        return {
            'emotions': emotion_scores,
            'dominant_emotion': dominant_name
        }
    
    def _neutral_emotions(self) -> dict:
        """Return neutral emotion baseline"""
        return {
            'Happiness/Joy': 20,
            'Trust': 50,
            'Fear/FOMO': 10,
            'Surprise': 10,
            'Anger': 10
        }
    
    # === OBJECTION DETECTION ===
    def detect_objection(self, text: str) -> dict:
        """Detect sales objections in conversation"""
        text_lower = text.lower()
        
        for objection_type, keywords in self.objection_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    suggestions = self._get_objection_suggestion(objection_type)
                    return {
                        'detected': True,
                        'type': objection_type,
                        'keyword': keyword,
                        'text': text,
                        'suggestion': suggestions,
                        'timestamp': time.time()
                    }
        
        return {'detected': False}
    
    def _get_objection_suggestion(self, objection_type: str) -> str:
        """Get coaching suggestion for objection type"""
        suggestions = {
            'price': "💰 Price objection detected. Focus on value and ROI. Ask: 'What would you compare this investment to?'",
            'timing': "⏰ Timing objection. Create urgency: 'What would need to change for you to move forward today?'",
            'authority': "👔 Authority objection. Ask: 'Who else should be part of this conversation?'",
            'need': "🤔 Need objection. Dig deeper: 'What are your current challenges in this area?'",
            'competition': "🏆 Competition objection. Differentiate: 'What's most important to you in a solution?'"
        }
        return suggestions.get(objection_type, "Address the concern directly.")
    
    # === TONE ANALYSIS ===
    def analyze_tone(self, text: str) -> dict:
        """Analyze tone, sarcasm, confidence"""
        text_lower = text.lower()
        
        # Sarcasm detection
        sarcasm_score = sum(1 for indicator in self.sarcasm_indicators if indicator in text_lower) * 30
        sarcasm_score = min(100, sarcasm_score)
        
        # Confidence level (inverse of hesitation)
        words = text.split()
        word_count = len(words)
        hesitation_count = sum(1 for word in words if word.lower() in self.hesitation_words)
        hesitation_ratio = hesitation_count / word_count if word_count > 0 else 0
        confidence_score = max(0, int(100 - (hesitation_ratio * 200)))
        
        # Sentiment
        positive_words = ['great', 'excellent', 'amazing', 'love', 'perfect', 'wonderful', 'good', 'happy']
        negative_words = ['bad', 'terrible', 'awful', 'horrible', 'worst', 'hate', 'poor', 'disappointed']
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            sentiment = 'positive'
        elif negative_count > positive_count:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        return {
            'sarcasm_score': sarcasm_score,
            'confidence_score': confidence_score,
            'sentiment': sentiment,
            'hesitation_ratio': round(hesitation_ratio, 3)
        }
    
    # === CONVERSATION ANALYTICS ===
    def add_transcript(self, text: str, speaker: str) -> dict:
        """Add transcript entry with metadata"""
        timestamp = time.time()
        words = text.split()
        word_count = len(words)
        
        entry = {
            'text': text,
            'speaker': speaker,
            'timestamp': timestamp,
            'word_count': word_count
        }
        
        self.transcript_buffer.append(entry)
        return entry
    
    def get_conversation_balance(self) -> dict:
        """Analyze conversation balance between speakers"""
        if not self.transcript_buffer:
            return {'user_percentage': 50, 'prospect_percentage': 50, 'recommendation': 'No data yet'}
        
        user_entries = [t for t in self.transcript_buffer if t['speaker'] == 'user']
        prospect_entries = [t for t in self.transcript_buffer if t['speaker'] == 'prospect']
        
        user_words = sum(t['word_count'] for t in user_entries)
        prospect_words = sum(t['word_count'] for t in prospect_entries)
        
        total_words = user_words + prospect_words
        
        if total_words == 0:
            return {'user_percentage': 50, 'prospect_percentage': 50, 'recommendation': 'Start speaking'}
        
        user_percentage = round((user_words / total_words) * 100, 1)
        prospect_percentage = round((prospect_words / total_words) * 100, 1)
        
        # Generate recommendation
        if user_percentage > 70:
            recommendation = "🗣️ You're talking too much. Let the prospect speak more."
        elif user_percentage < 30:
            recommendation = "🤫 Prospect is dominating. Ask more guiding questions."
        else:
            recommendation = "✅ Good conversation balance!"
        
        return {
            'user_percentage': user_percentage,
            'prospect_percentage': prospect_percentage,
            'user_words': user_words,
            'prospect_words': prospect_words,
            'recommendation': recommendation
        }
    
    # === COMPREHENSIVE ANALYSIS ===
    def analyze_comprehensive(self, text: str, speaker: str) -> dict:
        """Run all analyses together"""
        # Add to transcript buffer
        transcript_entry = self.add_transcript(text, speaker)
        
        # Emotion analysis
        emotion_data = self.analyze_emotions_from_text(text)
        
        # Objection detection
        objection_data = self.detect_objection(text)
        
        # Tone analysis
        tone_data = self.analyze_tone(text)
        
        # Conversation metrics
        balance = self.get_conversation_balance()
        
        return {
            'transcript': transcript_entry,
            'emotions': emotion_data['emotions'],
            'dominant_emotion': emotion_data['dominant_emotion'],
            'objection': objection_data,
            'tone': tone_data,
            'conversation_balance': balance,
            'timestamp': time.time()
        }

# --- GLOBAL ANALYZER ---
analyzer = VoiceAnalyzer()

# --- SOCKET EVENTS ---
@socketio.on('connect')
def handle_connect():
    try:
        print(f'✅ Client connected: {request.sid}')
        emit('connection_status', {'status': 'connected', 'mode': 'voice-focused'})
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
        emit('error', {'message': 'Failed to identify user'})

@socketio.on('transcript')
def handle_transcript(data):
    """Handle incoming transcript from speech recognition"""
    try:
        text = data.get('text', '')
        speaker = data.get('speaker', 'user')
        
        print(f'📝 [{speaker}]: {text}')
        
        # Run comprehensive analysis
        analysis = analyzer.analyze_comprehensive(text, speaker)
        
        # Send real-time emotion update
        socketio.emit('server_update', {
            'hr': 70,  # Placeholder - can be integrated with wearables
            'dominant_emotion': analysis['dominant_emotion'],
            'emotions': analysis['emotions'],
            'gaze_x': 50,
            'gaze_y': 50
        })
        
        # Send detailed analysis
        emit('analysis_result', analysis)
        
        # If objection detected, send immediate alert
        if analysis['objection']['detected']:
            emit('ai-response', {
                'suggestion': analysis['objection']['suggestion'],
                'type': 'objection'
            })
            emit('objection_alert', {
                'type': analysis['objection']['type'],
                'suggestion': analysis['objection']['suggestion']
            })
        
    except Exception as e:
        print(f'❌ Error processing transcript: {e}')
        emit('error', {'message': str(e)})

@socketio.on('audio-chunk')
def handle_audio_chunk(data):
    """Handle raw audio data for Whisper transcription"""
    try:
        audio_data = data.get('audio', None)
        if audio_data and analyzer.whisper_model:
            text = analyzer.process_audio_chunk(audio_data)
            if text:
                # Process the transcribed text
                handle_transcript({'text': text, 'speaker': 'user'})
    except Exception as e:
        print(f'❌ Error processing audio: {e}')

@socketio.on('analyze-context')
def handle_analysis(data):
    try:
        print(f'🔍 Analysis requested: {data}')
        transcript = data.get('transcript', '')
        emotions = data.get('emotions', {})
        
        suggestions = []
        
        # Analyze based on emotion levels
        trust_level = emotions.get('Trust', 0)
        if trust_level > 60:
            suggestions.append("✅ Strong trust signals. Good time to move toward commitment.")
        elif trust_level < 30:
            suggestions.append("⚠️ Low trust detected. Focus on building rapport and credibility.")
        
        anger_level = emotions.get('Anger', 0)
        if anger_level > 40:
            suggestions.append("🚨 Frustration detected. Consider active listening and empathy.")
        
        # Get conversation balance
        balance = analyzer.get_conversation_balance()
        suggestions.append(balance['recommendation'])
        
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
        session_id = data.get('roomId', f'session_{int(time.time())}')
        analyzer.current_session = session_id
        analyzer.transcript_buffer.clear()
        print(f'🎬 Session started: {session_id}')
        emit('session_confirmed', {'session_id': session_id})
    except Exception as e:
        print(f'❌ Error in session start handler: {e}')

@socketio.on('leave-room')
def handle_leave():
    try:
        print('👋 User left room')
        analyzer.transcript_buffer.clear()
    except Exception as e:
        print(f'❌ Error in leave room handler: {e}')

@socketio.on('get_conversation_summary')
def handle_get_summary():
    """Get conversation summary"""
    try:
        balance = analyzer.get_conversation_balance()
        
        # Get full transcript
        transcript_text = '\n'.join([
            f"[{t['speaker']}]: {t['text']}" 
            for t in analyzer.transcript_buffer
        ])
        
        emit('conversation_summary', {
            'balance': balance,
            'transcript': transcript_text,
            'total_messages': len(analyzer.transcript_buffer)
        })
        
    except Exception as e:
        print(f'❌ Error getting summary: {e}')
        emit('error', {'message': str(e)})

# --- HTTP ROUTES ---
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
        'mode': 'Voice-Focused',
        'whisper_available': WHISPER_AVAILABLE,
        'features': [
            'Speech-to-Text (Browser + Whisper)' if WHISPER_AVAILABLE else 'Speech-to-Text (Browser)',
            'Emotion Detection (Text-based)',
            'Objection Detection',
            'Tone Analysis',
            'Conversation Analytics'
        ]
    }

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """REST API endpoint for text analysis"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        speaker = data.get('speaker', 'user')
        
        result = analyzer.analyze_comprehensive(text, speaker)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# --- STARTUP ---
if __name__ == '__main__':
    print("=" * 60)
    print("🎤 InsightEngine P2P Backend - Voice-Focused Mode")
    print("=" * 60)
    print(f"📡 Server: http://0.0.0.0:5000")
    print(f"🎙️ Mode: Voice & Text Analysis")
    print(f"🗣️ Speech-to-Text: {'Whisper (AI) + Browser' if WHISPER_AVAILABLE else 'Browser Only'}")
    print(f"😊 Emotion Detection: Text-based Analysis")
    print(f"🎭 Tone Analysis: Active")
    print(f"💬 Objection Detection: Active")
    print(f"📊 Conversation Analytics: Active")
    print("=" * 60)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)