import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  ExternalLink,
  RotateCw,
  Cpu,
  Layers,
  Code2,
  CheckCircle2,
  AlertCircle,
  Play,
  Copy,
  Check,
  Maximize2,
  Terminal,
} from 'lucide-react';

const SPARK_UI_URL = 'http://localhost:5174';
const SPARK_BACKEND_URL = 'http://localhost:7001';
const SPARK_WS_URL = 'ws://127.0.0.1:7001/generate-code';

export function SparkStudio({ onSwitchToAssistant }) {
  const [iframeKey, setIframeKey] = useState(0);
  const [uiStatus, setUiStatus] = useState('checking'); // 'online' | 'offline' | 'checking'
  const [backendStatus, setBackendStatus] = useState('checking'); // 'online' | 'offline' | 'checking'
  const [copiedCmd, setCopiedCmd] = useState(false);
  const iframeRef = useRef(null);

  // Periodic health check for independent Spark services (5174 and 7001)
  const checkServices = async () => {
    // Check UI (Port 5174)
    try {
      const res = await fetch(SPARK_UI_URL, { mode: 'no-cors' });
      setUiStatus('online');
    } catch {
      setUiStatus('offline');
    }

    // Check Backend (Port 7001)
    try {
      const res = await fetch(`${SPARK_BACKEND_URL}/health`, { mode: 'no-cors' });
      setBackendStatus('online');
    } catch {
      setBackendStatus('offline');
    }
  };

  useEffect(() => {
    checkServices();
    const interval = setInterval(checkServices, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = () => {
    setIframeKey((prev) => prev + 1);
    checkServices();
  };

  const handleCopyCommand = () => {
    navigator.clipboard.writeText(
      'cd spark-studio/backend && poetry run uvicorn main:app --port 7001 &\ncd ../frontend && npm run dev -- --port 5174 &'
    );
    setCopiedCmd(true);
    setTimeout(() => setCopiedCmd(false), 2000);
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#131314] overflow-hidden relative">
      {/* Studio Header Bar */}
      <div className="h-12 px-4 border-b border-[#282a2c] bg-[#1a1b1c] flex items-center justify-between shrink-0 z-10">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="p-1 rounded-lg bg-gradient-to-tr from-purple-600 to-indigo-500 text-white shadow-sm">
              <Sparkles size={14} />
            </div>
            <span className="text-xs font-semibold tracking-tight text-[#f0f4f9]">
              Spark Studio
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRefresh}
            className="p-1.5 text-[#8e918f] hover:text-[#e3e3e3] hover:bg-[#282a2c] rounded-lg transition-colors cursor-pointer"
            title="Reload sandbox"
          >
            <RotateCw size={14} />
          </button>

          <a
            href={SPARK_UI_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-[#c4c7c5] hover:text-white bg-[#282a2c] hover:bg-[#333538] rounded-lg transition-colors cursor-pointer"
            title="Open in standalone tab"
          >
            <ExternalLink size={12} />
            <span className="hidden sm:inline">Popout</span>
          </a>

          {onSwitchToAssistant && (
            <button
              type="button"
              onClick={onSwitchToAssistant}
              className="px-2.5 py-1 text-xs font-medium text-purple-300 hover:text-white bg-purple-900/30 hover:bg-purple-900/50 border border-purple-500/30 rounded-lg transition-colors cursor-pointer"
            >
              Back to Chat
            </button>
          )}
        </div>
      </div>

      {/* Main Studio Viewport */}
      <div className="flex-1 w-full h-full relative overflow-hidden bg-[#131314]">
        {/* Isolated Micro-Frontend Iframe */}
        <iframe
          key={iframeKey}
          ref={iframeRef}
          src={SPARK_UI_URL}
          title="Spark Studio Workspace"
          className="w-full h-full border-0 relative z-10 bg-transparent"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads allow-modals"
          onLoad={() => setUiStatus('online')}
        />

        {/* Offline / Startup Fallback Diagnostic Card (renders underneath iframe, visible if port 5174 hasn't bound yet) */}
        {uiStatus !== 'online' && (
          <div className="absolute inset-0 z-0 flex items-center justify-center p-6 pointer-events-auto bg-[#131314]">
            <div className="max-w-md w-full bg-[#1e1f20] border border-[#282a2c] rounded-2xl p-6 shadow-2xl space-y-4 text-center">
              <div className="w-12 h-12 mx-auto rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center text-white shadow-lg">
                <Code2 size={24} />
              </div>

              <div>
                <h3 className="text-base font-semibold text-[#f0f4f9]">
                  Spark Studio Starting Up
                </h3>
                <p className="text-xs text-[#8e918f] mt-1 leading-relaxed">
                  The studio environment is loading...
                </p>
              </div>

              <div className="bg-[#171819] border border-[#282a2c] rounded-xl p-3 text-left">
                <div className="flex items-center justify-between text-[11px] font-mono text-[#8e918f] mb-1.5">
                  <span className="flex items-center gap-1.5">
                    <Terminal size={12} className="text-purple-400" />
                    Startup Command
                  </span>
                  <button
                    onClick={handleCopyCommand}
                    className="hover:text-white transition-colors cursor-pointer flex items-center gap-1"
                  >
                    {copiedCmd ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                    <span>{copiedCmd ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>
                <pre className="text-[10px] font-mono text-purple-300 overflow-x-auto whitespace-pre leading-relaxed">
                  {`cd spark-studio/backend && poetry run uvicorn main:app --port 7001 &\ncd ../frontend && npm run dev -- --port 5174 &`}
                </pre>
              </div>

              <div className="flex items-center justify-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleRefresh}
                  className="px-4 py-2 text-xs font-medium text-white bg-purple-600 hover:bg-purple-500 rounded-xl transition-all shadow-md cursor-pointer flex items-center gap-2"
                >
                  <RotateCw size={13} />
                  <span>Check Status</span>
                </button>
                <a
                  href={SPARK_UI_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-4 py-2 text-xs font-medium text-[#c4c7c5] hover:text-white bg-[#282a2c] hover:bg-[#333538] rounded-xl transition-all cursor-pointer"
                >
                  Direct Link
                </a>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default SparkStudio;
