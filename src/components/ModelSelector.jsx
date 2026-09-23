import React, { useState, useRef, useEffect } from 'react';
import { Sparkles, Brain, ChevronDown, Check, Zap } from 'lucide-react';

const MODELS = [
  {
    id: 'fast',
    name: 'Nexis Fast',
    subtext: 'Llama 3.3 70B • Instant responses',
    icon: Zap,
    color: 'text-amber-400',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
  },
  {
    id: 'deep',
    name: 'Nexis Deep Reasoning',
    subtext: 'DeepSeek-R1 • Step-by-step logic',
    icon: Brain,
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/20',
  },
];

export function ModelSelector({ activeModel = 'fast', onSelectModel }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  const current = MODELS.find((m) => m.id === activeModel) || MODELS[0];
  const CurrentIcon = current.icon;

  // Click outside to close
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleSelect = (modelId) => {
    onSelectModel(modelId);
    setIsOpen(false);
  };

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      {/* Trigger Pill */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#262626] hover:bg-[#2d2d2d] border border-[#383838] hover:border-neutral-500 transition-all text-neutral-200 text-xs font-medium shadow-sm group"
        aria-expanded={isOpen}
        title="Select AI Orchestration Model"
      >
        <div className={`p-1 rounded-md ${current.bg}`}>
          <CurrentIcon size={14} className={current.color} />
        </div>
        <span className="font-medium text-white tracking-tight">{current.name}</span>
        <ChevronDown
          size={13}
          className={`text-neutral-400 transition-transform duration-150 ${
            isOpen ? 'rotate-180 text-white' : 'group-hover:text-neutral-200'
          }`}
        />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 top-full mt-2 w-72 bg-[#1e1e1e] border border-[#2e2e2e] rounded-xl shadow-2xl p-1.5 z-50 origin-top animate-fade-in-up">
          <div className="px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-400 border-b border-[#282828] mb-1">
            Orchestration Engine
          </div>

          <div className="space-y-1">
            {MODELS.map((model) => {
              const isSelected = model.id === activeModel;
              const Icon = model.icon;
              return (
                <button
                  key={model.id}
                  type="button"
                  onClick={() => handleSelect(model.id)}
                  className={`w-full flex items-start gap-2.5 p-2 rounded-lg text-left transition-all ${
                    isSelected
                      ? 'bg-[#282828] border border-[#383838]'
                      : 'hover:bg-[#252525] border border-transparent'
                  }`}
                >
                  <div className={`p-1.5 rounded-lg ${model.bg} ${model.border} border shrink-0 mt-0.5`}>
                    <Icon size={15} className={model.color} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-white truncate">
                        {model.name}
                      </span>
                      {isSelected && (
                        <Check size={14} className="text-emerald-400 shrink-0 ml-1" />
                      )}
                    </div>
                    <p className="text-[11px] text-neutral-400 mt-0.5 leading-snug">
                      {model.subtext}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
