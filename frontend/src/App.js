import React, { useState, useRef, useEffect, useCallback } from 'react';
import './App.css';
import io from 'socket.io-client';
import { Mic, MicOff, PhoneOff, Activity, Bot, AlignLeft, Volume2 } from 'lucide-react';
import webgazer from 'webgazer';

// ==========================================
// 1. SUBCOMPONENTS
// ==========================================
const MetricBar = ({ label, value, max, color }) => (
  <div className="mb-2">
    <div className="flex justify-between text-xs mb-1">
      <span className="text-gray-400">{label}</span>
      <span className="text-gray-300 font-mono">{value}{max ? `/${max}` : ''}</span>
    </div>
    <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
      <div 
        className={`h-full ${color} rounded-full transition-all duration-500`} 
        style={{ width: `${max ? (value/max)*100 : value}%` }} 
      />
    </div>
  </div>
);

// ==========================================
// 2. CUSTOM HOOKS (Extracted Logic)
// ==========================================
const useEyeTracking = () => {
  const [isLookingAway, setIsLookingAway] = useState(false);

  const initEyeTracking = useCallback(async () => {
    try {
      await webgazer.setGazeListener((data) => {
        if (!data) return;

        const screenWidth = window.innerWidth;
        const screenHeight = window.innerHeight;

        // "Safe Zone" (center 60% of screen)
        const isOutX = data.x < screenWidth * 0.2 || data.x > screenWidth * 0.8;
        const isOutY = data.y < screenHeight * 0.1 || data.y > screenHeight * 0.9;

        setIsLookingAway(isOutX || isOutY);
      }).begin();

      // Run silently in the background
      webgazer.showVideoPreview(false);
      webgazer.showPredictionPoints(false); 
    } catch (e) {
      console.error("Eye tracking failed:", e);
    }
  }, []);

  const stopEyeTracking = useCallback(() => {
    if (window.webgazer) {
      window.webgazer.pause();
      window.webgazer.end();
    }
    setIsLookingAway(false);
  }, []);

  return { isLookingAway, initEyeTracking, stopEyeTracking };
};

