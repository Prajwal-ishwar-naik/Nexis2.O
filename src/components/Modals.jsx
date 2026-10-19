import React, { useState } from 'react';
import {
  X,
  UploadCloud,
  FileImage,
  BookOpen,
  Cpu,
  Search,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  PhoneCall,
  BellRing,
  Clock,
} from 'lucide-react';

/**
 * Prescription & Multimodal Vision Modal
 */
export function VisionModal({ isOpen, onClose, onUploadComplete }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [sector, setSector] = useState('healthcare');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleFileChange = (e) => {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      setError(null);
      const reader = new FileReader();
      reader.onload = () => setPreview(reader.result);
      reader.readAsDataURL(selected);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('sector', sector);

    try {
      const res = await fetch('http://127.0.0.1:8000/api/vision', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        onUploadComplete(data.analysis);
        onClose();
      } else {
        setError(data.detail || 'Vision processing failed.');
      }
    } catch (err) {
      setError(err.message || 'Network error connecting to Vision ingress.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-[#1e1e1e] border border-[#333333] rounded-2xl w-full max-w-md overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-[#2e2e2e]">
          <div className="flex items-center gap-2">
            <FileImage size={18} className="text-purple-400" />
            <h2 className="text-sm font-semibold text-white">Prescription & Medical Vision</h2>
          </div>
          <button onClick={onClose} className="p-1 text-neutral-400 hover:text-white rounded-md">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <p className="text-xs text-neutral-400 leading-relaxed">
            Upload a medical prescription, diagnosis report, or clinical document for automated OCR parsing and RxNorm drug resolution.
          </p>

          <label className="border-2 border-dashed border-[#383838] hover:border-purple-500/50 rounded-xl p-6 flex flex-col items-center justify-center cursor-pointer transition-colors bg-[#181818]">
            <input type="file" accept="image/png, image/jpeg, image/webp" onChange={handleFileChange} className="hidden" />
            {preview ? (
              <img src={preview} alt="Preview" className="max-h-40 object-contain rounded-lg shadow" />
            ) : (
              <div className="flex flex-col items-center text-center">
                <UploadCloud size={32} className="text-neutral-500 mb-2" />
                <span className="text-xs text-neutral-300 font-medium">Click to upload prescription</span>
                <span className="text-[10px] text-neutral-500 mt-1">PNG, JPG, WebP up to 10MB</span>
              </div>
            )}
          </label>

          {error && (
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
              <AlertCircle size={14} className="shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={onClose}
              className="px-3 py-2 text-xs text-neutral-400 hover:text-white bg-[#282828] rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleUpload}
              disabled={!file || uploading}
              className="px-4 py-2 text-xs font-medium text-white bg-purple-600 hover:bg-purple-500 disabled:opacity-50 rounded-lg shadow transition-all"
            >
              {uploading ? 'Analyzing Prescription...' : 'Analyze Image'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * MCP Tools Registry Inspection Modal
 */
export function McpModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  const tools = [
    {
      server: 'Agri Micro-Server (8001)',
      tools: ['get_agri_mandi_prices', 'get_agri_weather_advisories'],
      description: 'Live Agmarknet arrivals, modal prices, and Open-Meteo crop advisories.',
    },
    {
      server: 'Health Micro-Server (8002)',
      tools: ['get_nearby_healthcare_facilities', 'resolve_medicine_pharmacology'],
      description: 'OpenStreetMap Overpass QL spatial queries and NIH RxNav/OpenFDA lookup.',
    },
    {
      server: 'Education Micro-Server (8003)',
      tools: ['search_academic_resources', 'search_youtube_demonstrations', 'search_live_web'],
      description: 'arXiv papers, OpenLibrary textbooks, verified YouTube tutorials, and Tavily search.',
    },
    {
      server: 'Civic Welfare Micro-Server (8004)',
      tools: ['check_civic_welfare_eligibility', 'get_civic_wiki_scheme'],
      description: 'Multi-criteria public schemes eligibility and MediaWiki Action API scheme background.',
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-[#1e1e1e] border border-[#333333] rounded-2xl w-full max-w-xl overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-[#2e2e2e]">
          <div className="flex items-center gap-2">
            <Cpu size={18} className="text-amber-400" />
            <h2 className="text-sm font-semibold text-white">Model Context Protocol (MCP) Tools Registry</h2>
          </div>
          <button onClick={onClose} className="p-1 text-neutral-400 hover:text-white rounded-md">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <p className="text-xs text-neutral-400">
            Nexis AI integrates a native Model Context Protocol layer across all 4 domain micro-servers.
          </p>

          <div className="space-y-3">
            {tools.map((item, idx) => (
              <div key={idx} className="p-3 rounded-xl bg-[#161616] border border-[#2c2c2c] space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-neutral-200">{item.server}</span>
                  <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                    Live
                  </span>
                </div>
                <p className="text-[11px] text-neutral-400">{item.description}</p>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {item.tools.map((t, tidx) => (
                    <span
                      key={tidx}
                      className="px-2 py-0.5 rounded bg-[#252525] text-amber-300 font-mono text-[10px] border border-[#3a3a3a]"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-white bg-[#2d2d2d] hover:bg-[#383838] rounded-lg transition-colors"
            >
              Close Registry
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Academic Library Search Modal
 */
export function EduModal({ isOpen, onClose, onInsertPrompt }) {
  const [query, setQuery] = useState('');

  if (!isOpen) return null;

  const handleSearch = (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    onInsertPrompt(`Search arXiv and OpenLibrary for: ${query}`);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-[#1e1e1e] border border-[#333333] rounded-2xl w-full max-w-md overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-[#2e2e2e]">
          <div className="flex items-center gap-2">
            <BookOpen size={18} className="text-blue-400" />
            <h2 className="text-sm font-semibold text-white">Academic Library & Research</h2>
          </div>
          <button onClick={onClose} className="p-1 text-neutral-400 hover:text-white rounded-md">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSearch} className="p-5 space-y-4">
          <p className="text-xs text-neutral-400">
            Query arXiv pre-prints, OpenLibrary textbook repository, and Wikipedia academic summaries.
          </p>

          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. quantum computing, compiler design..."
              className="w-full bg-[#181818] border border-[#383838] text-neutral-200 text-xs rounded-xl px-3 py-2.5 outline-none focus:border-blue-500"
              autoFocus
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-2 text-xs text-neutral-400 hover:text-white bg-[#282828] rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!query.trim()}
              className="px-4 py-2 text-xs font-medium text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg shadow transition-all"
            >
              Query Papers
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/**
 * Cluster Health Status Modal
 * Displays active ports 8000–8004 and live microservice statuses
 */
export function ClusterHealthModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  const nodes = [
    { name: 'Gateway Orchestrator', port: 8000, role: 'FastAPI Router & Dual Inference (Llama-3.3 + DeepSeek-R1)', status: 'Active' },
    { name: 'Agriculture Node', port: 8001, role: 'Agmarknet Mandi API & Open-Meteo Weather Advisories', status: 'Active' },
    { name: 'Healthcare Node', port: 8002, role: 'OSM Overpass Emergency Discovery & RxNorm Clinical OCR', status: 'Active' },
    { name: 'Education Node', port: 8003, role: 'arXiv Pre-prints, Tavily Web Search & YouTube Tutorials', status: 'Active' },
    { name: 'Civic Welfare Node', port: 8004, role: 'Public Schemes DB, MediaWiki Summaries & Eligibility Engine', status: 'Active' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in-up">
      <div className="bg-[#1e1f20] border border-[#2d2f31] rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-[#282a2c]">
          <div className="flex items-center gap-2">
            <Cpu size={18} className="text-[#4da2ff]" />
            <h2 className="text-sm font-semibold text-[#f0f4f9]">Nexis Distributed Cluster Status</h2>
          </div>
          <button onClick={onClose} className="p-1 text-[#8e918f] hover:text-white rounded-md">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-3">
          <p className="text-xs text-[#8e918f]">
            5 microservices running concurrently on local ports 8000–8004 with zero-cost open integrations.
          </p>

          <div className="space-y-2">
            {nodes.map((node, i) => (
              <div key={i} className="p-3 rounded-xl bg-[#171819] border border-[#282a2c] flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-[#e3e3e3]">{node.name}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#282a2c] text-[#4da2ff]">
                      Port {node.port}
                    </span>
                  </div>
                  <p className="text-[11px] text-[#8e918f] mt-1">{node.role}</p>
                </div>
                <div className="flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20 shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span>{node.status}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-white bg-[#282a2c] hover:bg-[#333538] rounded-xl transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * User Profile & Session Management Modal
 */
export function UserProfileModal({ isOpen, onClose, sessionCount = 0, onClearAllSessions }) {
  const [confirmClear, setConfirmClear] = useState(false);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in-up">
      <div className="bg-[#1e1f20] border border-[#2d2f31] rounded-2xl w-full max-w-sm overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-[#282a2c]">
          <h2 className="text-sm font-semibold text-[#f0f4f9]">Account & Settings</h2>
          <button onClick={onClose} className="p-1 text-[#8e918f] hover:text-white rounded-md">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-gradient-to-tr from-[#4da2ff] to-[#9b72cf] flex items-center justify-center text-white font-semibold text-lg shadow-md">
              P
            </div>
            <div>
              <div className="text-sm font-medium text-[#e3e3e3]">Prajwal Naik</div>
              <div className="text-xs text-[#8e918f]">prajwal@nexis.ai</div>
            </div>
          </div>

          <div className="p-3 rounded-xl bg-[#171819] border border-[#282a2c] flex items-center justify-between text-xs">
            <span className="text-[#8e918f]">Active Chat Sessions:</span>
            <span className="font-mono text-[#f0f4f9] font-medium">{sessionCount}</span>
          </div>

          {confirmClear ? (
            <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/25 space-y-2">
              <p className="text-xs text-red-300 font-medium">Clear all conversations?</p>
              <p className="text-[11px] text-[#8e918f]">This action will delete all saved sessions from LocalStorage.</p>
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setConfirmClear(false)}
                  className="flex-1 px-3 py-1.5 rounded-lg bg-[#282a2c] hover:bg-[#333538] text-xs text-[#c4c7c5]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onClearAllSessions();
                    setConfirmClear(false);
                    onClose();
                  }}
                  className="flex-1 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-xs text-white font-medium"
                >
                  Confirm Delete
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmClear(true)}
              className="w-full py-2 px-3 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-xl border border-red-500/20 transition-colors text-center"
            >
              Clear All Sessions
            </button>
          )}

          <div className="flex justify-end pt-1">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-[#c4c7c5] hover:text-white bg-[#282a2c] hover:bg-[#333538] rounded-xl transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Smart Voice Reminders & Scheduled Calls Modal
 */
export function VoiceRemindersModal({ isOpen, onClose, onScheduleReminder }) {
  const [reminders, setReminders] = useState([
    {
      id: 1,
      title: 'Prescription Medication Alarm',
      time: '08:00 AM (Daily)',
      type: 'Voice Call',
      status: 'Active',
      desc: 'Automated synthesis reminder for Morning Blood Pressure & Metformin dose.',
    },
    {
      id: 2,
      title: 'Kisan Mandi Price Briefing',
      time: '10:30 AM (Daily)',
      type: 'Voice Summary',
      status: 'Active',
      desc: 'Automated arrival rates for Tomato, Onion & Potato at Kolar & Bangalore mandis.',
    },
    {
      id: 3,
      title: 'UPSC / Gate Revision Audio Prompt',
      time: '06:00 PM (Mon-Fri)',
      type: 'Socratic Alarm',
      status: 'Active',
      desc: 'Interactive audio question and answer session on Polity & General Science.',
    },
  ]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in-up">
      <div className="bg-[#1e1f20] border border-[#2d2f31] rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-[#282a2c]">
          <div className="flex items-center gap-2">
            <div className="p-1 rounded-lg bg-[#9b72cf]/20 text-[#c8a5ff]">
              <PhoneCall size={16} />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-[#f0f4f9]">
                Smart Reminders & Voice Calls
              </h2>
            </div>
          </div>
          <button onClick={onClose} className="p-1 text-[#8e918f] hover:text-white rounded-md">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <p className="text-xs text-[#8e918f]">
            Schedule autonomous voice briefings, medical alarm check-ins, and agricultural advisory reminders powered by Nexis Voice Dispatcher.
          </p>

          <div className="space-y-2.5">
            {reminders.map((r) => (
              <div
                key={r.id}
                className="p-3.5 rounded-xl bg-[#171819] border border-[#282a2c] space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-[#e3e3e3]">{r.title}</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    {r.status}
                  </span>
                </div>
                <p className="text-[11px] text-[#8e918f]">{r.desc}</p>
                <div className="flex items-center gap-2 text-[10px] font-mono text-[#c4c7c5] pt-1">
                  <Clock size={11} className="text-[#4da2ff]" />
                  <span>{r.time}</span>
                  <span className="text-[#8e918f]">•</span>
                  <span className="text-[#9b72cf]">{r.type}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-[#282a2c]">
            <button
              type="button"
              onClick={() => {
                if (onScheduleReminder) {
                  onScheduleReminder('Schedule a new voice reminder for: ');
                }
                onClose();
              }}
              className="text-xs text-[#4da2ff] hover:underline font-medium cursor-pointer"
            >
              + Create custom voice alarm
            </button>

            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-white bg-[#282a2c] hover:bg-[#333538] rounded-xl transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

