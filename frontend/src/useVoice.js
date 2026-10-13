import { useCallback, useEffect, useRef, useState } from 'react';

// Two ways to capture speech:
// 1. "browser": the Web Speech API transcribes on device (Chrome, Edge, Safari) and we send text.
// 2. "upload": record audio with MediaRecorder and let Gemini transcribe and extract on the server.
// Mode is chosen at runtime from what the browser and server support.

function getRecognition() {
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export function detectVoiceMode(serverAudio) {
  if (getRecognition()) return 'browser';
  if (serverAudio && typeof window !== 'undefined' && window.MediaRecorder && navigator.mediaDevices) return 'upload';
  return 'none';
}

export function useVoice({ mode, onText, onAudio, onError }) {
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => () => recRef.current?.stop?.(), []);

  const start = useCallback(async () => {
    if (mode === 'browser') {
      const Recognition = getRecognition();
      const rec = new Recognition();
      rec.lang = 'id-ID';
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onresult = (e) => onText(e.results[0][0].transcript);
      rec.onerror = (e) => onError(e.error === 'not-allowed' ? 'Izin mikrofon ditolak.' : 'Suara tidak tertangkap. Coba lagi.');
      rec.onend = () => setListening(false);
      recRef.current = rec;
      rec.start();
      setListening(true);
    } else if (mode === 'upload') {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const recorder = new MediaRecorder(stream);
        chunksRef.current = [];
        recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
        recorder.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          setListening(false);
          onAudio(new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' }));
        };
        recRef.current = recorder;
        recorder.start();
        setListening(true);
      } catch {
        onError('Izin mikrofon ditolak.');
      }
    }
  }, [mode, onText, onAudio, onError]);

  const stop = useCallback(() => {
    recRef.current?.stop();
  }, []);

  return { listening, start, stop };
}