// ==========================================
// 3. MAIN APPLICATION COMPONENT
// ==========================================
const InsightEngineApp = () => {
  // --- STATE MANAGEMENT ---
  const [isInLobby, setIsInLobby] = useState(true);
  const [isWaiting, setIsWaiting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('offline');
  const [currentRoomId, setCurrentRoomId] = useState(null); 
  
  const [transcript, setTranscript] = useState([]);
  const [aiSuggestion, setAiSuggestion] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  
  const [voiceAnalytics, setVoiceAnalytics] = useState({ confidence_score: 0, pitch_stability: 0, volume_stability: 0 });
  const [voiceMetrics, setVoiceMetrics] = useState({ wpm: 0, pauses_count: 0 });
  const [dominantEmotion, setDominantEmotion] = useState('neutral');
  const [sarcasmDetected, setSarcasmDetected] = useState(false);

  // --- REFS & CUSTOM HOOKS ---
  const localAudioRef = useRef(null);
  const socketRef = useRef(null);
  const recognitionRef = useRef(null);
<<<<<<< HEAD
  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const transcriptFeedRef = useRef(null);
=======
  const activeRecorderRef = useRef(null); 
  const isStreamingRef = useRef(false);   
  const transcriptFeedRef = useRef(null);
  
  // Bring in our custom eye tracking logic
  const { isLookingAway, initEyeTracking, stopEyeTracking } = useEyeTracking();
>>>>>>> c687ba6 (important changes)

  // --- CONNECTION LOGIC ---
  const getBackendURL = () => {
    if (process.env.REACT_APP_BACKEND_URL) return process.env.REACT_APP_BACKEND_URL;
    const hostname = window.location.hostname;
    if (hostname.includes('github.dev') || hostname.includes('app.github.dev')) {
      const match = hostname.match(/([\w-]+)-\d+\.app\.github\.dev/);
      if (match) return `https://${match[1]}-5000.app.github.dev`;
      return window.location.origin.replace('-3000.', '-5000.');
    }
    return hostname === 'localhost' ? 'http://localhost:5000' : window.location.origin;
  };

  useEffect(() => {
    const BACKEND_URL = getBackendURL();
    socketRef.current = io(BACKEND_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      path: '/socket.io'
    });

    socketRef.current.on('connect', () => setConnectionStatus('online'));
    socketRef.current.on('disconnect', () => setConnectionStatus('offline'));

    // Metric Listeners
    socketRef.current.on('transcription-result', (data) => addTranscript(data.speaker || 'Detected', data.text));
    socketRef.current.on('confidence-update', (data) => setVoiceAnalytics(prev => ({ ...prev, ...data })));
    socketRef.current.on('voice-metrics', (data) => setVoiceMetrics(prev => ({ ...prev, ...data })));
    socketRef.current.on('emotion-update', (data) => { if (data.dominant) setDominantEmotion(data.dominant); });
    
    // Gemini Chatbot Listener
    socketRef.current.on('ai-response', (data) => setAiSuggestion(data.suggestion));

    // Session Listeners
    socketRef.current.on('match-found', handleMatchFound);
    socketRef.current.on('peer-disconnected', () => {
      addTranscript('System', '👋 Partner left');
      setTimeout(stopSession, 2000);
    });

    return () => {
      socketRef.current?.disconnect();
      stopMediaStreams();
      stopEyeTracking();
    };
  }, []);

  // --- ACTIONS ---
  const startMatchmaking = async () => {
    setIsInLobby(false);
    setIsWaiting(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      localAudioRef.current = stream;
      setConnectionStatus('connecting');
      socketRef.current?.emit('identify', { type: 'user' });
      // Simulate match
      setTimeout(() => handleMatchFound({ roomId: 'room-' + Date.now() }), 1500);
    } catch (err) {
      alert('Microphone access required');
      stopSession();
    }
  };

  const handleMatchFound = (data) => {
    setIsWaiting(false);
    setIsConnected(true);
    setConnectionStatus('connected');
    setCurrentRoomId(data.roomId);
    
    initSpeechRecognition();
    startAudioStreaming(data.roomId);
    initEyeTracking(); // Start monitoring the webcam for eye movement
    
    socketRef.current?.emit('session-started', { roomId: data.roomId });
    addTranscript('System', `🎯 Session Active`);
  };

  const startAudioStreaming = (roomId) => {
    if (!localAudioRef.current) return;
    isStreamingRef.current = true;

    const recordSegment = () => {
      if (!isStreamingRef.current || !localAudioRef.current) return;

      try {
        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
        const recorder = new MediaRecorder(localAudioRef.current, { mimeType, audioBitsPerSecond: 16000 });
        const chunks = [];

        recorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.push(event.data); };
        recorder.onstop = () => {
          if (chunks.length > 0 && socketRef.current && !isMuted) {
            const blob = new Blob(chunks, { type: mimeType });
            const reader = new FileReader();
            reader.onloadend = () => {
              if (reader.result) {
                socketRef.current.emit('audio-chunk', { audio: reader.result.split(',')[1], roomId: roomId });
              }
            };
            reader.readAsDataURL(blob);
          }
          if (isStreamingRef.current) recordSegment();
        };

        activeRecorderRef.current = recorder;
        recorder.start();
        setTimeout(() => { if (recorder.state === 'recording') recorder.stop(); }, 3000);
      } catch (e) { console.error('Streaming error', e); }
    };

    recordSegment();
  };

  const stopSession = () => {
    setIsConnected(false);
    setIsWaiting(false);
    setIsInLobby(true);
    setConnectionStatus('online');
    setTranscript([]);
    setAiSuggestion('');
    
    isStreamingRef.current = false;
    stopMediaStreams();
    stopSpeechRecognition();
    stopEyeTracking(); // Stop WebGazer
    
    socketRef.current?.emit('leave-room');
  };

  const stopMediaStreams = () => {
    if (activeRecorderRef.current && activeRecorderRef.current.state !== 'inactive') activeRecorderRef.current.stop();
    localAudioRef.current?.getTracks().forEach(t => t.stop());
  };

  const toggleMute = () => {
    if (localAudioRef.current) {
      localAudioRef.current.getAudioTracks().forEach(t => t.enabled = !t.enabled);
      setIsMuted(!isMuted);
    }
  };

  const initSpeechRecognition = () => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) return;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognitionRef.current = new SpeechRecognition();
    recognitionRef.current.continuous = true;
    recognitionRef.current.interimResults = true;
    recognitionRef.current.lang = 'en-US';

    recognitionRef.current.onresult = (event) => {
      const last = event.results.length - 1;
      if (event.results[last].isFinal) {
        const text = event.results[last][0].transcript;
        addTranscript('You', text);
        socketRef.current?.emit('transcript', { speaker: 'user', text, timestamp: Date.now(), roomId: currentRoomId });
      }
    };
    
    recognitionRef.current.onerror = (e) => { if (e.error === 'network') setTimeout(() => recognitionRef.current?.start(), 1000); };
    try { recognitionRef.current.start(); } catch (e) {}
  };

  const stopSpeechRecognition = () => recognitionRef.current?.stop();

  const addTranscript = (speaker, text) => {
    setTranscript(prev => [...prev, { id: Date.now() + Math.random(), speaker, text, timestamp: new Date().toLocaleTimeString() }]);
  };

  const handleManualInput = (e) => {
    if (e.key === 'Enter' && e.target.value.trim()) {
      addTranscript('You', e.target.value);
      socketRef.current?.emit('transcript', { speaker: 'user', text: e.target.value, timestamp: Date.now(), roomId: currentRoomId });
      e.target.value = '';
    }
  };

  const triggerAnalysis = () => {
    const recent = transcript.slice(-5).map(t => `${t.speaker}: ${t.text}`).join('\n');
    socketRef.current?.emit('analyze-context', { transcript: recent, roomId: currentRoomId });
    setAiSuggestion('🔍 Gemini is analyzing context...');
  };

