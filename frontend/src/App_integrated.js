import React, { useState, useRef, useEffect, useCallback } from 'react';
import './App.css';
import io from 'socket.io-client';
import { Video, Mic, MicOff, PhoneOff, Camera, Network, TrendingUp, Bot, AlignLeft, Phone, Activity, Eye, Heart } from 'lucide-react';

const InsightEngineApp = () => {
  // State Management
  const [isInLobby, setIsInLobby] = useState(true);
  const [isWaiting, setIsWaiting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('offline');
  const [currentRoomId, setCurrentRoomId] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const [aiSuggestion, setAiSuggestion] = useState('');
  
  // Backend Configuration
  const [backendConfig, setBackendConfig] = useState(null);
  
  // Real-time Analytics from Backend
  const [analytics, setAnalytics] = useState({
    hr: 0,
    dominant_emotion: 'Neutral',
    emotions: {
      'Happiness/Joy': 0,
      'Trust': 0,
      'Fear/FOMO': 0,
      'Surprise': 0,
      'Anger': 0
    },
    gaze_x: 50,
    gaze_y: 50
  });
  
  const [stats, setStats] = useState({
    engagement: 0,
    stress: 'LOW',
    attention: 'HIGH'
  });
  
  const [dashboardPosition, setDashboardPosition] = useState({ x: 24, y: 24 });
  
  // Refs
  const localVideoRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const localStreamRef = useRef(null);
  const socketRef = useRef(null);
  const recognitionRef = useRef(null);
  const isDraggingRef = useRef(false);
  const dragOffsetRef = useRef({ x: 0, y: 0 });
  const videoFrameIntervalRef = useRef(null);

  // Get Backend URL
  const getBackendUrl = () => {
    // For GitHub Codespaces or localhost
    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    const host = window.location.hostname;
    
    // Check if running on Codespaces
    if (host.includes('github.dev') || host.includes('githubpreview.dev')) {
      // Codespaces URL pattern
      return `${protocol}//${host.replace(/-(3000|3001)/, '-5000')}`;
    }
    
    // Localhost
    return `${protocol}//${host}:5000`;
  };

  // Fetch Backend Configuration
  const fetchBackendConfig = async () => {
    try {
      const backendUrl = getBackendUrl();
      const response = await fetch(`${backendUrl}/api/config`);
      const config = await response.json();
      setBackendConfig(config);
      console.log('📋 Backend config loaded:', config);
    } catch (error) {
      console.error('Failed to fetch backend config:', error);
    }
  };

  // Socket.IO Connection to Flask Backend
  useEffect(() => {
    const BACKEND_URL = getBackendUrl();
    
    console.log('🔗 Connecting to backend:', BACKEND_URL);
    
    // Initialize socket connection
    socketRef.current = io(BACKEND_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
      timeout: 10000
    });

    // Connection Events
    socketRef.current.on('connect', () => {
      console.log('✅ Connected to backend:', socketRef.current.id);
      setConnectionStatus('online');
      fetchBackendConfig();
    });

    socketRef.current.on('disconnect', () => {
      console.log('❌ Disconnected from backend');
      setConnectionStatus('offline');
    });

    socketRef.current.on('connect_error', (error) => {
      console.error('Connection error:', error);
      setConnectionStatus('error');
    });

    // Real-time Analytics Updates
    socketRef.current.on('server_update', (data) => {
      console.log('📊 Analytics update:', data);
      setAnalytics(data);
      
      // Update engagement based on emotions
      const engagement = calculateEngagement(data.emotions);
      setStats(prev => ({
        ...prev,
        engagement,
        stress: data.hr > 80 ? 'HIGH' : data.hr > 70 ? 'MEDIUM' : 'LOW',
        attention: data.dominant_emotion === 'Trust' || data.dominant_emotion === 'Happiness/Joy' ? 'HIGH' : 'MEDIUM'
      }));
    });

    // Match Found Event
    socketRef.current.on('match-found', handleMatchFound);
    
    // Joined Room
    socketRef.current.on('joined-room', (data) => {
      console.log('✅ Joined room:', data);
    });
    
    // Peer Disconnected
    socketRef.current.on('peer-disconnected', handlePeerDisconnected);
    
    // AI Response
    socketRef.current.on('ai-response', handleAiResponse);
    
    // New Transcript from Peer
    socketRef.current.on('new-transcript', (data) => {
      addTranscript(data.speaker === 'user' ? 'Partner' : data.speaker, data.text);
    });
    
    // Transcription Result
    socketRef.current.on('transcription-result', (data) => {
      addTranscript('You (AI)', data.text);
    });
    
    // Text Emotion Analysis
    socketRef.current.on('text-emotion', (data) => {
      console.log('📝 Text emotion:', data);
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
      stopMediaStreams();
      stopVideoFrameCapture();
    };
  }, []);

  // Calculate Engagement Score from Emotions
  const calculateEngagement = (emotions) => {
    if (!emotions) return 0;
    const positive = (emotions['Happiness/Joy'] || 0) + (emotions['Trust'] || 0) + (emotions['Surprise'] || 0) * 0.5;
    const negative = (emotions['Anger'] || 0) + (emotions['Fear/FOMO'] || 0);
    return Math.max(0, Math.min(100, Math.round(positive - negative * 0.5)));
  };

  // Start Video Frame Capture for Analysis
  const startVideoFrameCapture = useCallback(() => {
    if (!backendConfig?.features?.videoAnalysis) {
      console.log('⚠️ Video analysis not available on backend');
      return;
    }
    
    stopVideoFrameCapture(); // Clear any existing interval
    
    videoFrameIntervalRef.current = setInterval(() => {
      if (localVideoRef.current && currentRoomId) {
        const canvas = document.createElement('canvas');
        const video = localVideoRef.current;
        
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);
        
        const frameData = canvas.toDataURL('image/jpeg', 0.5);
        
        socketRef.current?.emit('video-frame', {
          frame: frameData,
          roomId: currentRoomId
        });
      }
    }, 1000); // Send frame every second
  }, [currentRoomId, backendConfig]);

  // Stop Video Frame Capture
  const stopVideoFrameCapture = () => {
    if (videoFrameIntervalRef.current) {
      clearInterval(videoFrameIntervalRef.current);
      videoFrameIntervalRef.current = null;
    }
  };

  // Start Matchmaking
  const startMatchmaking = async () => {
    setIsInLobby(false);
    setIsWaiting(true);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { width: 640, height: 480 }, 
        audio: true 
      });
      
      localStreamRef.current = stream;
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = stream;
      }

      setConnectionStatus('connecting');
      
      // Notify backend
      socketRef.current?.emit('identify', { 
        type: 'user',
        user_id: socketRef.current.id,
        timestamp: Date.now() 
      });

    } catch (err) {
      console.error('Media access error:', err);
      alert('Camera/Mic access required. Please check permissions.');
      stopSession();
    }
  };

  // Handle Match Found
  const handleMatchFound = (data) => {
    console.log('🎯 Match found:', data);
    setIsWaiting(false);
    setIsConnected(true);
    setConnectionStatus('connected');
    setCurrentRoomId(data.roomId);

    // Join the room
    socketRef.current?.emit('join-room', { roomId: data.roomId });

    // Simulate remote stream (in production, use WebRTC peer connection)
    if (remoteVideoRef.current && localStreamRef.current) {
      remoteVideoRef.current.srcObject = localStreamRef.current;
      remoteVideoRef.current.muted = true;
    }

    initSpeechRecognition();
    startVideoFrameCapture();
    
    // Notify backend that session started
    socketRef.current?.emit('session-started', { roomId: data.roomId });
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
    setCurrentRoomId(null);
    setTranscript([]);
    setAiSuggestion('');
    setAnalytics({
      hr: 0,
      dominant_emotion: 'Neutral',
      emotions: {
        'Happiness/Joy': 0,
        'Trust': 0,
        'Fear/FOMO': 0,
        'Surprise': 0,
        'Anger': 0
      },
      gaze_x: 50,
      gaze_y: 50
    });

    stopMediaStreams();
    stopSpeechRecognition();
    stopVideoFrameCapture();

    socketRef.current?.emit('leave-room');
  };

  // Stop Media Streams
  const stopMediaStreams = () => {
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach(track => track.stop());
      localStreamRef.current = null;
    }
  };

  // Initialize Speech Recognition
  const initSpeechRecognition = () => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      console.log('Speech recognition not supported');
      addTranscript('System', 'Speech recognition not available in this browser');
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognitionRef.current = new SpeechRecognition();
    recognitionRef.current.continuous = true;
    recognitionRef.current.interimResults = true;

    recognitionRef.current.onresult = (event) => {
      const last = event.results.length - 1;
      const text = event.results[last][0].transcript;
      
      if (event.results[last].isFinal) {
        addTranscript('You', text);
        
        // Send to backend for AI analysis
        socketRef.current?.emit('transcript', { 
          speaker: 'user', 
          text,
          roomId: currentRoomId,
          timestamp: Date.now()
        });
      }
    };

    recognitionRef.current.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      if (event.error === 'no-speech') {
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
      addTranscript('You', e.target.value);
      socketRef.current?.emit('transcript', { 
        speaker: 'user', 
        text: e.target.value,
        roomId: currentRoomId,
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
      hr: analytics.hr,
      roomId: currentRoomId
    });
    setAiSuggestion('🔍 Analyzing conversation context and emotional state...');
  };

  // Dashboard Drag Handlers
  const handleDashboardMouseDown = (e) => {
    isDraggingRef.current = true;
    const rect = e.currentTarget.getBoundingClientRect();
    dragOffsetRef.current = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    };
  };

  const handleDashboardMouseMove = (e) => {
    if (!isDraggingRef.current) return;
    
    const container = e.currentTarget.closest('.main-stage');
    if (!container) return;
    
    const rect = container.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width - 200, e.clientX - rect.left - dragOffsetRef.current.x));
    const y = Math.max(0, Math.min(rect.height - 200, e.clientY - rect.top - dragOffsetRef.current.y));
    
    setDashboardPosition({ x, y });
  };

  const handleDashboardMouseUp = () => {
    isDraggingRef.current = false;
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
            <Phone className="w-4 h-4 text-white" />
          </div>
          <h1 className="font-bold text-lg tracking-wide hidden md:block">
            InsightEngine <span className="text-xs font-normal text-gray-500">P2P v2.0 Integrated</span>
          </h1>
          <h1 className="font-bold text-lg tracking-wide md:hidden">
            IE <span className="text-xs font-normal text-gray-500">v2</span>
          </h1>
        </div>
        
        <div className="flex items-center gap-4">
          <StatusDot />
          {isConnected && (
            <button 
              onClick={stopSession}
              className="bg-red-600/20 text-red-400 hover:bg-red-600 hover:text-white px-4 py-1.5 rounded text-sm transition border border-red-600/50 flex items-center gap-2"
            >
              <PhoneOff className="w-4 h-4" />
              <span className="hidden sm:inline">End Call</span>
            </button>
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
                <Video className="w-8 h-8 text-indigo-500" />
              </div>
            </div>
            
            <div className="space-y-2">
              <h2 className="text-3xl font-bold text-white">Sales Simulator</h2>
              <p className="text-gray-400 text-sm">
                AI-powered P2P training with real-time emotion analysis, heart rate monitoring, and intelligent coaching.
              </p>
            </div>
            
            <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700 text-left space-y-3">
              <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider">System Status</h3>
              
              <div className="flex justify-between text-sm items-center">
                <span className="text-gray-300 flex items-center gap-2">
                  <Camera className="w-4 h-4 text-indigo-400" />
                  Camera
                </span>
                <span className="text-green-400 text-xs bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">
                  Ready
                </span>
              </div>
              
              <div className="flex justify-between text-sm items-center">
                <span className="text-gray-300 flex items-center gap-2">
                  <Mic className="w-4 h-4 text-indigo-400" />
                  Microphone
                </span>
                <span className="text-green-400 text-xs bg-green-400/10 px-2 py-0.5 rounded border border-green-400/20">
                  Ready
                </span>
              </div>
              
              <div className="flex justify-between text-sm items-center">
                <span className="text-gray-300 flex items-center gap-2">
                  <Network className="w-4 h-4 text-indigo-400" />
                  Backend Server
                </span>
                <span className={`text-xs px-2 py-0.5 rounded border ${
                  connectionStatus === 'online' || connectionStatus === 'connected'
                    ? 'text-green-400 bg-green-400/10 border-green-400/20'
                    : 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'
                }`}>
                  {connectionStatus === 'online' || connectionStatus === 'connected' ? 'Connected' : 'Connecting...'}
                </span>
              </div>
              
              {backendConfig && (
                <div className="border-t border-gray-700 pt-2 mt-2 space-y-2">
                  <div className="text-xs text-gray-500">Backend Features:</div>
                  <div className="flex gap-2 flex-wrap">
                    {backendConfig.features.videoAnalysis && (
                      <span className="text-xs bg-indigo-500/10 text-indigo-400 px-2 py-0.5 rounded">Video Analysis</span>
                    )}
                    {backendConfig.features.audioTranscription && (
                      <span className="text-xs bg-purple-500/10 text-purple-400 px-2 py-0.5 rounded">Audio AI</span>
                    )}
                    {backendConfig.features.emotionDetection && (
                      <span className="text-xs bg-pink-500/10 text-pink-400 px-2 py-0.5 rounded">Emotion AI</span>
                    )}
                  </div>
                </div>
              )}
            </div>

            <button 
              onClick={startMatchmaking}
              disabled={connectionStatus === 'offline' || connectionStatus === 'error'}
              className="group w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed text-white py-3 rounded-xl font-bold text-lg shadow-lg shadow-indigo-500/30 transition-all transform hover:scale-[1.02] active:scale-[0.98]"
            >
              {connectionStatus === 'offline' || connectionStatus === 'error' ? 'Connecting to Server...' : 'Start Session →'}
            </button>
          </div>
        </div>
      )}

      {/* Main Grid - Rest of the UI remains the same as your original App.js */}
      <div className="flex-1 grid md:grid-cols-[1fr_400px] grid-rows-[2fr_1fr] md:grid-rows-1 overflow-hidden">
        
        {/* Video Stage */}
        <div className="relative bg-black flex items-center justify-center overflow-hidden main-stage">
          
          {/* Remote Video */}
          <video 
            ref={remoteVideoRef}
            autoPlay
            playsInline
            className="w-full h-full object-cover"
            style={{ transform: 'scaleX(-1)' }}
          />

          {/* AR Overlays */}
          {isConnected && (
            <div className="absolute inset-0 pointer-events-none z-10">
              {/* Gaze Tracker */}
              <div 
                className="absolute w-6 h-6 border-2 border-cyan-400 bg-cyan-400/20 rounded-full transition-all duration-500 shadow-lg shadow-cyan-400/50"
                style={{ 
                  left: `${analytics.gaze_x}%`, 
                  top: `${analytics.gaze_y}%`,
                  transform: 'translate(-50%, -50%)'
                }}
              >
                <Eye className="w-3 h-3 text-cyan-300 absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2" />
              </div>
              
              {/* Face Bounding Box */}
              <div 
                className="absolute border-2 border-indigo-500/40 rounded-lg"
                style={{ top: '20%', left: '30%', width: '40%', height: '60%' }}
              >
                <div className="absolute -top-6 left-0 bg-indigo-600 text-white text-xs px-2 py-1 rounded font-bold shadow-lg flex items-center gap-2">
                  <Activity className="w-3 h-3" />
                  {analytics.dominant_emotion}
                </div>
                
                {/* Heart Rate Badge */}
                <div className="absolute -top-6 right-0 bg-red-600 text-white text-xs px-2 py-1 rounded font-bold shadow-lg flex items-center gap-1">
                  <Heart className="w-3 h-3 animate-pulse" />
                  {analytics.hr} BPM
                </div>
              </div>

              {/* Draggable Analytics Dashboard */}
              <div 
                className="absolute bg-gray-900/90 backdrop-blur-md border border-gray-700/50 p-4 rounded-xl shadow-2xl space-y-3 w-64 cursor-move select-none pointer-events-auto z-50"
                style={{ left: dashboardPosition.x, top: dashboardPosition.y }}
                onMouseDown={handleDashboardMouseDown}
                onMouseMove={handleDashboardMouseMove}
                onMouseUp={handleDashboardMouseUp}
                onMouseLeave={handleDashboardMouseUp}
              >
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <div className="text-xs text-gray-400 font-bold tracking-wider">ENGAGEMENT SCORE</div>
                    <TrendingUp className="w-3 h-3 text-indigo-400" />
                  </div>
                  <div className="flex items-end gap-2 mb-3">
                    <span className="text-3xl font-bold text-white font-mono">{stats.engagement}%</span>
                    <div className="flex-1 h-2 bg-gray-700 rounded-full mb-2 overflow-hidden">
                      <div 
                        className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-700 ease-out"
                        style={{ width: `${stats.engagement}%` }}
                      />
                    </div>
                  </div>
                </div>
                
                <div className="border-t border-gray-700 pt-3 space-y-1">
                  <h4 className="text-xs text-gray-400 font-bold mb-2">EMOTIONAL STATE</h4>
                  <EmotionBar label="Joy" value={analytics.emotions['Happiness/Joy'] || 0} color="bg-yellow-500" />
                  <EmotionBar label="Trust" value={analytics.emotions['Trust'] || 0} color="bg-blue-500" />
                  <EmotionBar label="Surprise" value={analytics.emotions['Surprise'] || 0} color="bg-purple-500" />
                  <EmotionBar label="Fear/FOMO" value={analytics.emotions['Fear/FOMO'] || 0} color="bg-orange-500" />
                  <EmotionBar label="Anger" value={analytics.emotions['Anger'] || 0} color="bg-red-500" />
                </div>
              </div>
            </div>
          )}

          {/* Local Video PIP */}
          {isConnected && (
            <div className="absolute bottom-5 right-5 w-44 aspect-video bg-gray-800 border-2 border-indigo-600 rounded-lg overflow-hidden shadow-xl z-50 group">
              <video 
                ref={localVideoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover"
                style={{ transform: 'scaleX(-1)' }}
              />
              <div className="absolute bottom-1 left-2 text-xs text-white font-bold drop-shadow-md bg-black/50 px-1 rounded opacity-0 group-hover:opacity-100 transition">
                YOU
              </div>
              <div className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full animate-pulse border border-black/20" />
            </div>
          )}

          {/* Waiting Message */}
          {isWaiting && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-900/95 z-20">
              <div className="w-8 h-8 border-3 border-gray-300 border-t-indigo-500 rounded-full animate-spin mb-4" />
              <p className="text-indigo-200 animate-pulse font-medium mb-2">
                Finding a match...
              </p>
              <p className="text-gray-500 text-sm">
                Initializing AI analytics engine
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

        {/* Sidebar - Transcript and AI Coach */}
        <div className="bg-gray-900/95 backdrop-blur-md border-l border-gray-800 flex flex-col md:border-t-0 border-t">
          
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
                        entry.speaker === 'You' || entry.speaker === 'You (AI)' ? 'text-indigo-400' : 
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
                  placeholder="Type to simulate speech..."
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
                    {isConnected ? 'Monitoring conversation patterns...' : 'AI coach will activate during session'}
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