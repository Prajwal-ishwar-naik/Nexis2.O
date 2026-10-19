import { useState, useRef, useEffect, useCallback } from 'react';

/**
 * Custom React hook for Web Speech Recognition.
 * Supports cross-browser prefixing (window.SpeechRecognition || window.webkitSpeechRecognition),
 * graceful permission and error handling, interim streaming transcripts, and clean lifecycle teardown.
 */
export function useSpeechRecognition({ onTranscript, onError } = {}) {
  const [isListening, setIsListening] = useState(false);
  const [isSupported, setIsSupported] = useState(true);
  const [errorMessage, setErrorMessage] = useState(null);
  const recognitionRef = useRef(null);
  const isListeningRef = useRef(false);

  // Validate browser support on mount
  useEffect(() => {
    const SpeechRecognition =
      typeof window !== 'undefined'
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : null;

    if (!SpeechRecognition) {
      setIsSupported(false);
    }
  }, []);

  const stop = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (e) {
        // Safe ignore if recognition is already stopped
      }
    }
    setIsListening(false);
    isListeningRef.current = false;
  }, []);

  const start = useCallback(() => {
    setErrorMessage(null);

    const SpeechRecognition =
      typeof window !== 'undefined'
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : null;

    if (!SpeechRecognition) {
      const msg = 'Speech recognition is not supported in this browser. Please use Google Chrome or Microsoft Edge.';
      setErrorMessage(msg);
      if (onError) onError(msg);
      return;
    }

    // Abort existing instance if active
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch (e) {}
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListening(true);
        isListeningRef.current = true;
      };

      recognition.onresult = (event) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = 0; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            finalTranscript += result[0].transcript;
          } else {
            interimTranscript += result[0].transcript;
          }
        }

        const combinedTranscript = (finalTranscript + interimTranscript).trim();
        if (onTranscript) {
          onTranscript(combinedTranscript, {
            final: finalTranscript.trim(),
            interim: interimTranscript.trim(),
            isFinal: event.results[event.results.length - 1]?.isFinal || false,
          });
        }
      };

      recognition.onerror = (event) => {
        console.warn('SpeechRecognition error:', event.error);
        let userMessage = null;

        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
          userMessage = 'Microphone access denied. Please allow microphone permissions in your browser address bar.';
        } else if (event.error === 'no-speech') {
          // Normal timeout when silence is encountered
          return;
        } else if (event.error === 'network') {
          userMessage = 'Speech recognition network error. Please verify your internet connection.';
        } else if (event.error === 'audio-capture') {
          userMessage = 'No microphone detected or microphone is in use by another application.';
        } else if (event.error !== 'already-started') {
          userMessage = `Speech recognition notice: ${event.error}`;
        }

        if (userMessage) {
          setErrorMessage(userMessage);
          if (onError) onError(userMessage);
        }
        setIsListening(false);
        isListeningRef.current = false;
      };

      recognition.onend = () => {
        setIsListening(false);
        isListeningRef.current = false;
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      console.error('Failed to initialize speech recognition:', err);
      const msg = err.name === 'InvalidStateError' ? null : 'Unable to start microphone recording.';
      if (msg) {
        setErrorMessage(msg);
        if (onError) onError(msg);
      }
      setIsListening(false);
      isListeningRef.current = false;
    }
  }, [onTranscript, onError]);

  const toggle = useCallback(() => {
    if (isListeningRef.current) {
      stop();
    } else {
      start();
    }
  }, [start, stop]);

  // Cleanup on component unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch (e) {}
      }
    };
  }, []);

  return {
    isListening,
    isSupported,
    errorMessage,
    clearError: () => setErrorMessage(null),
    start,
    stop,
    toggle,
  };
}