<<<<<<< HEAD
  // Auto-scroll transcript to bottom when new messages arrive
  useEffect(() => {
    if (transcriptFeedRef.current) {
      transcriptFeedRef.current.scrollTop = transcriptFeedRef.current.scrollHeight;
    }
=======
  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptFeedRef.current) transcriptFeedRef.current.scrollTop = transcriptFeedRef.current.scrollHeight;
>>>>>>> c687ba6 (important changes)
  }, [transcript]);

  // --- RENDER UI ---
  return (
<<<<<<< HEAD
    <div className="bg-gray-900 text-gray-100 h-screen overflow-hidden flex flex-col">
      {/* Navbar */}
      <nav className="h-16 bg-gray-900 border-b border-gray-800 flex justify-between items-center px-4 md:px-6 z-50 flex-shrink-0">
=======
    <div className="bg-gray-900 text-gray-100 h-screen w-screen overflow-hidden flex flex-col font-sans">
      
      {/* NAVBAR */}
      <nav className="h-16 bg-gray-900 border-b border-gray-800 flex justify-between items-center px-4 md:px-6 flex-shrink-0 z-50">
>>>>>>> c687ba6 (important changes)
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-indigo-600 rounded flex items-center justify-center">
            <Mic className="w-4 h-4 text-white" />
          </div>
          <h1 className="font-bold text-lg hidden md:block">InsightEngine <span className="text-xs font-normal text-gray-500">Voice</span></h1>
        </div>
        <div className="flex items-center gap-4">
           <div className={`w-2 h-2 rounded-full ${connectionStatus === 'online' || connectionStatus === 'connected' ? 'bg-green-500' : 'bg-red-500'}`} />
           {isConnected && (
            <div className="flex gap-2">
              <button onClick={toggleMute} className="px-3 py-1 bg-gray-800 rounded border border-gray-700 text-sm flex items-center gap-2">
                {isMuted ? <MicOff className="w-3 h-3"/> : <Mic className="w-3 h-3"/>}
                {isMuted ? 'Unmute' : 'Mute'}
              </button>
              <button onClick={stopSession} className="px-3 py-1 bg-red-900/50 text-red-200 rounded border border-red-900 text-sm flex items-center gap-2">
                <PhoneOff className="w-3 h-3"/> End
              </button>
            </div>
           )}
        </div>
      </nav>

 HEAD
      {/* Lobby Screen */}
      {isInLobby && (
        <div className="absolute inset-0 top-16 z-50 bg-gray-900 flex flex-col items-center justify-center p-4">
          <div className="max-w-md w-full text-center space-y-8 bg-gray-800/30 p-8 rounded-2xl border border-gray-700/50 backdrop-blur-sm">
            <div className="relative inline-block">
              <div className="absolute inset-0 bg-indigo-600 blur-2xl opacity-20 rounded-full animate-pulse"></div>
              <div className="w-20 h-20 bg-gray-800 rounded-full flex items-center justify-center border border-gray-700 relative z-10 mx-auto">
                <Volume2 className="w-8 h-8 text-indigo-500" />
              </div>
            </div>
            
            <div className="space-y-2">
              <h2 className="text-3xl font-bold text-white">Voice Sales Coach</h2>
              <p className="text-gray-400 text-sm">
                AI-powered voice analysis with transcription, emotion detection, and real-time coaching.
              </p>
            </div>
            
            <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700 text-left space-y-3">
              <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Voice Modules Status</h3>
              
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex items-center gap-2 text-gray-300">
                  <span className={`w-2 h-2 rounded-full ${voiceModules.transcribe ? 'bg-green-500' : 'bg-gray-600'}`}></span>
                  <span>Transcription</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <span className={`w-2 h-2 rounded-full ${voiceModules.text_emotion ? 'bg-green-500' : 'bg-gray-600'}`}></span>
                  <span>Emotion AI</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <span className={`w-2 h-2 rounded-full ${voiceModules.sarcasm ? 'bg-green-500' : 'bg-gray-600'}`}></span>
                  <span>Sarcasm</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <span className={`w-2 h-2 rounded-full ${voiceModules.objections ? 'bg-green-500' : 'bg-gray-600'}`}></span>
                  <span>Objections</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <span className={`w-2 h-2 rounded-full ${voiceModules.confidence ? 'bg-green-500' : 'bg-gray-600'}`}></span>
                  <span>Confidence</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <span className={`w-2 h-2 rounded-full ${connectionStatus === 'online' || connectionStatus === 'connected' ? 'bg-green-500' : 'bg-yellow-500'}`}></span>
                  <span>Backend</span>
                </div>
              </div>
            </div>

            <button 
              onClick={startMatchmaking}
              disabled={connectionStatus === 'offline' || connectionStatus === 'error'}
              className="group w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed text-white py-3 rounded-xl font-bold text-lg shadow-lg shadow-indigo-500/30 transition-all transform hover:scale-[1.02] active:scale-[0.98]"
            >
              {connectionStatus === 'offline' || connectionStatus === 'error' ? 'Connecting...' : 'Start Voice Session →'}
            </button>
          </div>
        </div>
      )}

      {/* Main Content - FIXED HEIGHT CONSTRAINT */}
      <div className="flex-1 grid md:grid-cols-[1fr_400px] overflow-hidden min-h-0">
        
        {/* Voice Visualization Area */}
        <div className="relative bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 flex items-center justify-center overflow-hidden">
          
          {isConnected && (
            <div className="text-center space-y-8 w-full max-w-3xl px-8 overflow-y-auto max-h-full">
              <div className="relative">
                <div className="absolute inset-0 bg-indigo-500 blur-3xl opacity-30 animate-pulse"></div>
                <div className="w-40 h-40 bg-gradient-to-br from-indigo-600 to-purple-600 rounded-full flex items-center justify-center relative z-10 shadow-2xl shadow-indigo-500/50 mx-auto">
                  {isMuted ? <MicOff className="w-16 h-16 text-white" /> : <Volume2 className="w-16 h-16 text-white animate-pulse" />}
                </div>
              </div>
              
              <div className="space-y-3">
                <h2 className="text-2xl font-bold text-white">Voice Analysis Active</h2>
                <div className="flex items-center justify-center gap-2 text-indigo-300">
                  <div className="w-2 h-2 bg-indigo-400 rounded-full animate-pulse"></div>
                  <span className="text-sm">Real-time AI coaching...</span>
                </div>
                {sarcasmDetected && (
                  <div className="text-yellow-400 text-sm animate-bounce">😏 Sarcasm Detected!</div>
                )}
              </div>
      {/* MAIN LAYOUT GRID */}
      <div className="flex-1 flex flex-col md:grid md:grid-cols-[1fr_400px] min-h-0 overflow-hidden relative">
        
        {/* LOBBY OVERLAY */}
        {isInLobby && (
          <div className="absolute inset-0 z-40 bg-gray-900 flex flex-col items-center justify-center p-4">
             <div className="w-20 h-20 bg-gray-800 rounded-full flex items-center justify-center border border-gray-700 mb-8">
                <Volume2 className="w-8 h-8 text-indigo-500" />
             </div>
             <h2 className="text-3xl font-bold mb-2">Voice Sales Coach</h2>
             <button 
               onClick={startMatchmaking}
               disabled={connectionStatus === 'offline'}
               className="bg-indigo-600 hover:bg-indigo-500 text-white px-8 py-3 rounded-xl font-bold transition-all disabled:opacity-50"
             >
               {connectionStatus === 'offline' ? 'Connecting...' : 'Start Session'}
             </button>
          </div>
        )}
 c687ba6 (important changes)

        {/* LEFT PANEL: METRICS & WARNINGS */}
        <div className="bg-gradient-to-br from-gray-900 to-indigo-950 relative flex flex-col items-center justify-center p-6 overflow-hidden">
           {isConnected && (
             <div className="w-full max-w-2xl space-y-8 animate-fade-in text-center">
                
                <div className="relative inline-block">
                  <div className="absolute inset-0 bg-indigo-500 blur-3xl opacity-20 animate-pulse" />
                  <Volume2 className={`w-24 h-24 mx-auto ${isMuted ? 'text-gray-600' : 'text-indigo-400'}`} />
                </div>
                
                <h2 className="text-2xl font-bold">Analysis Active</h2>
                
                {/* DYNAMIC WARNINGS (Sarcasm & Eye Tracking) */}
                <div className="h-10 flex items-center justify-center flex-col gap-2">
                  {sarcasmDetected && <div className="text-yellow-400 font-bold animate-bounce text-sm">⚠️ Sarcasm Detected</div>}
                  {isLookingAway && (
                    <div className="bg-red-500/20 border border-red-500 text-red-400 px-4 py-1.5 rounded-lg font-bold animate-pulse text-sm">
                      👀 Prospect is looking away! Re-engage them.
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                   <div className="bg-gray-800/40 p-4 rounded-xl border border-gray-700/50">
                      <div className="text-gray-400 text-xs mb-1">Confidence</div>
                      <div className="text-xl font-bold">{Math.round(voiceAnalytics.confidence_score)}%</div>
                   </div>
                   <div className="bg-gray-800/40 p-4 rounded-xl border border-gray-700/50">
                      <div className="text-gray-400 text-xs mb-1">Emotion</div>
                      <div className="text-xl font-bold capitalize">{dominantEmotion}</div>
                   </div>
                   <div className="bg-gray-800/40 p-4 rounded-xl border border-gray-700/50">
                      <div className="text-gray-400 text-xs mb-1">Rate</div>
                      <div className="text-xl font-bold">{Math.round(voiceMetrics.wpm)} wpm</div>
                   </div>
                   <div className="bg-gray-800/40 p-4 rounded-xl border border-gray-700/50">
                      <div className="text-gray-400 text-xs mb-1">Pauses</div>
                      <div className="text-xl font-bold">{voiceMetrics.pauses_count}</div>
                   </div>
                </div>

                <div className="bg-gray-800/30 p-6 rounded-xl border border-gray-700/50 text-left">
                   <MetricBar label="Pitch Stability" value={voiceAnalytics.pitch_stability} max={100} color="bg-blue-500" />
                   <MetricBar label="Volume Stability" value={voiceAnalytics.volume_stability} max={100} color="bg-green-500" />
                </div>
             </div>
           )}
           {isWaiting && (
             <div className="text-center animate-pulse">
               <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
               <p className="text-indigo-200">Initializing AI Models...</p>
             </div>
           )}
        </div>

 HEAD
        {/* Sidebar - FIXED HEIGHT AND OVERFLOW */}
        <div className="bg-gray-900/95 backdrop-blur-md border-l border-gray-800 flex flex-col h-full overflow-hidden">
          
          {/* Transcript Section - PROPERLY CONSTRAINED */}
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <div className="p-3 border-b border-gray-700 bg-gray-800/50 flex justify-between items-center flex-shrink-0">
              <span className="text-xs font-bold text-gray-400 uppercase flex items-center gap-2">
                <AlignLeft className="w-3 h-3" />
                Live Transcript
              </span>
              {isConnected && (
                <span className="text-xs bg-red-500/10 text-red-400 px-2 py-0.5 rounded-full border border-red-500/20 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" /> REC
                </span>
              )}
            </div>
            
            {/* Transcript Feed - THIS IS THE KEY FIX */}
            <div 
              ref={transcriptFeedRef}
              className="flex-1 overflow-y-auto p-4 space-y-3 text-sm min-h-0"
              style={{ 
                maxHeight: '100%',
                overflowY: 'auto',
                overflowX: 'hidden',
                wordBreak: 'break-word'
              }}
            >
              {transcript.length === 0 ? (
                <div className="text-center text-gray-600 italic text-xs mt-10">
                  <MicOff className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  {isConnected ? 'Start speaking...' : 'Waiting for session...'}
                </div>
              ) : (
                transcript.map((entry) => (
                  <div key={entry.id} className="animate-fade-in">
                    <div className="flex items-baseline gap-2 mb-1">
                      <span className={`font-bold text-xs ${
                        entry.speaker === 'You' ? 'text-indigo-400' : 
                        entry.speaker === 'System' ? 'text-yellow-400' : 
                        entry.speaker === 'AI Coach' ? 'text-green-400' :
                        entry.speaker === 'AI Alert' ? 'text-orange-400' :
                        'text-blue-400'
                      }`}>
                        {entry.speaker}
                      </span>
                      <span className="text-gray-600 text-xs">{entry.timestamp}</span>
                    </div>
                    <p className="text-gray-300 leading-relaxed break-words">{entry.text}</p>
                  </div>
                ))
              )}
            </div>

            {isConnected && (
              <div className="p-2 border-t border-gray-700 bg-gray-800/30 flex-shrink-0">
                <input 
                  type="text"
                  placeholder="Type message (or speak)..."
                  className="w-full bg-gray-900 text-gray-300 text-xs p-2 rounded border border-gray-700 focus:border-indigo-500 focus:outline-none transition"
                  onKeyPress={handleManualInput}
                />
              </div>
            )}
          </div>

          {/* AI Coach Section - FIXED HEIGHT */}
          <div className="h-48 border-t border-indigo-500/20 bg-indigo-900/5 flex flex-col flex-shrink-0 overflow-hidden">
            <div className="p-3 border-b border-indigo-500/20 flex justify-between items-center bg-indigo-900/20 flex-shrink-0">
              <span className="text-xs font-bold text-indigo-300 uppercase flex items-center gap-2">
                <Bot className="w-3 h-3" />
                AI Coach
              </span>
              {isConnected && (
                <button 
                  onClick={triggerAnalysis}
                  className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1 rounded transition shadow-lg shadow-indigo-600/20 flex items-center gap-1"
                >
                  <Activity className="w-3 h-3" />
                  Analyze
                </button>
              )}
            </div>
            
            <div className="flex-1 p-4 overflow-y-auto min-h-0">
              <div className="text-sm text-indigo-100/90 leading-relaxed break-words">
                {aiSuggestion || (
                  <div className="flex items-center gap-2 text-indigo-300/50 italic text-xs">
                    <div className="w-3 h-3 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
                    {isConnected ? 'Monitoring voice patterns...' : 'AI coach activates during session'}
                  </div>
        {/* RIGHT PANEL: TRANSCRIPT & COACH */}
        <div className="bg-gray-900/95 border-l border-gray-800 flex flex-col h-full overflow-hidden">
          
          <div className="p-3 border-b border-gray-700 bg-gray-800/50 flex-shrink-0 flex justify-between items-center">
             <span className="text-xs font-bold text-gray-400 uppercase flex items-center gap-2"><AlignLeft className="w-3 h-3" /> Live Transcript</span>
             {isConnected && <span className="text-xs text-red-400 animate-pulse">● REC</span>}
          </div>

          <div ref={transcriptFeedRef} className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0" style={{ scrollBehavior: 'smooth' }}>
             {transcript.length === 0 ? (
               <div className="text-center text-gray-600 text-xs mt-10 italic">Conversation will appear here...</div>
             ) : (
               transcript.map((t) => (
                 <div key={t.id} className="text-sm animate-fade-in">
                    <div className="flex gap-2 mb-1 items-baseline">
                       <span className={`font-bold text-xs ${t.speaker === 'You' ? 'text-indigo-400' : t.speaker === 'AI Coach' ? 'text-green-400' : 'text-blue-400'}`}>
                         {t.speaker}
                       </span>
                       <span className="text-gray-600 text-[10px]">{t.timestamp}</span>
                    </div>
                    <p className="text-gray-300 leading-relaxed">{t.text}</p>
                 </div>
               ))
             )}
          </div>

          {isConnected && (
            <div className="p-2 border-t border-gray-800 bg-gray-900 flex-shrink-0">
               <input 
                 className="w-full bg-gray-800 text-gray-200 text-xs p-2 rounded border border-gray-700 focus:border-indigo-500 outline-none"
                 placeholder="Type a message..."
                 onKeyPress={handleManualInput}
               />
            </div>
          )}

          {/* AI COACH WINDOW */}
          <div className="h-48 min-h-[12rem] border-t border-indigo-500/20 bg-indigo-900/10 flex flex-col flex-shrink-0">
             <div className="p-3 border-b border-indigo-500/10 bg-indigo-900/20 flex justify-between items-center">
                <span className="text-xs font-bold text-indigo-300 uppercase flex items-center gap-2"><Bot className="w-3 h-3" /> Gemini Coach</span>
                {isConnected && (
                  <button onClick={triggerAnalysis} className="text-[10px] bg-indigo-600 px-2 py-1 rounded text-white hover:bg-indigo-500 flex items-center gap-1 shadow-lg shadow-indigo-500/20">
                    <Activity className="w-3 h-3" /> Analyze
                  </button>
 c687ba6 (important changes)
                )}
             </div>
             <div className="flex-1 p-4 overflow-y-auto">
                <p className="text-sm text-indigo-100 leading-relaxed">
                   {aiSuggestion || <span className="text-indigo-400/50 italic">Click Analyze to get interview tips...</span>}
                </p>
             </div>
          </div>

        </div>
      </div>
      
      <style>{`
        .animate-fade-in { animation: fadeIn 0.3s ease-out; }
 HEAD
        
        /* Custom scrollbar for transcript */
        .overflow-y-auto::-webkit-scrollbar {
          width: 6px;
        }
        .overflow-y-auto::-webkit-scrollbar-track {
          background: rgba(31, 41, 55, 0.5);
          border-radius: 3px;
        }
        .overflow-y-auto::-webkit-scrollbar-thumb {
          background: rgba(75, 85, 99, 0.8);
          border-radius: 3px;
        }
        .overflow-y-auto::-webkit-scrollbar-thumb:hover {
          background: rgba(107, 114, 128, 1);

        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
 c687ba6 (important changes)
      `}</style>
    </div>
  );
};

export default InsightEngineApp;