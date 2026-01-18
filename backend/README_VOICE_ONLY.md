# 🎤 Voice-Only P2P Backend

A lightweight backend for real-time conversation analysis **without video processing**.

## ✨ Features

### 1. **Emotion Detection from Text**
- Analyzes transcript text to detect emotions:
  - Happiness/Joy
  - Trust
  - Fear/FOMO
  - Surprise
  - Anger
- Returns emotion scores (0-100)
- Identifies dominant emotion

### 2. **Sales Objection Detection**
- Detects 5 types of objections:
  - **Price** - "expensive", "costly", "too much"
  - **Timing** - "think about it", "later", "not now"
  - **Authority** - "ask my boss", "discuss with team"
  - **Need** - "don't need", "not interested"
  - **Competition** - "other options", "comparing"
- Provides coaching suggestions for each objection type

### 3. **Tone & Sarcasm Analysis**
- **Sarcasm Detection** - Detects non-literal communication
- **Confidence Analysis** - Measures hesitation vs certainty
- **Sentiment Analysis** - Positive, negative, or neutral
- **Urgency Detection** - Identifies time-sensitive language

### 4. **Conversation Analytics**
- **Speaking Balance** - User vs Prospect word count
- **Speaking Rate** - Words per minute
- **Pause Detection** - Identifies awkward silences
- **Conversation Recommendations** - AI coaching tips

---

## 🚀 Quick Start

### Installation

```bash
cd backend
pip install -r requirements_voice_only.txt
```

### Run the Server

```bash
python app_voice_only.py
```

Server will start on: `http://localhost:5000`

---

## 📡 WebSocket Events

### Client → Server

#### 1. **Send Transcript**
```javascript
socket.emit('transcript', {
    text: "I think the pricing is a bit high",
    speaker: "prospect"  // or "user"
});
```

**Response:**
```javascript
socket.on('analysis_result', (data) => {
    console.log(data.emotions);          // Emotion scores
    console.log(data.dominant_emotion);  // "Anger" or "Trust" etc.
    console.log(data.objection);         // Objection details
    console.log(data.tone);              // Sarcasm, confidence, sentiment
    console.log(data.conversation_balance); // Speaking ratios
});
```

#### 2. **Start Session**
```javascript
socket.emit('start_session', {
    session_id: "demo_session_123"
});
```

#### 3. **Get Conversation Summary**
```javascript
socket.emit('get_conversation_summary');

socket.on('conversation_summary', (data) => {
    console.log(data.balance);     // Who's talking more
    console.log(data.patterns);    // Speaking rate, pauses
    console.log(data.transcript);  // Full conversation text
});
```

### Server → Client

#### **Objection Alert**
```javascript
socket.on('objection_alert', (data) => {
    console.log(data.type);        // "price", "timing", etc.
    console.log(data.suggestion);  // Coaching tip
});
```

---

## 🔌 REST API Endpoints

### **POST /api/analyze**

Analyze text without WebSocket.

```bash
curl -X POST http://localhost:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "text": "This is too expensive for us",
    "speaker": "prospect"
  }'
```

**Response:**
```json
{
  "emotions": {
    "Happiness/Joy": 10,
    "Trust": 20,
    "Fear/FOMO": 30,
    "Surprise": 5,
    "Anger": 35
  },
  "dominant_emotion": "Anger",
  "objection": {
    "detected": true,
    "type": "price",
    "keyword": "expensive",
    "suggestion": "💰 Price objection detected. Focus on value and ROI..."
  },
  "tone": {
    "sarcasm_score": 0,
    "confidence_score": 65,
    "sentiment": "negative",
    "urgency_score": 0
  },
  "conversation_balance": {
    "user_percentage": 45.0,
    "prospect_percentage": 55.0,
    "recommendation": "✅ Good conversation balance!"
  }
}
```

### **GET /health**

Check server status.

```bash
curl http://localhost:5000/health
```

---

## 📊 Example Analysis Output

### Input:
```json
{
  "text": "I'm not sure if this is the right fit for us. It seems expensive and I need to talk to my team first.",
  "speaker": "prospect"
}
```

### Output:
```json
{
  "emotions": {
    "Happiness/Joy": 0,
    "Trust": 15,
    "Fear/FOMO": 45,
    "Surprise": 10,
    "Anger": 30
  },
  "dominant_emotion": "Fear/FOMO",
  "objection": {
    "detected": true,
    "type": "authority",
    "keyword": "talk to my team",
    "suggestion": "👔 Authority objection. Ask: 'Who else should be part of this conversation?'"
  },
  "tone": {
    "sarcasm_score": 0,
    "confidence_score": 42,
    "sentiment": "negative",
    "urgency_score": 0,
    "hesitation_ratio": 0.083
  },
  "conversation_balance": {
    "user_percentage": 35.2,
    "prospect_percentage": 64.8,
    "recommendation": "🤫 Prospect is dominating. Ask more guiding questions."
  },
  "speaking_patterns": {
    "words_per_minute": 142.3,
    "total_words": 156,
    "pause_count": 2,
    "avg_pause_duration": 4.2
  }
}
```

---

## 🎯 Use Cases

### 1. **Sales Calls**
- Detect when prospect raises objections
- Get real-time coaching suggestions
- Monitor conversation balance
- Identify buying signals vs resistance

### 2. **Phone Conversations**
- Works without video (audio-only)
- Analyze tone and sentiment
- Track speaking patterns
- Measure confidence levels

### 3. **Customer Support**
- Detect frustration or anger
- Identify urgent issues
- Monitor agent performance
- Improve response quality

### 4. **Meeting Analysis**
- Track who dominates conversation
- Identify key concerns
- Measure engagement
- Generate meeting summaries

---

## 🔧 Future Enhancements

### Planned Features:
- [ ] Real speech-to-text integration (Web Speech API / Whisper)
- [ ] Multi-language support
- [ ] Custom objection patterns
- [ ] AI-powered suggestions (GPT/Claude integration)
- [ ] Session recording & playback
- [ ] Export to CSV/PDF
- [ ] Real-time dashboard
- [ ] Call scoring system

---

## 🆚 Comparison: Voice-Only vs Video Backend

| Feature | Voice-Only | Video Backend |
|---------|------------|---------------|
| **Dependencies** | Minimal (Flask, SocketIO) | Heavy (OpenCV, MediaPipe, DeepFace) |
| **Performance** | ⚡ Fast | 🐌 Slower |
| **CPU Usage** | 💚 Low | 🔴 High |
| **Works on Phone** | ✅ Yes | ❌ No |
| **Emotion Detection** | Text-based | Facial recognition |
| **Heart Rate** | ❌ No | ✅ Yes |
| **Gaze Tracking** | ❌ No | ✅ Yes |
| **Objection Detection** | ✅ Yes | ✅ Yes |
| **Tone Analysis** | ✅ Yes | ⚠️ Limited |
| **Conversation Analytics** | ✅ Yes | ⚠️ Limited |

---

## 🐛 Troubleshooting

### Issue: Port 5000 already in use
```bash
# Find process using port 5000
lsof -i :5000

# Kill the process
kill -9 <PID>

# Or use a different port
python app_voice_only.py --port 8000
```

### Issue: WebSocket connection fails
- Check CORS settings
- Verify frontend is connecting to correct URL
- Ensure firewall allows port 5000

### Issue: No analysis results
- Check that transcript text is not empty
- Verify speaker is "user" or "prospect"
- Check browser console for errors

---

## 📝 License

MIT License - Feel free to use in your projects!

---

## 🤝 Contributing

Pull requests welcome! Please test thoroughly before submitting.

---

**Made with ❤️ for better conversations**
