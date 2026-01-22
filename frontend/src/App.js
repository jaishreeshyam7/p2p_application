import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import io from 'socket.io-client';
import { Mic, MicOff, PhoneOff, Activity, Bot, AlignLeft, Zap, AlertTriangle, MessageSquare, TrendingUp, Volume2 } from 'lucide-react';

const InsightEngineApp = () => {
  // State Management
  const [isInLobby, setIsInLobby] = useState(true);
  const [isWaiting, setIsWaiting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('offline');
  const [voiceModules, setVoiceModules] = useState({
    transcribe: false,
    text_emotion: false,
    sarcasm: false,
    objections: false,
    diarization: false,
    confidence: false
  });
  const [transcript, setTranscript] = useState([]);
  const [aiSuggestion, setAiSuggestion] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  
  // Voice-specific Analytics
  const [voiceAnalytics, setVoiceAnalytics] = useState({
    confidence_score: 75,
    pitch_stability: 0,
    volume_stability: 0,
    avg_pitch_hz: 0,
    jitter: 0,
    shimmer: 0
  });
  
  const [voiceMetrics, setVoiceMetrics] = useState({
    wpm: 0,
    total_words: 0,
    duration: 0,
    pauses_count: 0
  });
  
  const [emotions, setEmotions] = useState({
    anger: 0,
    joy: 0,
    sadness: 0,
    fear: 0,
    surprise: 0,
    neutral: 60
  });
  
  const [dominantEmotion, setDominantEmotion] = useState('neutral');
  const [sarcasmDetected, setSarcasmDetected] = useState(false);
  const [lastObjection, setLastObjection] = useState(null);
  
  // Refs
  const localAudioRef = useRef(null);
  const socketRef = useRef(null);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);

  // Get Backend URL
  const getBackendURL = () => {
    if (process.env.REACT_APP_BACKEND_URL) {
      return process.env.REACT_APP_BACKEND_URL;
    }
    const hostname = window.location.hostname;
    if (hostname.includes('github.dev') || hostname.includes('preview.app.github.dev')) {
      return window.location.origin.replace('3000', '5000');
    }
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:5000';
    }
    return window.location.origin;
  };

  // Socket.IO Connection
  useEffect(() => {
    const BACKEND_URL = getBackendURL();
    console.log('🔗 Connecting to voice-only backend:', BACKEND_URL);
    
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
      reconnectAttempts.current = 0;
    });

    socketRef.current.on('disconnect', () => {
      console.log('❌ Disconnected from backend');
      setConnectionStatus('offline');
      addTranscript('System', '⚠️ Disconnected. Reconnecting...');
    });

    socketRef.current.on('connect_error', (error) => {
      console.error('❌ Connection error:', error);
      setConnectionStatus('error');
      
      reconnectAttempts.current += 1;
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
      
      if (reconnectAttempts.current <= 5) {
        addTranscript('System', `Retrying in ${delay/1000}s... (${reconnectAttempts.current}/5)`);
      }
    });

    socketRef.current.on('connection_status', (data) => {
      console.log('📊 Backend status:', data);
      if (data.modules) {
        setVoiceModules(data.modules);
      }
      addTranscript('System', `✅ Connected in ${data.mode || 'voice'} mode`);
    });

    // Voice-specific events
    socketRef.current.on('transcription-result', (data) => {
      console.log('📝 Transcription:', data);
      addTranscript(data.speaker || 'Detected', data.text);
    });

    socketRef.current.on('confidence-update', (data) => {
      console.log('💪 Confidence update:', data);
      setVoiceAnalytics({
        confidence_score: data.confidence_score || 75,
        pitch_stability: data.pitch_stability || 0,
        volume_stability: data.volume_stability || 0,
        avg_pitch_hz: data.avg_pitch_hz || 0,
        jitter: data.jitter || 0,
        shimmer: data.shimmer || 0
      });
    });

    socketRef.current.on('voice-metrics', (data) => {
      console.log('📊 Voice metrics:', data);
      setVoiceMetrics({
        wpm: data.wpm || 0,
        total_words: data.total_words || 0,
        duration: data.duration || 0,
        pauses_count: data.pauses_count || 0
      });
    });

    socketRef.current.on('emotion-update', (data) => {
      console.log('😊 Emotion update:', data);
      if (data.emotions) {
        setEmotions(data.emotions);
      }
      if (data.dominant) {
        setDominantEmotion(data.dominant);
      }
    });

    socketRef.current.on('sarcasm-detected', (data) => {
      console.log('😏 Sarcasm detected:', data);
      setSarcasmDetected(true);
      addTranscript('AI Alert', `😏 Sarcasm detected (${data.score}%): "${data.text}"`);
      setTimeout(() => setSarcasmDetected(false), 5000);
    });

    socketRef.current.on('objection-detected', (data) => {
      console.log('🚨 Objection detected:', data);
      setLastObjection(data);
      addTranscript('AI Coach', data.suggestion);
      setAiSuggestion(data.suggestion);
    });

    socketRef.current.on('match-found', handleMatchFound);
    socketRef.current.on('session-confirmed', (data) => {
      console.log('✅ Session confirmed:', data);
      addTranscript('System', '✅ Voice session active');
    });
    socketRef.current.on('peer-disconnected', handlePeerDisconnected);
    socketRef.current.on('session-ended', () => {
      addTranscript('System', 'Session ended');
    });
    
    socketRef.current.on('ai-response', handleAiResponse);
    socketRef.current.on('error', (data) => {
      console.error('❌ Backend error:', data);
      addTranscript('System', `❌ ${data.message || 'Error occurred'}`);
    });

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
      stopMediaStreams();
    };
  }, []);

  // Start Session
  const startMatchmaking = async () => {
    setIsInLobby(false);
    setIsWaiting(true);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000
        },
        video: false
      });
      
      localAudioRef.current = stream;
      setConnectionStatus('connecting');
      
      socketRef.current?.emit('identify', { 
        type: 'user', 
        timestamp: Date.now() 
      });
      
      setTimeout(() => {
        handleMatchFound({ roomId: 'room-' + Date.now() });
      }, 2000);

    } catch (err) {
      console.error('Microphone error:', err);
      alert('Microphone access required. Please allow access and try again.');
      stopSession();
    }
  };

  // Handle Match Found
  const handleMatchFound = (data) => {
    console.log('🎯 Match found:', data);
    setIsWaiting(false);
    setIsConnected(true);
    setConnectionStatus('connected');

    initSpeechRecognition();
    startAudioStreaming();
    
    socketRef.current?.emit('session-started', { roomId: data.roomId });
    addTranscript('System', `🎯 Session: ${data.roomId}`);
  };

  // Audio Streaming
  const startAudioStreaming = () => {
    if (!localAudioRef.current) return;

    try {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      
      mediaRecorderRef.current = new MediaRecorder(localAudioRef.current, {
        mimeType: 'audio/webm;codecs=opus',
        audioBitsPerSecond: 16000
      });

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0 && socketRef.current && !isMuted) {
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64Audio = reader.result.split(',')[1];
            socketRef.current.emit('audio-data', { audio: base64Audio });
          };
          reader.readAsDataURL(event.data);
        }
      };

      mediaRecorderRef.current.start(3000); // Send chunks every 3 seconds
      console.log('🎤 Audio streaming started');
      
    } catch (err) {
      console.error('Audio streaming error:', err);
      addTranscript('System', '⚠️ Audio streaming unavailable');
    }
  };

  const handlePeerDisconnected = () => {
    addTranscript('System', '👋 Partner left');
    setTimeout(() => stopSession(), 2000);
  };

  const handleAiResponse = (data) => {
    console.log('🤖 AI Response:', data);
    setAiSuggestion(data.suggestion || data.message || '');
  };

  // Stop Session
  const stopSession = () => {
    setIsConnected(false);
    setIsWaiting(false);
    setIsInLobby(true);
    setConnectionStatus('online');
    setTranscript([]);
    setAiSuggestion('');
    setSarcasmDetected(false);
    setLastObjection(null);

    stopMediaStreams();
    stopSpeechRecognition();
    socketRef.current?.emit('leave-room');
  };

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

  const toggleMute = () => {
    if (localAudioRef.current) {
      localAudioRef.current.getAudioTracks().forEach(track => {
        track.enabled = !track.enabled;
      });
      setIsMuted(!isMuted);
    }
  };

  // Speech Recognition
  const initSpeechRecognition = () => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      addTranscript('System', '⚠️ Speech recognition unavailable');
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
        socketRef.current?.emit('transcript', { 
          speaker: 'user', 
          text,
          timestamp: Date.now()
        });
      }
    };

    recognitionRef.current.onerror = (event) => {
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        console.error('Speech recognition error:', event.error);
      }
    };

    recognitionRef.current.onend = () => {
      if (isConnected && recognitionRef.current) {
        try {
          recognitionRef.current.start();
        } catch (e) {}
      }
    };

    try {
      recognitionRef.current.start();
      console.log('🎤 Speech recognition started');
    } catch (err) {
      console.error('Failed to start speech recognition:', err);
    }
  };

  const stopSpeechRecognition = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
  };

  const addTranscript = (speaker, text) => {
    setTranscript(prev => [...prev, {
      id: Date.now() + Math.random(),
      speaker,
      text,
      timestamp: new Date().toLocaleTimeString()
    }]);
  };

  const handleManualInput = (e) => {
    if (e.key === 'Enter' && e.target.value.trim()) {
      const text = e.target.value;
      addTranscript('You', text);
      socketRef.current?.emit('transcript', { 
        speaker: 'user', 
        text,
        timestamp: Date.now()
      });
      e.target.value = '';
    }
  };

  const triggerAnalysis = () => {
    const recentTranscript = transcript.slice(-5).map(t => `${t.speaker}: ${t.text}`).join('\n');
    socketRef.current?.emit('analyze-context', { 
      transcript: recentTranscript
    });
    setAiSuggestion('🔍 Analyzing...');
  };

  useEffect(() => {
    const feed = document.getElementById('transcript-feed');
    if (feed) {
      feed.scrollTop = feed.scrollHeight;
    }
  }, [transcript]);

  // Status Component
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
      </div>
    );
  };

  // Metric Bar
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

      {/* Main Content */}
      <div className="flex-1 grid md:grid-cols-[1fr_400px] overflow-hidden">
        
        {/* Voice Visualization Area */}
        <div className="relative bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 flex items-center justify-center overflow-hidden">
          
          {isConnected && (
            <div className="text-center space-y-8 w-full max-w-3xl px-8">
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

              {/* Voice Analytics Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-gray-800/50 backdrop-blur-md p-4 rounded-xl border border-gray-700/50">
                  <div className="text-xs text-gray-400 mb-2">Confidence</div>
                  <div className="text-2xl font-bold text-white">{Math.round(voiceAnalytics.confidence_score)}%</div>
                  <div className="h-1 bg-gray-700 rounded-full mt-2 overflow-hidden">
                    <div className="h-full bg-indigo-500 rounded-full transition-all" style={{ width: `${voiceAnalytics.confidence_score}%` }}></div>
                  </div>
                </div>
                
                <div className="bg-gray-800/50 backdrop-blur-md p-4 rounded-xl border border-gray-700/50">
                  <div className="text-xs text-gray-400 mb-2">Speaking Rate</div>
                  <div className="text-2xl font-bold text-white">{voiceMetrics.wpm}</div>
                  <div className="text-xs text-gray-500 mt-1">words/min</div>
                </div>
                
                <div className="bg-gray-800/50 backdrop-blur-md p-4 rounded-xl border border-gray-700/50">
                  <div className="text-xs text-gray-400 mb-2">Emotion</div>
                  <div className="text-lg font-bold text-white truncate capitalize">{dominantEmotion}</div>
                </div>
                
                <div className="bg-gray-800/50 backdrop-blur-md p-4 rounded-xl border border-gray-700/50">
                  <div className="text-xs text-gray-400 mb-2">Pauses</div>
                  <div className="text-2xl font-bold text-white">{voiceMetrics.pauses_count}</div>
                </div>
              </div>

              {/* Detailed Voice Metrics */}
              <div className="max-w-2xl mx-auto bg-gray-800/30 backdrop-blur-md p-5 rounded-xl border border-gray-700/50">
                <h3 className="text-xs text-gray-400 font-bold mb-3 uppercase">Voice Quality Metrics</h3>
                <MetricBar label="Pitch Stability" value={voiceAnalytics.pitch_stability} max={100} color="bg-blue-500" />
                <MetricBar label="Volume Stability" value={voiceAnalytics.volume_stability} max={100} color="bg-green-500" />
                <div className="grid grid-cols-2 gap-4 mt-3 text-xs">
                  <div>
                    <span className="text-gray-400">Avg Pitch:</span>
                    <span className="text-gray-300 ml-2">{Math.round(voiceAnalytics.avg_pitch_hz)} Hz</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Total Words:</span>
                    <span className="text-gray-300 ml-2">{voiceMetrics.total_words}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {isWaiting && (
            <div className="text-center">
              <div className="w-8 h-8 border-3 border-gray-300 border-t-indigo-500 rounded-full animate-spin mb-4 mx-auto" />
              <p className="text-indigo-200 animate-pulse font-medium mb-2">Initializing voice AI...</p>
              <p className="text-gray-500 text-sm">Loading analysis models</p>
              <button onClick={stopSession} className="mt-8 text-xs text-gray-500 hover:text-gray-300 underline">Cancel</button>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="bg-gray-900/95 backdrop-blur-md border-l border-gray-800 flex flex-col">
          
          {/* Transcript */}
          <div className="flex-1 flex flex-col min-h-0">
            <div className="p-3 border-b border-gray-700 bg-gray-800/50 flex justify-between items-center">
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
            
            <div id="transcript-feed" className="flex-1 overflow-y-auto p-4 space-y-3 text-sm">
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
                    <p className="text-gray-300 leading-relaxed">{entry.text}</p>
                  </div>
                ))
              )}
            </div>

            {isConnected && (
              <div className="p-2 border-t border-gray-700 bg-gray-800/30">
                <input 
                  type="text"
                  placeholder="Type message (or speak)..."
                  className="w-full bg-gray-900 text-gray-300 text-xs p-2 rounded border border-gray-700 focus:border-indigo-500 focus:outline-none transition"
                  onKeyPress={handleManualInput}
                />
              </div>
            )}
          </div>

          {/* AI Coach */}
          <div className="h-1/3 border-t border-indigo-500/20 bg-indigo-900/5 flex flex-col min-h-[150px]">
            <div className="p-3 border-b border-indigo-500/20 flex justify-between items-center bg-indigo-900/20">
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
            
            <div className="flex-1 p-4 overflow-y-auto">
              <div className="text-sm text-indigo-100/90 leading-relaxed">
                {aiSuggestion || (
                  <div className="flex items-center gap-2 text-indigo-300/50 italic text-xs">
                    <div className="w-3 h-3 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
                    {isConnected ? 'Monitoring voice patterns...' : 'AI coach activates during session'}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(5px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in { animation: fadeIn 0.3s ease-out; }
      `}</style>
    </div>
  );
};

export default InsightEngineApp;
