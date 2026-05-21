import React, { useState, useEffect, useRef } from 'react';

// Interfaces for structured data
interface Doctor {
  id: number;
  name: string;
  specialty: string;
  available_days: string;
  available_hours: string;
  languages: string;
}

interface Appointment {
  id: number;
  patient_id: string;
  patient_name: string;
  doctor_id: number;
  doctor_name: string;
  specialty: string;
  date: string;
  time: string;
  status: 'booked' | 'rescheduled' | 'cancelled';
}

interface Patient {
  id: string;
  name: string;
  preferred_language: string;
  preferred_doctor_id: number;
  notes: string;
  appointments: any[];
}

interface TranscriptItem {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
}

interface LatencyMetrics {
  stt: number;
  llm: number;
  tts: number;
  network: number;
  total: number;
}

export default function App() {
  // App settings
  const [patientId, setPatientId] = useState<string>('P101');
  const [apiKey, setApiKey] = useState<string>(() => localStorage.getItem('2care_api_key') || '');
  const [useLocalSpeechAPI, setUseLocalSpeechAPI] = useState<boolean>(true); // True = Hybrid Mode, False = Server Audio Mode
  const [showConfigModal, setShowConfigModal] = useState<boolean>(false);

  // Connection & Call State
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [callActive, setCallActive] = useState<boolean>(false);
  const [callState, setCallState] = useState<'IDLE' | 'CONNECTING' | 'GREETING' | 'LISTENING' | 'THINKING' | 'SPEAKING'>('IDLE');
  
  // Database States
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [patientProfile, setPatientProfile] = useState<Patient | null>(null);

  // Active Session memory synced from backend
  const [sessionState, setSessionState] = useState<any>({
    session_id: '',
    intent: null,
    doctor_id: null,
    doctor_name: null,
    date: null,
    time: null,
    language: 'English',
    alternatives_offered: []
  });

  // Conversation logs
  const [transcripts, setTranscripts] = useState<TranscriptItem[]>([]);
  const [thinkingLogs, setThinkingLogs] = useState<string[]>([]);
  const [textInput, setTextInput] = useState<string>('');
  
  // Latency Metrics
  const [metrics, setMetrics] = useState<LatencyMetrics>({
    stt: 0,
    llm: 0,
    tts: 0,
    network: 0,
    total: 0
  });

  // References
  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioInputRef = useRef<any>(null);
  const recognitionRef = useRef<any>(null);
  const audioPlayingRef = useRef<HTMLAudioElement | null>(null);
  const logsEndRef = useRef<HTMLDivElement | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  // Save API key to local storage
  useEffect(() => {
    localStorage.setItem('2care_api_key', apiKey);
  }, [apiKey]);

  // Load database metadata on startup and whenever calls affect state
  useEffect(() => {
    fetchDoctors();
    fetchAppointments();
    fetchPatientProfile();
  }, [patientId]);

  // Scroll to bottom helper
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [thinkingLogs]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcripts]);

  const fetchDoctors = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/doctors');
      const data = await res.json();
      if (data.status === 'success') setDoctors(data.doctors);
    } catch (e) {
      console.error("Error loading doctors", e);
    }
  };

  const fetchAppointments = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/appointments');
      const data = await res.json();
      if (data.status === 'success') setAppointments(data.appointments);
    } catch (e) {
      console.error("Error loading appointments", e);
    }
  };

  const fetchPatientProfile = async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/patients/${patientId}`);
      const data = await res.json();
      if (data.status === 'success') setPatientProfile(data.patient);
    } catch (e) {
      console.error("Error loading patient profile", e);
    }
  };

  // Trigger outbound campaign trigger
  const triggerOutbound = async (campaignType: string, docId: number) => {
    try {
      const res = await fetch('http://localhost:8000/api/outbound/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: patientId,
          doctor_id: docId,
          campaign_type: campaignType
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        alert(`Campaign '${campaignType}' scheduled for ${patientProfile?.name}. Click 'Start Call' to trigger the call!`);
      }
    } catch (e) {
      console.error("Error triggering outbound campaign", e);
    }
  };

  // --- Speech Recognition Browser API Setup ---
  const initBrowserSpeechRecognition = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("Browser Speech Recognition not supported in this browser.");
      return;
    }
    const r = new SpeechRecognition();
    r.continuous = false;
    r.interimResults = false;
    
    // Dynamically adjust language code
    if (sessionState.language === 'Hindi') {
      r.lang = 'hi-IN';
    } else if (sessionState.language === 'Tamil') {
      r.lang = 'ta-IN';
    } else {
      r.lang = 'en-US';
    }

    r.onstart = () => {
      setCallState('LISTENING');
    };

    r.onresult = (event: any) => {
      const text = event.results[0][0].transcript;
      console.log("Browser Speech Result: ", text);
      sendTextTranscript(text);
    };

    r.onerror = (e: any) => {
      console.error("Speech Recognition Error", e);
      if (callActive) {
        // Restart listening if active
        setTimeout(() => {
          try { r.start(); } catch (err) {}
        }, 1000);
      }
    };

    r.onend = () => {
      if (callActive && callState === 'LISTENING') {
        try { r.start(); } catch (err) {}
      }
    };

    recognitionRef.current = r;
  };

  // Speech Synthesis Browser API Setup (for hybrid mode tts)
  const speakTextBrowser = (text: string, langName: string) => {
    window.speechSynthesis.cancel(); // Stop playing previous
    const utterance = new SpeechSynthesisUtterance(text);
    
    let langCode = 'en-US';
    if (langName === 'Hindi') langCode = 'hi-IN';
    else if (langName === 'Tamil') langCode = 'ta-IN';
    utterance.lang = langCode;

    // Try to find a high quality native voice
    const voices = window.speechSynthesis.getVoices();
    const matchedVoice = voices.find(v => v.lang.startsWith(langCode));
    if (matchedVoice) utterance.voice = matchedVoice;

    utterance.onstart = () => {
      setCallState('SPEAKING');
    };
    utterance.onend = () => {
      setCallState('LISTENING');
      if (useLocalSpeechAPI && recognitionRef.current) {
        try { recognitionRef.current.start(); } catch (e) {}
      }
    };

    window.speechSynthesis.speak(utterance);
  };

  // --- WebSocket Call Flow ---
  const startCall = () => {
    if (callActive) return;
    
    setCallActive(true);
    setCallState('CONNECTING');
    setTranscripts([]);
    setThinkingLogs(['Initiating WebSocket handshake...']);
    
    // Connect to WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//localhost:8000/ws/voice?session_id=sess_${Date.now()}&patient_id=${patientId}&api_key=${apiKey}`;
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      setThinkingLogs(prev => [...prev, 'WebSocket connection established. Session active.']);
      setCallState('GREETING');
    };

    ws.onmessage = async (event) => {
      if (event.data instanceof Blob) {
        // Binary audio stream response
        setThinkingLogs(prev => [...prev, `Received audio packet: ${event.data.size} bytes.`]);
        setCallState('SPEAKING');
        
        // Convert Blob to URL and play
        const audioUrl = URL.createObjectURL(event.data);
        if (audioPlayingRef.current) {
          audioPlayingRef.current.pause();
        }
        const audio = new Audio(audioUrl);
        audioPlayingRef.current = audio;
        
        audio.onplay = () => {
          // If native recognition is running, mute or pause it to avoid hearing itself (barge-in prevention)
          if (useLocalSpeechAPI && recognitionRef.current) {
            try { recognitionRef.current.stop(); } catch (e) {}
          }
        };
        
        audio.onended = () => {
          setCallState('LISTENING');
          // Resume listening
          if (useLocalSpeechAPI && recognitionRef.current) {
            try { recognitionRef.current.start(); } catch (e) {}
          }
        };
        
        audio.play().catch(err => {
          console.error("Audio playback blocked by browser", err);
          setCallState('LISTENING');
        });
      } else {
        // JSON Text events
        const data = JSON.parse(event.data);
        
        switch (data.type) {
          case 'state':
            setSessionState(data.state);
            // Refresh DB listings to show updates in real-time
            fetchAppointments();
            fetchPatientProfile();
            break;
            
          case 'thinking':
            setThinkingLogs(prev => [...prev, data.log]);
            break;
            
          case 'user_transcript':
            setCallState('THINKING');
            setTranscripts(prev => [...prev, {
              role: 'user',
              text: data.text,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
            }]);
            break;
            
          case 'agent_response':
            setTranscripts(prev => [...prev, {
              role: 'assistant',
              text: data.text,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
            }]);
            
            // If hybrid mode is toggled, browser synthesizes local voice
            if (useLocalSpeechAPI) {
              speakTextBrowser(data.text, sessionState.language);
            }
            break;
            
          case 'stop_audio':
            // Stop active playback on user barge-in
            if (audioPlayingRef.current) {
              audioPlayingRef.current.pause();
              setThinkingLogs(prev => [...prev, '[Barge-in] Stopped agent speech.']);
            }
            window.speechSynthesis.cancel();
            break;
            
          case 'latency':
            setMetrics(data.metrics);
            break;
            
          default:
            console.log("Unhandled WS message", data);
        }
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
      setCallActive(false);
      setCallState('IDLE');
      setThinkingLogs(prev => [...prev, 'Session disconnected.']);
      stopAudioRecording();
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (e) {}
      }
    };

    ws.onerror = (e) => {
      console.error("WS error", e);
    };

    // Initialize inputs
    if (useLocalSpeechAPI) {
      initBrowserSpeechRecognition();
      // Start listening after connection resolves
      setTimeout(() => {
        if (recognitionRef.current) {
          try { recognitionRef.current.start(); } catch (err) {}
        }
      }, 1000);
    } else {
      // Backend Audio Mode: start recording mic and streaming chunks
      startAudioRecording();
    }
  };

  const endCall = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    if (audioPlayingRef.current) {
      audioPlayingRef.current.pause();
    }
    window.speechSynthesis.cancel();
    stopAudioRecording();
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch (e) {}
    }
    setCallActive(false);
    setCallState('IDLE');
  };

  // --- Audio Recorder for Server-Side STT Streaming ---
  const startAudioRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      const audioContext = new AudioContextClass();
      audioContextRef.current = audioContext;
      
      const source = audioContext.createMediaStreamSource(stream);
      // Processor to chunk raw audio bytes
      const processor = audioContext.createScriptProcessor(2048, 1, 1);
      audioInputRef.current = processor;
      
      source.connect(processor);
      processor.connect(audioContext.destination);
      
      setCallState('LISTENING');
      
      processor.onaudioprocess = (e) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        
        const inputData = e.inputBuffer.getChannelData(0);
        // Downsample PCM float32 to Int16 to save bandwidth
        const buffer = new ArrayBuffer(inputData.length * 2);
        const view = new DataView(buffer);
        let offset = 0;
        for (let i = 0; i < inputData.length; i++, offset += 2) {
          let s = Math.max(-1, Math.min(1, inputData[i]));
          view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }
        
        // Send raw PCM bytes chunk
        wsRef.current.send(buffer);
      };
    } catch (err) {
      console.error("Failed to start recording mic stream", err);
      setThinkingLogs(prev => [...prev, 'Error: Microphone access denied.']);
      endCall();
    }
  };

  const stopAudioRecording = () => {
    if (audioInputRef.current) {
      audioInputRef.current.disconnect();
      audioInputRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }
  };

  // Send visual text transcript (used for hybrid mode or typing manually)
  const sendTextTranscript = (text: string) => {
    if (!text.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    
    wsRef.current.send(JSON.stringify({
      type: 'text_transcript',
      text: text
    }));
  };

  const handleManualInputSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;
    
    // Simulate user speaking (useful if mic isn't available or for fast testing)
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      if (useLocalSpeechAPI) {
        sendTextTranscript(textInput);
      } else {
        // Send a simulated audio command to server with text fallback
        wsRef.current.send(JSON.stringify({
          type: 'stop-speaking',
          text_fallback: textInput
        }));
      }
      setTextInput('');
    } else {
      alert("Call must be active to chat.");
    }
  };

  // Trigger manual interrupt
  const triggerBargeIn = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
    }
  };

  // Trigger mock release-to-send when recording on server mode
  const triggerStopSpeaking = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN && !useLocalSpeechAPI) {
      wsRef.current.send(JSON.stringify({ type: 'stop-speaking' }));
    }
  };

  return (
    <div className="dashboard-container">
      {/* Header Bar */}
      <header className="glass-card" style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: 'var(--primary)', boxShadow: '0 0 10px var(--primary)' }}></div>
          <h1 style={{ fontSize: '20px', fontWeight: '700', color: 'var(--text-primary)' }}>2Care.ai Voice Agent</h1>
          <span style={{ fontSize: '11px', background: 'rgba(255,255,255,0.06)', padding: '2px 8px', borderRadius: '4px', color: 'var(--text-muted)' }}>
            v1.0.0 (FastAPI + SQLite)
          </span>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div className={`status-indicator ${wsConnected ? 'status-online' : 'status-offline'}`}>
            {wsConnected ? 'WebSocket Online' : 'WebSocket Offline'}
          </div>
          
          <button 
            className="slot-btn" 
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px' }}
            onClick={() => setShowConfigModal(true)}
          >
            ⚙️ API Keys
          </button>
        </div>
      </header>

      {/* LEFT COLUMN: CALL PANEL & SETTINGS */}
      <aside className="glass-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px', overflowY: 'auto' }}>
        <div>
          <h3 style={{ fontSize: '15px', color: 'var(--text-primary)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            👥 Patient Selector
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {[
              { id: 'P101', name: 'Amit Kumar', lang: 'Hindi (हिन्दी)' },
              { id: 'P102', name: 'Srinivasan', lang: 'Tamil (தமிழ்)' },
              { id: 'P103', name: 'Sarah Jenkins', lang: 'English' }
            ].map(p => (
              <div 
                key={p.id}
                onClick={() => !callActive && setPatientId(p.id)}
                style={{
                  padding: '10px',
                  borderRadius: 'var(--border-radius-sm)',
                  background: patientId === p.id ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${patientId === p.id ? 'var(--primary)' : 'var(--border-color)'}`,
                  cursor: callActive ? 'not-allowed' : 'pointer',
                  transition: 'var(--transition-smooth)'
                }}
              >
                <div style={{ fontWeight: '600', fontSize: '13px' }}>{p.name}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between', marginTop: '2px' }}>
                  <span>ID: {p.id}</span>
                  <span>{p.lang}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h3 style={{ fontSize: '15px', color: 'var(--text-primary)', marginBottom: '10px' }}>🎙️ Voice Pipeline Mode</h3>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button 
              className="slot-btn"
              style={{ flex: 1, padding: '10px 4px', background: useLocalSpeechAPI ? 'rgba(16, 185, 129, 0.1)' : 'transparent', borderColor: useLocalSpeechAPI ? 'var(--secondary)' : 'var(--border-color)' }}
              onClick={() => !callActive && setUseLocalSpeechAPI(true)}
              title="Transcribes in browser, super fast."
            >
              Hybrid Native
            </button>
            <button 
              className="slot-btn"
              style={{ flex: 1, padding: '10px 4px', background: !useLocalSpeechAPI ? 'rgba(99, 102, 241, 0.1)' : 'transparent', borderColor: !useLocalSpeechAPI ? 'var(--primary)' : 'var(--border-color)' }}
              onClick={() => !callActive && setUseLocalSpeechAPI(false)}
              title="Streams raw audio chunks to backend."
            >
              Server Audio
            </button>
          </div>
        </div>

        <div style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', justifyItems: 'center', justifyContent: 'center', alignItems: 'center', border: '1px dashed var(--border-color)', borderRadius: 'var(--border-radius-md)', padding: '20px', background: 'rgba(0,0,0,0.1)' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700', marginBottom: '8px' }}>
            Agent Call State
          </div>
          <div style={{
            fontSize: '18px',
            fontWeight: '800',
            color: callState === 'LISTENING' ? '#10b981' : callState === 'THINKING' ? '#f59e0b' : callState === 'SPEAKING' ? '#6366f1' : 'var(--text-muted)',
            marginBottom: '20px',
            letterSpacing: '0.05em'
          }}>
            {callState}
          </div>

          <div className={`waveform-container ${['LISTENING', 'SPEAKING'].includes(callState) ? 'waveform-active' : ''}`} style={{ marginBottom: '24px' }}>
            <div className="waveform-bar"></div>
            <div className="waveform-bar"></div>
            <div className="waveform-bar"></div>
            <div className="waveform-bar"></div>
            <div className="waveform-bar"></div>
            <div className="waveform-bar"></div>
            <div className="waveform-bar"></div>
            <div className="waveform-bar"></div>
            <div className="waveform-bar"></div>
            <div className="waveform-bar"></div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', width: '100%', gap: '8px' }}>
            {!callActive ? (
              <button 
                onClick={startCall}
                style={{
                  width: '100%',
                  padding: '14px',
                  borderRadius: '30px',
                  background: 'linear-gradient(135deg, #10b981, #059669)',
                  color: 'white',
                  fontWeight: '700',
                  border: 'none',
                  boxShadow: '0 4px 15px rgba(16, 185, 129, 0.3)',
                  cursor: 'pointer',
                  fontSize: '14px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px'
                }}
              >
                📞 Start Call
              </button>
            ) : (
              <>
                <button 
                  onClick={endCall}
                  style={{
                    width: '100%',
                    padding: '14px',
                    borderRadius: '30px',
                    background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                    color: 'white',
                    fontWeight: '700',
                    border: 'none',
                    boxShadow: '0 4px 15px rgba(239, 68, 68, 0.3)',
                    cursor: 'pointer',
                    fontSize: '14px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px'
                  }}
                >
                  🛑 End Call
                </button>
                
                {callState === 'SPEAKING' && (
                  <button 
                    onClick={triggerBargeIn}
                    className="slot-btn"
                    style={{ background: 'rgba(245, 158, 11, 0.1)', borderColor: 'var(--accent)', color: '#fbbf24', borderRadius: '20px' }}
                  >
                    ✋ Tap to Interrupt (Barge-In)
                  </button>
                )}

                {!useLocalSpeechAPI && callState === 'LISTENING' && (
                  <button 
                    onClick={triggerStopSpeaking}
                    style={{
                      background: 'rgba(99, 102, 241, 0.2)',
                      borderColor: 'var(--primary)',
                      color: 'white',
                      padding: '10px',
                      borderRadius: '20px',
                      cursor: 'pointer',
                      border: '1px solid var(--primary)',
                      fontSize: '12px'
                    }}
                  >
                    🎙️ I'm Done Speaking (Send Audio)
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </aside>

      {/* CENTER COLUMN: LIVE CALL TRANSCRIPT & STATE DUMP */}
      <main style={{ display: 'flex', flexDirection: 'column', gap: '20px', overflow: 'hidden' }}>
        {/* Transcript Panel */}
        <section className="glass-card" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', padding: '20px', overflow: 'hidden' }}>
          <h3 style={{ fontSize: '15px', color: 'var(--text-primary)', marginBottom: '12px', borderBottom: '1px solid var(--border-color)', paddingBottom: '8px' }}>
            💬 Live Voice Transcript
          </h3>
          
          <div style={{ flexGrow: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px', paddingRight: '6px' }}>
            {transcripts.length === 0 ? (
              <div style={{ display: 'flex', flexGrow: 1, justifyItems: 'center', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dark)', fontSize: '13px' }}>
                No active call transcript. Click 'Start Call' to begin.
              </div>
            ) : (
              transcripts.map((t, idx) => (
                <div 
                  key={idx}
                  style={{
                    alignSelf: t.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '80%',
                    background: t.role === 'user' ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${t.role === 'user' ? 'rgba(99, 102, 241, 0.3)' : 'var(--border-color)'}`,
                    borderRadius: t.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                    padding: '10px 14px',
                    fontSize: '13px',
                    lineHeight: '1.4'
                  }}
                >
                  <div style={{ fontWeight: '700', fontSize: '11px', color: t.role === 'user' ? '#a5b4fc' : '#34d399', marginBottom: '2px', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{t.role === 'user' ? 'PATIENT' : 'CLINIC AI'}</span>
                    <span style={{ fontSize: '9px', opacity: 0.5, marginLeft: '12px' }}>{t.timestamp}</span>
                  </div>
                  <div>{t.text}</div>
                </div>
              ))
            )}
            <div ref={transcriptEndRef} />
          </div>

          <form onSubmit={handleManualInputSubmit} style={{ display: 'flex', gap: '8px', marginTop: '12px', borderTop: '1px solid var(--border-color)', paddingTop: '12px' }}>
            <input 
              type="text" 
              placeholder={callActive ? "Type message here to simulate speaking..." : "Start a call to chat..."}
              disabled={!callActive}
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              style={{
                flexGrow: 1,
                background: 'rgba(0,0,0,0.2)',
                border: '1px solid var(--border-color)',
                borderRadius: '20px',
                padding: '10px 16px',
                color: 'white',
                fontSize: '13px'
              }}
            />
            <button 
              type="submit" 
              disabled={!callActive}
              style={{
                background: 'var(--primary)',
                color: 'white',
                border: 'none',
                padding: '0 18px',
                borderRadius: '20px',
                cursor: 'pointer',
                fontWeight: '600',
                fontSize: '12px'
              }}
            >
              Send
            </button>
          </form>
        </section>

        {/* Console logs showing active reasoning steps */}
        <section className="glass-card" style={{ height: '180px', display: 'flex', flexDirection: 'column', padding: '16px 20px', overflow: 'hidden' }}>
          <h3 style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
            🤖 Agent reasoning & Tool Orchestration Logs
          </h3>
          <div style={{
            flexGrow: 1,
            overflowY: 'auto',
            background: '#040508',
            borderRadius: 'var(--border-radius-sm)',
            padding: '10px',
            fontFamily: 'monospace',
            fontSize: '11px',
            color: '#a7f3d0',
            lineHeight: '1.5'
          }}>
            {thinkingLogs.length === 0 ? (
              <span style={{ color: 'var(--text-dark)' }}>Logs will appear here during active agent execution...</span>
            ) : (
              thinkingLogs.map((log, idx) => (
                <div key={idx} style={{ marginBottom: '4px' }}>
                  <span style={{ color: '#6366f1' }}>&gt;</span> {log}
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </section>
      </main>

      {/* RIGHT COLUMN: CALENDAR & MEMORIES */}
      <aside style={{ display: 'flex', flexDirection: 'column', gap: '20px', overflowY: 'auto' }}>
        {/* Session Memory */}
        <section className="glass-card" style={{ padding: '16px 20px' }}>
          <h3 style={{ fontSize: '14px', color: 'var(--text-primary)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            🧠 Session Context (RAM)
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '11px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Intent:</span>
              <span style={{ color: 'var(--accent)', fontWeight: 'bold' }}>{sessionState.intent || 'None'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Doctor:</span>
              <span style={{ color: 'white', fontWeight: '600' }}>{sessionState.doctor_name || 'None'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Date:</span>
              <span style={{ color: 'white', fontWeight: '600' }}>{sessionState.date || 'None'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Time Slot:</span>
              <span style={{ color: 'white', fontWeight: '600' }}>{sessionState.time || 'None'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Language:</span>
              <span style={{ color: 'var(--primary)', fontWeight: '600' }}>{sessionState.language}</span>
            </div>
            {sessionState.alternatives_offered && sessionState.alternatives_offered.length > 0 && (
              <div style={{ marginTop: '6px' }}>
                <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Suggested alternatives:</span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {sessionState.alternatives_offered.map((alt: any, idx: number) => (
                    <span 
                      key={idx}
                      style={{
                        background: 'rgba(245, 158, 11, 0.08)',
                        border: '1px solid rgba(245, 158, 11, 0.3)',
                        borderRadius: '4px',
                        padding: '2px 6px',
                        color: '#fbbf24',
                        fontSize: '9px'
                      }}
                    >
                      {alt[0]} @ {alt[1]}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Persistent Memory */}
        <section className="glass-card" style={{ padding: '16px 20px' }}>
          <h3 style={{ fontSize: '14px', color: 'var(--text-primary)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            💾 Persistent Memory (DB)
          </h3>
          {patientProfile ? (
            <div style={{ fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Patient Name:</span>
                <span style={{ fontWeight: '600' }}>{patientProfile.name}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Pref Language:</span>
                <span style={{ color: 'var(--primary)' }}>{patientProfile.preferred_language || 'Not Set'}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', marginTop: '4px' }}>
                <span style={{ color: 'var(--text-muted)', marginBottom: '2px' }}>Clinical Heuristics/Notes:</span>
                <div style={{ background: 'rgba(0,0,0,0.15)', padding: '6px', borderRadius: '4px', border: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                  {patientProfile.notes || 'No profile notes.'}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ fontSize: '11px', color: 'var(--text-dark)' }}>No patient context loaded.</div>
          )}
        </section>

        {/* Outbound Campaigns Panel */}
        <section className="glass-card" style={{ padding: '16px 20px' }}>
          <h3 style={{ fontSize: '14px', color: 'var(--text-primary)', marginBottom: '10px' }}>
            🚀 Outbound Campaigns
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <button 
              className="slot-btn" 
              style={{ textAlign: 'left', display: 'flex', justifyItems: 'center', justifyContent: 'space-between', padding: '8px' }}
              onClick={() => triggerOutbound('reminder', 1)}
            >
              <span>📅 Send Appointment Reminder</span>
              <span>Dr. Sharma</span>
            </button>
            <button 
              className="slot-btn" 
              style={{ textAlign: 'left', display: 'flex', justifyItems: 'center', justifyContent: 'space-between', padding: '8px' }}
              onClick={() => triggerOutbound('follow-up', 3)}
            >
              <span>🩺 Schedule Follow-up Call</span>
              <span>Dr. Raja</span>
            </button>
            <button 
              className="slot-btn" 
              style={{ textAlign: 'left', display: 'flex', justifyItems: 'center', justifyContent: 'space-between', padding: '8px' }}
              onClick={() => triggerOutbound('vaccination', 4)}
            >
              <span>💉 Trigger Vaccination Alert</span>
              <span>Dr. Krishnan</span>
            </button>
          </div>
        </section>
      </aside>

      {/* CALENDAR BOARD - SPANS BOTTOM LEFT & CENTER */}
      <section className="glass-card" style={{ gridColumn: '1 / -2', padding: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <h3 style={{ fontSize: '15px', color: 'var(--text-primary)', borderBottom: '1px solid var(--border-color)', paddingBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>📅 Clinical Scheduling Board & Active Bookings</span>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Target Schedule for: Tomorrow / Active Week</span>
        </h3>
        
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
          {doctors.map(doc => {
            // Find appointments for this doctor tomorrow (2026-05-22)
            const docAppts = appointments.filter(a => a.doctor_id === doc.id && a.status !== 'cancelled');
            
            return (
              <div 
                key={doc.id}
                style={{
                  background: 'rgba(255, 255, 255, 0.01)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--border-radius-md)',
                  padding: '12px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <h4 style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{doc.name}</h4>
                    <span style={{ fontSize: '10px', color: 'var(--primary)', fontWeight: '600' }}>{doc.specialty}</span>
                  </div>
                  <div style={{ display: 'flex', gap: '2px', fontSize: '9px', background: 'rgba(255,255,255,0.04)', padding: '2px 4px', borderRadius: '4px' }}>
                    🌐 {doc.languages}
                  </div>
                </div>
                
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                  🕒 {doc.available_days} | {doc.available_hours}
                </div>

                <div style={{ marginTop: '8px' }}>
                  <div style={{ fontSize: '10px', fontWeight: '700', color: 'var(--text-primary)', marginBottom: '4px' }}>
                    Active Appointments
                  </div>
                  {docAppts.length === 0 ? (
                    <div style={{ fontSize: '10px', color: 'var(--text-dark)', fontStyle: 'italic' }}>
                      No booked slots.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {docAppts.map(a => (
                        <div 
                          key={a.id} 
                          style={{
                            background: a.status === 'rescheduled' ? 'rgba(245, 158, 11, 0.08)' : 'rgba(16, 185, 129, 0.08)',
                            border: `1px solid ${a.status === 'rescheduled' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(16, 185, 129, 0.2)'}`,
                            borderRadius: '4px',
                            padding: '4px 8px',
                            fontSize: '10px',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center'
                          }}
                        >
                          <span style={{ fontWeight: '600' }}>{a.time} - {a.patient_name} ({a.date})</span>
                          <span style={{
                            fontSize: '8px',
                            padding: '1px 4px',
                            borderRadius: '2px',
                            background: a.status === 'rescheduled' ? 'var(--accent)' : 'var(--secondary)',
                            color: 'black',
                            fontWeight: 'bold'
                          }}>
                            {a.status.toUpperCase()}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* LATENCY METRICS DASHBOARD (SPANS BOTTOM RIGHT) */}
      <section className="glass-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <h3 style={{ fontSize: '14px', color: 'var(--text-primary)', borderBottom: '1px solid var(--border-color)', paddingBottom: '8px' }}>
          ⏱️ Real-Time Latency Meter
        </h3>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
            <span style={{ color: 'var(--text-muted)' }}>Speech Recognition (STT):</span>
            <span style={{ fontFamily: 'monospace' }}>{metrics.stt.toFixed(0)} ms</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
            <span style={{ color: 'var(--text-muted)' }}>LLM Agent Reasoning:</span>
            <span style={{ fontFamily: 'monospace' }}>{metrics.llm.toFixed(0)} ms</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
            <span style={{ color: 'var(--text-muted)' }}>Voice Synthesis (TTS):</span>
            <span style={{ fontFamily: 'monospace' }}>{metrics.tts.toFixed(0)} ms</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
            <span style={{ color: 'var(--text-muted)' }}>Network Handshake:</span>
            <span style={{ fontFamily: 'monospace' }}>{metrics.network.toFixed(0)} ms</span>
          </div>
          
          <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '6px', marginTop: '4px', display: 'flex', justifyContent: 'space-between', fontSize: '12px', fontWeight: 'bold' }}>
            <span>Total Turnaround:</span>
            <span style={{ color: metrics.total <= 450 ? '#34d399' : metrics.total <= 1000 ? '#fbbf24' : '#f87171' }}>
              {metrics.total.toFixed(0)} ms
            </span>
          </div>

          {/* Visual Gauge Bar */}
          <div style={{ background: 'rgba(255,255,255,0.05)', height: '8px', borderRadius: '4px', overflow: 'hidden', marginTop: '6px' }}>
            <div style={{
              width: `${Math.min(100, (metrics.total / 1200) * 100)}%`,
              height: '100%',
              background: metrics.total <= 450 ? 'linear-gradient(90deg, #10b981, #34d399)' : metrics.total <= 1000 ? '#f59e0b' : '#ef4444',
              boxShadow: metrics.total <= 450 ? '0 0 8px rgba(16, 185, 129, 0.4)' : 'none',
              transition: 'width 0.5s ease-in-out'
            }} />
          </div>

          <div style={{ fontSize: '9px', color: 'var(--text-muted)', textAlign: 'center', marginTop: '2px' }}>
            Target: &lt; 450ms. {metrics.total <= 450 ? '🎉 Meeting SLA requirements' : 'SLA Target Exceeded'}
          </div>
        </div>
      </section>

      {/* CONFIGURATION MODAL */}
      {showConfigModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          background: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div className="glass-card" style={{ width: '400px', padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '18px', fontWeight: '700' }}>⚙️ API Keys Setup</h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>OpenAI API Key (Whisper + GPT + TTS)</label>
              <input 
                type="password" 
                placeholder="sk-proj-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                style={{
                  background: 'rgba(0,0,0,0.2)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--border-radius-sm)',
                  padding: '8px 12px',
                  color: 'white',
                  fontSize: '12px'
                }}
              />
              <span style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
                Leave empty to run in <b>Offline Simulator Mode</b> (fully functional heuristics).
              </span>
            </div>

            <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
              <button 
                className="slot-btn" 
                style={{ flex: 1, padding: '10px', background: 'var(--primary)', color: 'white', border: 'none', fontWeight: '700' }}
                onClick={() => setShowConfigModal(false)}
              >
                Save & Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
