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
} from 'lucide-react';

export function InputDeck({
  onSendMessage,
  isLoading,
  onOpenVisionModal,
  activeModel = 'fast',
  onSelectModel,
  prefillPrompt = '',
  attachedImage = null,
  onClearAttachedImage,
}) {
  const [text, setText] = useState('');
  const [selectedImageBase64, setSelectedImageBase64] = useState(null);
  const [selectedImageName, setSelectedImageName] = useState('');
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false);
  const textareaRef = useRef(null);
  const modelMenuRef = useRef(null);
  const fileInputRef = useRef(null);

  const isThinkActive = activeModel === 'deep';

  // React to externally passed image attachment (e.g. from Sidebar or Drag & Drop)
  useEffect(() => {
    if (attachedImage) {
      if (typeof attachedImage === 'string') {
        setSelectedImageBase64(attachedImage);
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

  // Convert File to clean Base64 Data URI
  const handleImageUpload = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onloadend = () => {
      setSelectedImageBase64(reader.result);
      setSelectedImageName(file.name || 'image.png');
    };
    reader.readAsDataURL(file);
  };

  const handleClearImage = () => {
    setSelectedImageBase64(null);
    setSelectedImageName('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    if (onClearAttachedImage) {
      onClearAttachedImage();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    const trimmed = text.trim();
    if ((!trimmed && !selectedImageBase64) || isLoading) return;

    let queryToSend = trimmed;
    if (!queryToSend && selectedImageBase64) {
      queryToSend = 'Inspect and analyze this image in detail.';
    }

    if (isThinkActive && !queryToSend.includes('[Deep Reasoning Mode]')) {
      queryToSend = `[Deep Reasoning Mode] ${queryToSend}`;
    }

    onSendMessage(queryToSend, isThinkActive, selectedImageBase64);
    setText('');
    handleClearImage();

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
              onClick={() => handleSelectModel('deep')}
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

      {/* Attached Image Preview Pill */}
      {selectedImageBase64 && (
        <div className="mb-2.5 flex items-center gap-3 px-3 py-2 bg-[#1e1f20] border border-[#2d2f31] rounded-2xl w-fit max-w-sm shadow-xl animate-fade-in-up">
          <div className="relative w-10 h-10 rounded-xl overflow-hidden bg-black/40 border border-[#3f4144] shrink-0 flex items-center justify-center">
            <img
              src={selectedImageBase64}
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

      {/* Hidden File Input for Native Image Ingestion */}
      <input
        type="file"
        ref={fileInputRef}
        accept="image/*"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            handleImageUpload(file);
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
          title="Attach image for vision inspection"
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
          placeholder={selectedImageBase64 ? "Ask anything about this image..." : "Ask Nexis..."}
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
            className="p-1.5 text-[#8e918f] hover:text-[#f0f4f9] hover:bg-[#282a2c] rounded-full transition-colors cursor-pointer"
            title="Use microphone"
          >
            <Mic size={17} />
          </button>

          {/* Circular Send Arrow */}
          <button
            type="button"
            onClick={handleSubmit}
            disabled={(!text.trim() && !selectedImageBase64) || isLoading}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
              (text.trim() || selectedImageBase64) && !isLoading
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
