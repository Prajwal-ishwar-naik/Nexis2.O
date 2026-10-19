import React, { useState, useRef, useEffect } from 'react';
import {
  Plus,
  ArrowUp,
  Mic,
  ChevronDown,
  Sparkles,
  Brain,
  Check,
  X,
  FileImage,
  FileText,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';

export function InputDeck({
  onSendMessage,
  isLoading,
  onOpenVisionModal,
  activeModel = 'fast',
  onSelectModel,
  prefillPrompt = '',
  attachedImage = null,
  onClearAttachedImage,
  sessionId = 'default',
  activeChatId = null,
  onEnsureActiveChat = null,
}) {
  const [text, setText] = useState('');
  const [selectedImage, setSelectedImage] = useState(null);
  const [selectedImageName, setSelectedImageName] = useState('');
  const [uploadingDoc, setUploadingDoc] = useState(null);
  const [attachedDoc, setAttachedDoc] = useState(null);
  const [indexedDocs, setIndexedDocs] = useState([]);
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false);
  const textareaRef = useRef(null);
  const modelMenuRef = useRef(null);
  const fileInputRef = useRef(null);

  const isThinkActive = activeModel === 'deep_reasoning' || activeModel === 'deep';
  const baseTextOnStartRef = useRef('');

  const {
    isListening,
    isSupported,
    errorMessage: speechError,
    clearError: clearSpeechError,
    toggle: toggleSpeechRecognition,
    stop: stopSpeechRecognition,
  } = useSpeechRecognition({
    onTranscript: (transcript) => {
      const base = baseTextOnStartRef.current;
      const combined = base ? `${base} ${transcript}` : transcript;
      setText(combined);
    },
  });

  const handleMicClick = () => {
    if (!isListening) {
      baseTextOnStartRef.current = text.trim();
    }
    toggleSpeechRecognition();
  };

  // React to externally passed image attachment (e.g. from Sidebar or Drag & Drop)
  useEffect(() => {
    if (attachedImage) {
      if (typeof attachedImage === 'string') {
        setSelectedImage(attachedImage);
        setSelectedImageName('Attached Image');
      } else if (attachedImage instanceof File) {
        handleImageUpload(attachedImage);
      }
    }
  }, [attachedImage]);

  // React to external prompt pre-fill triggers
  useEffect(() => {
    if (prefillPrompt) {
      setText(prefillPrompt);
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
          textareaRef.current.setSelectionRange(prefillPrompt.length, prefillPrompt.length);
        }
      }, 50);
    }
  }, [prefillPrompt]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${Math.min(scrollHeight, 160)}px`;
    }
  }, [text]);

  // Click outside to close model popover
  useEffect(() => {
    function handleClickOutside(event) {
      if (modelMenuRef.current && !modelMenuRef.current.contains(event.target)) {
        setIsModelMenuOpen(false);
      }
    }
    if (isModelMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isModelMenuOpen]);

  // Convert File to clean Base64 Data URL (data:image/jpeg;base64,...) with auto-scaling to prevent pixel limit errors
  const handleImageUpload = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const MAX_DIM = 2048;
        let { width, height } = img;
        if (width > MAX_DIM || height > MAX_DIM) {
          if (width > height) {
            height = Math.round((height * MAX_DIM) / width);
            width = MAX_DIM;
          } else {
            width = Math.round((width * MAX_DIM) / height);
            height = MAX_DIM;
          }
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);
        const optimizedDataUrl = canvas.toDataURL('image/jpeg', 0.92);
        setSelectedImage(optimizedDataUrl);
        setSelectedImageName(file.name || 'image.jpg');
      };
      img.onerror = () => {
        setSelectedImage(e.target.result);
        setSelectedImageName(file.name || 'image.jpg');
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  };

  const handleClearImage = () => {
    setSelectedImage(null);
    setSelectedImageName('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    if (onClearAttachedImage) {
      onClearAttachedImage();
    }
  };

  // When file is picked:
  const handleFileUpload = async (file) => {
    if (!file) return;
    const currentChatId = (onEnsureActiveChat ? onEnsureActiveChat() : null) || activeChatId || sessionId || 'default';
    setUploadingDoc({ name: file.name, status: 'indexing' });
    setAttachedDoc({ filename: file.name, ready: false });

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('session_id', currentChatId); // MUST match chat_id passed to /api/chat

      const res = await fetch('http://127.0.0.1:8000/api/rag/upload', {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      if (res.ok && data.status === 'success') {
        const docRecord = {
          filename: file.name,
          filePath: data.file_path || file.name,
          ready: true,
          count: data.chunks_indexed,
        };
        setAttachedDoc(docRecord);
        setUploadingDoc({
          name: file.name,
          status: 'ready',
          count: data.chunks_indexed,
        });
        setIndexedDocs((prev) => [...prev, file.name]);
      } else {
        setAttachedDoc(null);
        setUploadingDoc({
          name: file.name,
          status: 'error',
          error: data.detail || 'Indexing failed',
        });
      }
    } catch (err) {
      setAttachedDoc(null);
      setUploadingDoc({
        name: file.name,
        status: 'error',
        error: err.message,
      });
    }
  };

  const handleDocumentUpload = handleFileUpload;

  const handleRemoveDoc = () => {
    setAttachedDoc(null);
    setUploadingDoc(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleFileSelection = (file) => {
    if (!file) return;
    const isImage = file.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name);
    if (isImage) {
      handleImageUpload(file);
    } else {
      handleFileUpload(file);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (isListening) {
      stopSpeechRecognition();
    }
    const trimmed = text.trim();
    if ((!trimmed && !selectedImage && !attachedDoc) || isLoading) return;

    let queryToSend = trimmed;
    if (!queryToSend && selectedImage) {
      queryToSend = 'Analyze and describe this image in detail.';
    } else if (!queryToSend && attachedDoc) {
      queryToSend = `Summarize and explain the key findings in ${attachedDoc.filename}.`;
    }

    if (isThinkActive && !queryToSend.includes('[Deep Reasoning Mode]')) {
      queryToSend = `[Deep Reasoning Mode] ${queryToSend}`;
    }

    // Capture attached document details before any state changes
    const activeDocPayload = attachedDoc ? {
      filename: attachedDoc.filename,
      filePath: attachedDoc.filePath || attachedDoc.filename,
    } : null;

    // Never send image if document is attached to avoid accidental vision token consumption
    const imageToSend = activeDocPayload ? null : selectedImage;

    onSendMessage(
      queryToSend,
      isThinkActive,
      imageToSend,
      activeDocPayload ? 'llama-3.3-70b-versatile' : (isThinkActive ? 'deep_reasoning' : 'fast'),
      activeDocPayload
    );

    // Clear text prompt and any standalone image, but preserve attachedDoc so follow-ups work
    setText('');
    if (!attachedDoc) {
      handleClearImage();
    }

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleSelectModel = (modelId) => {
    if (onSelectModel) {
      onSelectModel(modelId);
    }
    setIsModelMenuOpen(false);
  };

  return (
    <div className="w-full max-w-3xl mx-auto px-4 pb-6 relative select-none">
      {/* Floating Model Selector Popover */}
      {isModelMenuOpen && (
        <div
          ref={modelMenuRef}
          className="absolute right-6 bottom-20 z-50 w-72 bg-[#1e1f20] border border-[#2d2f31] rounded-2xl shadow-2xl p-1.5 text-xs text-[#e3e3e3] animate-fade-in-up"
        >
          <div className="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-[#8e918f] border-b border-[#282a2c] mb-1">
            Model
          </div>

          <div className="space-y-0.5">
            {/* Nexis Fast Option */}
            <button
              type="button"
              onClick={() => handleSelectModel('fast')}
              className={`w-full flex items-start gap-3 p-2 rounded-xl text-left transition-all cursor-pointer ${
                !isThinkActive
                  ? 'bg-[#282a2c] text-white'
                  : 'text-[#c4c7c5] hover:text-white hover:bg-[#282a2c]/60'
              }`}
            >
              <div className="p-1.5 rounded-lg bg-[#4da2ff]/10 border border-[#4da2ff]/20 text-[#4da2ff] shrink-0 mt-0.5">
                <Sparkles size={14} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium truncate">Nexis Fast</span>
                  {!isThinkActive && (
                    <Check size={14} className="text-[#4da2ff] shrink-0 ml-1" />
                  )}
                </div>
                <p className="text-[11px] text-[#8e918f] mt-0.5 leading-snug">
                  Llama 3.3 70B • Instant responses
                </p>
              </div>
            </button>

            {/* Nexis Deep Reasoning Option */}
            <button
              type="button"
              onClick={() => handleSelectModel('deep_reasoning')}
              className={`w-full flex items-start gap-3 p-2 rounded-xl text-left transition-all cursor-pointer ${
                isThinkActive
                  ? 'bg-[#282a2c] text-white'
                  : 'text-[#c4c7c5] hover:text-white hover:bg-[#282a2c]/60'
              }`}
            >
              <div className="p-1.5 rounded-lg bg-[#9b72cf]/10 border border-[#9b72cf]/20 text-[#9b72cf] shrink-0 mt-0.5">
                <Brain size={14} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium truncate">Nexis Deep Reasoning</span>
                  {isThinkActive && (
                    <Check size={14} className="text-[#9b72cf] shrink-0 ml-1" />
                  )}
                </div>
                <p className="text-[11px] text-[#8e918f] mt-0.5 leading-snug">
                  DeepSeek-R1 • Step-by-step thinking
                </p>
              </div>
            </button>
          </div>
        </div>
      )}

      {/* Speech Recognition Error Notice */}
      {speechError && (
        <div className="mb-2.5 flex items-center justify-between gap-2.5 px-3.5 py-2 bg-rose-950/70 border border-rose-500/40 text-rose-200 text-xs rounded-xl shadow-lg animate-fade-in-up">
          <div className="flex items-center gap-2">
            <span className="text-sm">⚠️</span>
            <p className="leading-snug">{speechError}</p>
          </div>
          <button
            type="button"
            onClick={clearSpeechError}
            className="p-1 hover:text-white rounded-full transition-colors cursor-pointer shrink-0"
            title="Dismiss notice"
          >
            <X size={13} />
          </button>
        </div>
      )}

      {/* Active Voice Listening Pill */}
      {isListening && (
        <div className="mb-2.5 flex items-center justify-between gap-3 px-3.5 py-1.5 bg-[#1e1f20] border border-rose-500/40 rounded-full w-fit max-w-sm shadow-xl animate-fade-in-up">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
            </span>
            <span className="text-xs font-medium text-rose-300">
              Listening to voice... Speak now
            </span>
          </div>
          <button
            type="button"
            onClick={stopSpeechRecognition}
            className="text-[11px] text-[#8e918f] hover:text-white underline cursor-pointer"
          >
            Done
          </button>
        </div>
      )}

      {/* Attached Image Preview Pill */}
      {selectedImage && (
        <div className="mb-2.5 flex items-center gap-3 px-3 py-2 bg-[#1e1f20] border border-[#2d2f31] rounded-2xl w-fit max-w-sm shadow-xl animate-fade-in-up">
          <div className="relative w-10 h-10 rounded-xl overflow-hidden bg-black/40 border border-[#3f4144] shrink-0 flex items-center justify-center">
            <img
              src={selectedImage}
              alt="Attached thumbnail"
              className="w-full h-full object-cover"
            />
          </div>
          <div className="flex-1 min-w-0 pr-1">
            <div className="flex items-center gap-1.5">
              <FileImage size={12} className="text-[#4da2ff] shrink-0" />
              <p className="text-xs font-medium text-[#f0f4f9] truncate">
                {selectedImageName || 'Attached Image'}
              </p>
            </div>
            <p className="text-[10px] text-[#8e918f] mt-0.5">Ready for multimodal vision inspection</p>
          </div>
          <button
            type="button"
            onClick={handleClearImage}
            className="p-1 text-[#8e918f] hover:text-white hover:bg-[#282a2c] rounded-full transition-colors cursor-pointer"
            title="Remove attachment"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Document Upload Progress / Ready Pill */}
      {uploadingDoc && (
        <div className="mb-2.5 flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-variant border border-border-subtle text-xs text-text-primary shadow-lg w-fit max-w-sm animate-fade-in-up">
          {uploadingDoc.status === 'indexing' && (
            <>
              <Loader2 size={13} className="text-[#4da2ff] animate-spin shrink-0" />
              <span className="truncate max-w-[220px] font-medium">{uploadingDoc.name}</span>
              <span className="text-[11px] text-text-muted shrink-0">(indexing...)</span>
            </>
          )}

          {uploadingDoc.status === 'ready' && (
            <>
              <span className="text-emerald-400">●</span>
              <span className="truncate max-w-[220px] font-medium">{uploadingDoc.name}</span>
              <button 
                onClick={handleRemoveDoc} 
                className="text-text-muted hover:text-text-primary transition-colors ml-1"
                aria-label="Remove document"
              >
                ×
              </button>
            </>
          )}

          {uploadingDoc.status === 'error' && (
            <>
              <span className="text-rose-400">●</span>
              <span className="truncate max-w-[220px] text-rose-300 font-medium">{uploadingDoc.name}</span>
              <button 
                onClick={handleRemoveDoc} 
                className="text-text-muted hover:text-text-primary transition-colors ml-1"
                aria-label="Remove document"
              >
                ×
              </button>
            </>
          )}
        </div>
      )}

      {/* Hidden File Input for Image & Multi-format Document Ingestion */}
      <input
        type="file"
        ref={fileInputRef}
        accept="image/*,.pdf,.docx,.pptx,.xlsx,.csv,.txt"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            handleFileSelection(file);
          }
        }}
        className="hidden"
      />

      {/* Floating Pill Input Bar */}
      <div className="relative rounded-full bg-[#1e1f20] border border-[#2d2f31] px-4 py-2.5 shadow-2xl flex items-center gap-2.5 focus-within:border-[#3f4144] transition-all">
        {/* Left Attachment Action (+) */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          title="Attach document (.pdf, .docx, .pptx, .xlsx, .csv, .txt) or image"
          className="w-8 h-8 rounded-full flex items-center justify-center text-[#c4c7c5] hover:text-white hover:bg-[#282a2c] transition-colors shrink-0 cursor-pointer"
        >
          <Plus size={18} />
        </button>

        {/* Center Textarea */}
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            selectedImage
              ? "Ask anything about this image..."
              : attachedDoc
              ? `Ask questions about ${attachedDoc.filename}...`
              : "Ask Nexis..."
          }
          disabled={isLoading}
          className="flex-1 bg-transparent text-[#f0f4f9] placeholder-[#8e918f] text-sm md:text-base outline-none resize-none max-h-[140px] leading-relaxed py-1"
        />

        {/* Right Action Group */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Model Selector Pill (Fast ▾ / Deep ▾) */}
          <button
            type="button"
            onClick={() => setIsModelMenuOpen(!isModelMenuOpen)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-all cursor-pointer ${
              isThinkActive
                ? 'bg-[#9b72cf]/20 text-[#c8a5ff] border border-[#9b72cf]/30'
                : 'text-[#c4c7c5] hover:text-[#f0f4f9] hover:bg-[#282a2c]'
            }`}
            title="Switch model engine"
          >
            <span>{isThinkActive ? 'Deep' : 'Fast'}</span>
            <ChevronDown
              size={12}
              className={`transition-transform duration-150 ${isModelMenuOpen ? 'rotate-180' : ''}`}
            />
          </button>

          {/* Voice Microphone Icon */}
          <button
            type="button"
            onClick={handleMicClick}
            className={`p-1.5 rounded-full transition-all cursor-pointer relative ${
              isListening
                ? 'bg-rose-500/20 text-rose-400 ring-2 ring-rose-500/60 animate-pulse'
                : 'text-[#8e918f] hover:text-[#f0f4f9] hover:bg-[#282a2c]'
            }`}
            title={
              isListening
                ? 'Listening... Click to stop voice input'
                : isSupported
                ? 'Use microphone for voice dictation'
                : 'Speech recognition not supported in this browser'
            }
            aria-label={isListening ? 'Stop voice dictation' : 'Start voice dictation'}
          >
            {isListening ? (
              <span className="relative flex items-center justify-center">
                <Mic size={17} className="text-rose-400" />
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-rose-500 rounded-full animate-ping" />
              </span>
            ) : (
              <Mic size={17} />
            )}
          </button>

          {/* Circular Send Arrow */}
          <button
            type="button"
            onClick={handleSubmit}
            disabled={(!text.trim() && !selectedImage) || isLoading}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
              (text.trim() || selectedImage) && !isLoading
                ? 'bg-gradient-to-tr from-[#4da2ff] to-[#9b72cf] text-white shadow-md hover:opacity-95 cursor-pointer'
                : 'text-[#8e918f] hover:text-[#c4c7c5] hover:bg-[#282a2c]'
            }`}
            title="Send message"
          >
            <ArrowUp size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
