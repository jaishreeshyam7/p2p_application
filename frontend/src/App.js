import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import io from 'socket.io-client';
import { Video, Mic, MicOff, PhoneOff, Phone, Activity, TrendingUp, Bot, AlignLeft, Zap, AlertTriangle, MessageSquare } from 'lucide-react';

const InsightEngineApp = () => {
  // State Management
  const [isInLobby, setIsInLobby] = useState(true);
  const [isWaiting, setIsWaiting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('offline');
  const [audioMode, setAudioMode] = useState('pipeline'); // 'pipeline' or 'simulation'
  const [transcript, setTranscript] = useState([]);
  const [aiSuggestion, setAiSuggestion] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  
  // Voice Analytics from Backend
  const [analytics, setAnalytics] = useState({
    dominant_emotion: 'Neutral',
    emotions: {
      'Happiness/Joy': 0,
      'Trust': 60,
      'Fear/FOMO': 0,
      'Surprise': 0,
      'Anger': 0
    },
    confidence: 75,
    is_sarcastic: false
  });
  
  const [stats, setStats] = useState({
    engagement: 60,
    stress: 'LOW',
    attention: 'HIGH'
  });
  
  // Refs
  const localAudioRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const socketRef = useRef(null);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);

  // Socket.IO Connection to Flask Backend
  useEffect(() => {
    // Detect backend URL (works in dev and production)
    const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 
                        (window.location.hostname === 'localhost' 
                          ? 'http://localhost:5000' 
                          : window.location.origin.replace('3000', '5000'));
    
    console.log('🔗 Connecting to backend:', BACKEND_URL);
    
    socketRef.current = io(BACKEND_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 10,
      timeout: 10000
    });

    // Connection Events
    socketRef.current.on('connect', () => {
      console.log('✅ Connected to backend:', socketRef.current.id);
      setConnectionStatus('online');
    });

    socketRef.current.on('disconnect', () => {
      console.log('❌ Disconnected from backend');
      setConnectionStatus('offline');
    });

    socketRef.current.on('connect_error', (error) => {
      console.error('Connection error:', error);
      setConnectionStatus('error');
    });

    socketRef.current.on('connection_status', (data) => {
      console.log('📊 Backend status:', data);
      setAudioMode(data.audio_pipeline_available ? 'pipeline' : 'simulation');
      addTranscript('System', `Connected in ${data.mode} mode`);
    });

    // Voice Analysis Updates
    socketRef.current.on('voice_analysis', (data) => {
      console.log('📊 Voice analysis update:', data);
      setAnalytics(prev => ({
        ...prev,
        emotions: data.emotions || prev.emotions,
        dominant_emotion: data.dominant_emotion || prev.dominant_emotion,
        confidence: data.confidence || prev.confidence,
        is_sarcastic: data.is_sarcastic || false
      }));
      
      // Update engagement
      const engagement = calculateEngagement(data.emotions);
      setStats(prev => ({
        ...prev,
        engagement,
        stress: data.confidence < 50 ? 'HIGH' : data.confidence < 75 ? 'MEDIUM' : 'LOW',
        attention: data.dominant_emotion === 'Trust' || data.dominant_emotion === 'Happiness/Joy' ? 'HIGH' : 'MEDIUM'
      }));
    });

    // Real-time Transcription
    socketRef.current.on('transcription', (data) => {
      console.log('📝 Transcription:', data);
      addTranscript(data.speaker || 'Speaker', data.text);
    });

    // Objection Detection
    socketRef.current.on('objection_detected', (data) => {
      console.log('🚨 Objection detected:', data);
      addTranscript('System', `⚠️ ${data.message}`);
      if (data.suggestion) {
        setAiSuggestion(data.suggestion);
      }
    });

    // Sarcasm Detection
    socketRef.current.on('sarcasm_detected', (data) => {
      console.log('😏 Sarcasm detected:', data);
      addTranscript('System', `😏 ${data.message}`);
    });

    // Match Found Event
    socketRef.current.on('match-found', handleMatchFound);
    
    // Peer Disconnected
    socketRef.current.on('peer-disconnected', handlePeerDisconnected);
    
    // AI Response
    socketRef.current.on('ai-response', handleAiResponse);

    // Error handling
    socketRef.current.on('error', (data) => {
      console.error('Backend error:', data);
      addTranscript('System', `❌ Error: ${data.message}`);
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
      stopMediaStreams();
    };
  }, []);

  // Calculate Engagement Score from Emotions
  const calculateEngagement = (emotions) => {
    if (!emotions) return 60;
    const positive = (emotions['Happiness/Joy'] || 0) + (emotions['Trust'] || 0) + (emotions['Surprise'] || 0) * 0.5;
    const negative = (emotions['Anger'] || 0) + (emotions['Fear/FOMO'] || 0);
    return Math.max(0, Math.min(100, Math.round(positive - negative * 0.5)));
  };

  // Start Matchmaking
  const startMatchmaking = async () => {
    setIsInLobby(false);
    setIsWaiting(true);

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000
        },
        video: false // Voice-only mode
      });
      
      localAudioRef.current = stream;

      setConnectionStatus('connecting');
      
      // Notify backend
      socketRef.current?.emit('identify', { 
        type: 'voice_user', 
        timestamp: Date.now() 
      });
      
      // Auto-match after delay
      setTimeout(() => {
        handleMatchFound({ roomId: 'room-voice-' + Date.now() });
      }, 2000);

    } catch (err) {
      console.error('Microphone access error:', err);
      alert('Microphone access required. Please check permissions.');
      stopSession();
    }
  };

  // Handle Match Found
  const handleMatchFound = (data) => {
    console.log('🎯 Match found:', data);
    setIsWaiting(false);
    setIsConnected(true);
    setConnectionStatus('connected');

    // Initialize speech recognition
    initSpeechRecognition();
    
    // Start audio streaming (if audio pipeline mode)
    if (audioMode === 'pipeline') {
      startAudioStreaming();
    }
    
    // Notify backend
    socketRef.current?.emit('session-started', { roomId: data.roomId });
  };

  // Start Audio Streaming to Backend
  const startAudioStreaming = () => {
    if (!localAudioRef.current) return;

    try {
      // Create audio context for processing
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioContextRef.current.createMediaStreamSource(localAudioRef.current);
      
      // Create media recorder
      mediaRecorderRef.current = new MediaRecorder(localAudioRef.current, {
        mimeType: 'audio/webm;codecs=opus',
        audioBitsPerSecond: 16000
      });

      // Send audio chunks to backend
      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0 && socketRef.current) {
          // Convert blob to base64 and send
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64Audio = reader.result.split(',')[1];
            socketRef.current.emit('audio_data', { audio: base64Audio });
          };
          reader.readAsDataURL(event.data);
        }
      };

      // Start recording in chunks (every 2 seconds)
      mediaRecorderRef.current.start(2000);
      console.log('🎤 Audio streaming started');
      
    } catch (err) {
      console.error('Failed to start audio streaming:', err);
      addTranscript('System', '⚠️ Audio streaming failed, using text-only mode');
    }
  };

  // Handle Peer Disconnected
  const handlePeerDisconnected = () => {
    console.log('👋 Peer disconnected');
    addTranscript('System', 'Partner has left the session');
    setTimeout(() => stopSession(), 2000);
  };

  // Handle AI Response
  const handleAiResponse = (data) => {
    console.log('🤖 AI Response:', data);
    setAiSuggestion(data.suggestion || data.message);
  };

  // Stop Session
  const stopSession = () => {
    setIsConnected(false);
    setIsWaiting(false);
    setIsInLobby(true);
    setConnectionStatus('online');
    setTranscript([]);
    setAiSuggestion('');
    setAnalytics({
      dominant_emotion: 'Neutral',
      emotions: {
        'Happiness/Joy': 0,
        'Trust': 60,
        'Fear/FOMO': 0,
        'Surprise': 0,
        'Anger': 0
      },
      confidence: 75,
      is_sarcastic: false
    });

    stopMediaStreams();
    stopSpeechRecognition();

    socketRef.current?.emit('leave-room');
  };

  // Stop Media Streams
  const stopMediaStreams = () => {
    if (localAudioRef.current) {
      localAudioRef.current.getTracks().forEach(track => track.stop());
      localAudioRef.current = null;
    }
    
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    }
    
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
  };

  // Toggle Mute
  const toggleMute = () => {
    if (localAudioRef.current) {
      localAudioRef.current.getAudioTracks().forEach(track => {
        track.enabled = !track.enabled;
      });
      setIsMuted(!isMuted);
    }
  };

  // Initialize Speech Recognition
  const initSpeechRecognition = () => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      console.log('Speech recognition not supported');
      addTranscript('System', 'Speech recognition not available - using manual input');
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognitionRef.current = new SpeechRecognition();
    recognitionRef.current.continuous = true;
    recognitionRef.current.interimResults = true;
    recognitionRef.current.lang = 'en-US';

    recognitionRef.current.onresult = (event) => {
      const last = event.results.length - 1;
      const text = event.results[last][0].transcript;
      
      if (event.results[last].isFinal) {
        addTranscript('You', text);
        
        // Send to backend for analysis
        socketRef.current?.emit('text_input', { 
          speaker: 'User', 
          text,
          timestamp: Date.now()
        });
      }
    };

    recognitionRef.current.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      if (event.error === 'no-speech') {
        // Auto-restart on silence
        setTimeout(() => {
          if (isConnected && recognitionRef.current) {
            try {
              recognitionRef.current.start();
            } catch (e) {
              console.log('Recognition already started');
            }
          }
        }, 1000);
      }
    };

    recognitionRef.current.onend = () => {
      if (isConnected) {
        setTimeout(() => {
          if (recognitionRef.current) {
            try {
              recognitionRef.current.start();
            } catch (e) {
              console.log('Recognition already started');
            }
          }
        }, 100);
      }
    };

    try {
      recognitionRef.current.start();
      console.log('🎤 Speech recognition started');
    } catch (err) {
      console.error('Failed to start speech recognition:', err);
    }
  };

  // Stop Speech Recognition
  const stopSpeechRecognition = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
  };

  // Add Transcript Entry
  const addTranscript = (speaker, text) => {
    setTranscript(prev => [...prev, {
      id: Date.now() + Math.random(),
      speaker,
      text,
      timestamp: new Date().toLocaleTimeString()
    }]);
  };

  // Manual Input Handler
  const handleManualInput = (e) => {
    if (e.key === 'Enter' && e.target.value.trim()) {
      const text = e.target.value;
      addTranscript('You', text);
      socketRef.current?.emit('text_input', { 
        speaker: 'User', 
        text,
        timestamp: Date.now()
      });
      e.target.value = '';
    }
  };

  // Trigger AI Analysis
  const triggerAnalysis = () => {
    const recentTranscript = transcript.slice(-5).map(t => `${t.speaker}: ${t.text}`).join('\n');
    socketRef.current?.emit('analyze-context', { 
      transcript: recentTranscript,
      emotions: analytics.emotions,
      confidence: analytics.confidence
    });
    setAiSuggestion('🔍 Analyzing conversation context and emotional state...');
  };

  // Auto-scroll transcript
  useEffect(() => {
    const feed = document.getElementById('transcript-feed');
    if (feed) {
      feed.scrollTop = feed.scrollHeight;
    }
  }, [transcript]);

  // Connection Status Component
  const StatusDot = () => {
    const statusConfig = {
      offline: { color: 'bg-red-500', text: 'Offline' },
      connecting: { color: 'bg-yellow-500', text: 'Connecting' },
      online: { color: 'bg-blue-500', text: 'Online' },
      connected: { color: 'bg-green-500', text: 'Live' },
      error: { color: 'bg-red-500', text: 'Error' }
    };
    
    const config = statusConfig[connectionStatus] || statusConfig.offline;
    
    return (
      <div className="flex items-center gap-2 text-xs font-mono text-gray-400 bg-gray-800/50 px-3 py-1 rounded-full">
        <span className={`w-2 h-2 rounded-full ${config.color} ${connectionStatus === 'connecting' ? 'animate-pulse' : ''}`}></span>
        <span>{config.text}</span>
        <span className="text-gray-600 ml-1">| {audioMode === 'pipeline' ? '🎤 AI' : '🎲 Sim'}</span>
      </div>
    );
  };

  // Emotion Bar Chart Component
  const EmotionBar = ({ label, value, color }) => (
    <div className="mb-2">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-400">{label}</span>
        <span className="text-gray-300 font-mono">{value}%</span>
      </div>
      <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div 
          className={`h-full ${color} rounded-full transition-all duration-500`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );

  return (
    <div className="bg-gray-900 text-gray-100 h-screen overflow-hidden flex flex-col">
      {/* Navbar */}
      <nav className="h-16 bg-gray-900 border-b border-gray-800 flex justify-between items-center px-4 md:px-6 z-50">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-indigo-600 rounded flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <Mic className="w-4 h-4 text-white" />
          </div>
          <h1 className="font-bold text-lg tracking-wide hidden md:block">
            InsightEngine <span className="text-xs font-normal text-gray-500">Voice Coach</span>
          </h1>
          <h1 className="font-bold text-lg tracking-wide md:hidden">
            IE <span className="text-xs font-normal text-gray-500">Voice</span>
          </h1>
        </div>
        
        <div className="flex items-center gap-4">
          <StatusDot />
          {isConnected && (
            <>
              <button 
                onClick={toggleMute}
                className={`${isMuted ? 'bg-red-600/20 text-red-400 border-red-600/50' : 'bg-gray-700 text-gray-300 border-gray-600'} hover:bg-opacity-80 px-3 py-1.5 rounded text-sm transition border flex items-center gap-2`}
              >
                {isMuted ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                <span className="hidden sm:inline">{isMuted ? 'Unmute' : 'Mute'}</span>
              </button>
              <button 
                onClick={stopSession}
                className="bg-red-600/20 text-red-400 hover:bg-red-600 hover:text-white px-4 py-1.5 rounded text-sm transition border border-red-600/50 flex items-center gap-2"
              >
                <PhoneOff className="w-4 h-4" />
                <span className="hidden sm:inline">End</span>
              </button>
            </>
          )}
        </div>
      </nav>

      {/* Lobby Screen */}
      {isInLobby && (
        <div className="absolute inset-0 top-16 z-50 bg-gray-900 flex flex-col items-center justify-center p-4">
          <div className="max-w-md w-full text-center space-y-8 bg-gray-800/30 p-8 rounded-2xl border border-gray-700/50 backdrop-blur-sm">
            <div className="relative inline-block">
              <div className="absolute inset-0 bg-indigo-600 blur-2xl opacity-20 rounded-full animate-pulse"></div>
              <div className="w-20 h-20 bg-gray-800 rounded-full flex items-center justify-center border border-gray-700 relative z-10 mx-auto">
                <Mic className="w-8 h-8 text-indigo-500" />
              </div>
            </div>
            
            <div className="space-y-2">
              <h2 className="text-3xl font-bold text-white">Voice Sales Trainer</h2>
              <p className="text-gray-400 text-sm">
                AI-powered voice analysis with real-time emotion detection, objection handling, and intelligent coaching.
              </p>
            </div>
            
            <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700 text-left space-y-3">
              <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Features Active</h3>
              
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex items-center gap-2 text-gray-300">
                  <Mic className="w-3 h-3 text-indigo-400" />
                  <span>Voice Analysis</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <Activity className="w-3 h-3 text-indigo-400" />
                  <span>Emotion Detection</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <AlertTriangle className="w-3 h-3 text-indigo-400" />
                  <span>Objection Detection</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <MessageSquare className="w-3 h-3 text-indigo-400" />
                  <span>Live Transcript</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <Zap className="w-3 h-3 text-indigo-400" />
                  <span>Confidence Score</span>
                </div>
                <div className="flex items-center gap-2 text-gray-300">
                  <Bot className="w-3 h-3 text-indigo-400" />
                  <span>AI Coaching</span>
                </div>
              </div>
              
              <div className="border-t border-gray-700 pt-3 mt-3">
                <div className="flex justify-between items-center">
                  <span className="text-gray-400 text-xs">Backend Status</span>
                  <span className={`text-xs px-2 py-0.5 rounded border ${
                    connectionStatus === 'online' || connectionStatus === 'connected'
                      ? 'text-green-400 bg-green-400/10 border-green-400/20'
                      : 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'
                  }`}>
                    {connectionStatus === 'online' || connectionStatus === 'connected' ? '✓ Ready' : 'Connecting...'}
                  </span>
                </div>
              </div>
            </div>

            <button 
              onClick={startMatchmaking}
              disabled={connectionStatus === 'offline'}
              className="group w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed text-white py-3 rounded-xl font-bold text-lg shadow-lg shadow-indigo-500/30 transition-all transform hover:scale-[1.02] active:scale-[0.98]"
            >
              {connectionStatus === 'offline' ? 'Connecting to Server...' : 'Start Voice Session →'}
            </button>
          </div>
        </div>
      )}

      {/* Main Content Grid */}
      <div className="flex-1 grid md:grid-cols-[1fr_400px] overflow-hidden">
        
        {/* Voice Visualization Area */}
        <div className="relative bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 flex items-center justify-center overflow-hidden">
          
          {/* Audio Visualizer Placeholder */}
          {isConnected && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center space-y-8">
                <div className="relative">
                  <div className="absolute inset-0 bg-indigo-500 blur-3xl opacity-30 animate-pulse"></div>
                  <div className="w-40 h-40 bg-gradient-to-br from-indigo-600 to-purple-600 rounded-full flex items-center justify-center relative z-10 shadow-2xl shadow-indigo-500/50 animate-pulse">
                    {isMuted ? (
                      <MicOff className="w-16 h-16 text-white" />
                    ) : (
                      <Mic className="w-16 h-16 text-white" />
                    )}
                  </div>
                </div>
                
                <div className="space-y-3">
                  <h2 className="text-2xl font-bold text-white">Voice Analysis Active</h2>
                  <div className="flex items-center justify-center gap-2 text-indigo-300">
                    <div className="w-2 h-2 bg-indigo-400 rounded-full animate-pulse"></div>
                    <span className="text-sm">Listening and analyzing...</span>
                  </div>
                </div>

                {/* Live Analytics Cards */}
                <div className="grid grid-cols-3 gap-4 max-w-2xl mx-auto mt-8">
                  <div className="bg-gray-800/50 backdrop-blur-md p-4 rounded-xl border border-gray-700/50">
                    <div className="text-xs text-gray-400 mb-2">Confidence</div>
                    <div className="text-2xl font-bold text-white">{analytics.confidence}%</div>
                    <div className="h-1 bg-gray-700 rounded-full mt-2 overflow-hidden">
                      <div className="h-full bg-indigo-500 rounded-full transition-all" style={{ width: `${analytics.confidence}%` }}></div>
                    </div>
                  </div>
                  
                  <div className="bg-gray-800/50 backdrop-blur-md p-4 rounded-xl border border-gray-700/50">
                    <div className="text-xs text-gray-400 mb-2">Emotion</div>
                    <div className="text-xl font-bold text-white truncate">{analytics.dominant_emotion}</div>
                    {analytics.is_sarcastic && (
                      <div className="text-xs text-yellow-400 mt-1">😏 Sarcasm detected</div>
                    )}
                  </div>
                  
                  <div className="bg-gray-800/50 backdrop-blur-md p-4 rounded-xl border border-gray-700/50">
                    <div className="text-xs text-gray-400 mb-2">Engagement</div>
                    <div className="text-2xl font-bold text-white">{stats.engagement}%</div>
                    <div className="h-1 bg-gray-700 rounded-full mt-2 overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all" style={{ width: `${stats.engagement}%` }}></div>
                    </div>
                  </div>
                </div>

                {/* Emotion Breakdown */}
                <div className="max-w-md mx-auto bg-gray-800/30 backdrop-blur-md p-5 rounded-xl border border-gray-700/50">
                  <h3 className="text-xs text-gray-400 font-bold mb-3 uppercase tracking-wider">Emotional State</h3>
                  <EmotionBar label="Joy" value={analytics.emotions['Happiness/Joy'] || 0} color="bg-yellow-500" />
                  <EmotionBar label="Trust" value={analytics.emotions['Trust'] || 0} color="bg-blue-500" />
                  <EmotionBar label="Surprise" value={analytics.emotions['Surprise'] || 0} color="bg-purple-500" />
                  <EmotionBar label="Fear/FOMO" value={analytics.emotions['Fear/FOMO'] || 0} color="bg-orange-500" />
                  <EmotionBar label="Anger" value={analytics.emotions['Anger'] || 0} color="bg-red-500" />
                </div>
              </div>
            </div>
          )}

          {/* Waiting State */}
          {isWaiting && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-900/95 z-20">
              <div className="w-8 h-8 border-3 border-gray-300 border-t-indigo-500 rounded-full animate-spin mb-4" />
              <p className="text-indigo-200 animate-pulse font-medium mb-2">
                Initializing voice analysis engine...
              </p>
              <p className="text-gray-500 text-sm">
                Connecting to AI models
              </p>
              <button 
                onClick={stopSession}
                className="mt-8 text-xs text-gray-500 hover:text-gray-300 underline"
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="bg-gray-900/95 backdrop-blur-md border-l border-gray-800 flex flex-col">
          
          {/* Transcript Section */}
          <div className="flex-1 flex flex-col min-h-0">
            <div className="p-3 border-b border-gray-700 bg-gray-800/50 flex justify-between items-center">
              <span className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                <AlignLeft className="w-3 h-3" />
                Live Transcript
              </span>
              {isConnected && (
                <span className="text-xs bg-red-500/10 text-red-400 px-2 py-0.5 rounded-full border border-red-500/20 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" /> REC
                </span>
              )}
            </div>
            
            <div id="transcript-feed" className="flex-1 overflow-y-auto p-4 space-y-3 text-sm">
              {transcript.length === 0 ? (
                <div className="text-center text-gray-600 italic text-xs mt-10">
                  <MicOff className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  {isConnected ? 'Start speaking to begin transcript...' : 'Waiting for session to start...'}
                </div>
              ) : (
                transcript.map((entry) => (
                  <div key={entry.id} className="animate-fade-in">
                    <div className="flex items-baseline gap-2 mb-1">
                      <span className={`font-bold text-xs ${
                        entry.speaker === 'You' ? 'text-indigo-400' : 
                        entry.speaker === 'System' ? 'text-yellow-400' : 'text-green-400'
                      }`}>
                        {entry.speaker}
                      </span>
                      <span className="text-gray-600 text-xs">{entry.timestamp}</span>
                    </div>
                    <p className="text-gray-300 leading-relaxed">{entry.text}</p>
                  </div>
                ))
              )}
            </div>

            {isConnected && (
              <div className="p-2 border-t border-gray-700 bg-gray-800/30">
                <input 
                  type="text"
                  placeholder="Type to send text (or speak)..."
                  className="w-full bg-gray-900 text-gray-300 text-xs p-2 rounded border border-gray-700 focus:border-indigo-500 focus:outline-none transition"
                  onKeyPress={handleManualInput}
                />
              </div>
            )}
          </div>

          {/* AI Coach Section */}
          <div className="h-1/3 border-t border-indigo-500/20 bg-indigo-900/5 flex flex-col min-h-[150px]">
            <div className="p-3 border-b border-indigo-500/20 flex justify-between items-center bg-indigo-900/20">
              <span className="text-xs font-bold text-indigo-300 uppercase flex items-center gap-2">
                <Bot className="w-3 h-3" />
                AI Voice Coach
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
            
            <div className="flex-1 p-4 overflow-y-auto">
              <div className="text-sm text-indigo-100/90 leading-relaxed">
                {aiSuggestion || (
                  <div className="flex items-center gap-2 text-indigo-300/50 italic text-xs">
                    <div className="w-3 h-3 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
                    {isConnected ? 'Monitoring voice patterns and emotions...' : 'AI coach will activate during session'}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <style>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(5px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-fade-in {
          animation: fadeIn 0.3s ease-out;
        }
      `}</style>
    </div>
  );
};

export default InsightEngineApp;