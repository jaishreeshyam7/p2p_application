import os
import time
import random
import threading
from collections import deque
from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# --- CONFIGURATION ---
app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class RobustAnalyzer:
    def __init__(self):
        self.fs = 30
        self.buffer = deque(maxlen=self.fs * 10)
        self.running = False
        
    def stream_simulation(self):
        """Forces mock data to keep the dashboard alive"""
        print("🚀 SIMULATION STREAM STARTED. Sending data to frontend...")
        self.running = True
        
        while self.running:
            try:
                # Create realistic looking fake data
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
                print(f"❌ Error in simulation stream: {e}")
                time.sleep(1.0)
    
    def stop(self):
        self.running = False

# --- GLOBAL ANALYZER ---
analyzer = RobustAnalyzer()

# --- SOCKET EVENTS ---
@socketio.on('connect')
def handle_connect():
    try:
        print(f'✅ Client connected: {request.sid}')
        emit('connection_status', {'status': 'connected'})
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
        # Simulate match found after 2 seconds
        time.sleep(2)
        emit('match-found', {'roomId': 'room-beta-1', 'timestamp': time.time()})
    except Exception as e:
        print(f'❌ Error in identify handler: {e}')
        emit('error', {'message': 'Failed to identify user'})

@socketio.on('transcript')
def handle_transcript(data):
    try:
        print(f'📝 Transcript received: {data}')
        speaker = data.get('speaker', 'unknown')
        text = data.get('text', '')
        
        # Simple objection detection
        objections = ['expensive', 'costly', 'think about it', 'not sure', 'too much']
        if any(word in text.lower() for word in objections):
            suggestion = f"💡 Objection detected: '{text}'. Consider addressing value proposition and ROI benefits."
            emit('ai-response', {'suggestion': suggestion, 'type': 'objection'})
    except Exception as e:
        print(f'❌ Error in transcript handler: {e}')
        emit('error', {'message': 'Failed to process transcript'})

@socketio.on('analyze-context')
def handle_analysis(data):
    try:
        print(f'🔍 Analysis requested: {data}')
        transcript = data.get('transcript', '')
        emotions = data.get('emotions', {})
        hr = data.get('hr', 0)
        
        # Generate AI coaching based on data
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
        })
    except Exception as e:
        print(f'❌ Error in analysis handler: {e}')
        emit('error', {'message': 'Failed to analyze context'})

@socketio.on('session-started')
def handle_session_start(data):
    try:
        print(f'🎬 Session started: {data}')
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
    return {'status': 'healthy', 'analyzer_running': analyzer.running}

# --- STARTUP ---
def start_background_task():
    time.sleep(2)
    analyzer.stream_simulation()

if __name__ == '__main__':
    # Start data stream
    threading.Thread(target=start_background_task, daemon=True).start()
    
    print("🌍 Server starting on port 5000...")
    print("📡 WebSocket server ready")
    print("🔗 Frontend will be available at: http://localhost:5000")
    
    # Note: Remove allow_unsafe_werkzeug=True in production
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
