import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { InputDeck } from './components/InputDeck';
import { NexisLogo } from './components/NexisLogo';
import { SparkStudio } from './components/SparkStudio';
import {
  VisionModal,
  McpModal,
  EduModal,
  ClusterHealthModal,
  UserProfileModal,
  VoiceRemindersModal,
} from './components/Modals';
import { useGeolocation } from './hooks/useGeolocation';
import { redactSensitiveIdentifiers } from './utils/redact';
import { PanelLeft } from 'lucide-react';

const GATEWAY_URL = 'http://127.0.0.1:8000';
const SESSIONS_STORAGE_KEY = 'nexis_react_sessions';
const ACTIVE_SESSION_STORAGE_KEY = 'nexis_current_session_id';
const ACTIVE_MODEL_STORAGE_KEY = 'nexis_active_model';

export default function App() {
  const { location, acquireFreshLocation, updateResolvedLocality } = useGeolocation();

  // Sessions state from LocalStorage
  const [sessions, setSessions] = useState(() => {
    try {
      const raw = localStorage.getItem(SESSIONS_STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      // Ensure all sessions conform to { id, title, createdAt, updatedAt, messages }
      return parsed.map((s) => ({
        ...s,
        createdAt: s.createdAt || Date.now(),
        updatedAt: s.updatedAt || s.createdAt || Date.now(),
        messages: s.messages || [],
      }));
    } catch {
      return [];
    }
  });

  const [currentSessionId, setCurrentSessionId] = useState(() => {
    return localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY) || null;
  });

  // Mode state: 'assistant' | 'spark'
  const [activeMode, setActiveMode] = useState('assistant');

  // Active Model State: 'fast' | 'deep'
  const [activeModel, setActiveModel] = useState(() => {
    return localStorage.getItem(ACTIVE_MODEL_STORAGE_KEY) || 'fast';
  });

  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Modals state
  const [isVisionModalOpen, setIsVisionModalOpen] = useState(false);
  const [isEduModalOpen, setIsEduModalOpen] = useState(false);
  const [isMcpModalOpen, setIsMcpModalOpen] = useState(false);
  const [isClusterModalOpen, setIsClusterModalOpen] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [isVoiceModalOpen, setIsVoiceModalOpen] = useState(false);

  // Prompt pre-fill state (e.g. from Sidebar 'Videos')
  const [prefillPrompt, setPrefillPrompt] = useState('');

  // Attached image state for InputDeck from Sidebar/external triggers
  const [attachedImageForInput, setAttachedImageForInput] = useState(null);

  // Mode / Model synchronization
  const handleSelectMode = (mode) => {
    setActiveMode(mode);
    if (mode === 'spark') {
      setActiveModel('deep');
    } else {
      setActiveModel('fast');
    }
  };

  const handleSelectModel = (model) => {
    setActiveModel(model);
    if (model === 'deep') {
      setActiveMode('spark');
    } else {
      setActiveMode('assistant');
    }
  };

  // Clear all sessions action
  const handleClearAllSessions = () => {
    setSessions([]);
    setCurrentSessionId(null);
    try {
      localStorage.removeItem(SESSIONS_STORAGE_KEY);
      localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
    } catch (e) {
      console.error('Failed clearing sessions:', e);
    }
  };

  // Sync sessions to LocalStorage
  useEffect(() => {
    try {
      localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify(sessions));
    } catch (e) {
      console.error('Failed saving sessions to LocalStorage:', e);
    }
  }, [sessions]);

  // Sync currentSessionId to LocalStorage
  useEffect(() => {
    if (currentSessionId) {
      localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, currentSessionId);
    } else {
      localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
    }
  }, [currentSessionId]);

  // Sync activeModel to LocalStorage
  useEffect(() => {
    try {
      localStorage.setItem(ACTIVE_MODEL_STORAGE_KEY, activeModel);
    } catch (e) {
      console.error('Failed saving active model to LocalStorage:', e);
    }
  }, [activeModel]);

  // Current session object
  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const messages = currentSession?.messages || [];

  // Create a new session
  const handleNewChat = () => {
    const newSession = {
      id: `session_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
      title: '',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
    };
    setSessions((prev) => [newSession, ...prev]);
    setCurrentSessionId(newSession.id);
    if (window.innerWidth < 1024) {
      setIsSidebarOpen(false);
    }
  };

  // Rename a session
  const handleRenameSession = (idToRename, newTitle) => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === idToRename
          ? { ...s, title: newTitle, updatedAt: Date.now() }
          : s
      )
    );
  };

  // Duplicate a session
  const handleDuplicateSession = (idToDuplicate) => {
    const original = sessions.find((s) => s.id === idToDuplicate);
    if (!original) return;
    const cloned = {
      ...original,
      id: `session_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
      title: `${original.title || 'Untitled Session'} (Copy)`,
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [...original.messages],
    };
    setSessions((prev) => [cloned, ...prev]);
    setCurrentSessionId(cloned.id);
  };

  // Delete a session
  const handleDeleteSession = (idToDelete) => {
    setSessions((prev) => prev.filter((s) => s.id !== idToDelete));
    if (currentSessionId === idToDelete) {
      const remaining = sessions.filter((s) => s.id !== idToDelete);
      setCurrentSessionId(remaining.length > 0 ? remaining[0].id : null);
    }
  };

  // Dispatch message to Gateway orchestrator
  const handleSendMessage = async (rawQuery, isDeepThink = false, imageBase64 = null) => {
    let sanitizedQuery = rawQuery ? redactSensitiveIdentifiers(rawQuery.trim()) : '';
    if (!sanitizedQuery && imageBase64) {
      sanitizedQuery = 'Inspect and analyze this image in detail.';
    }
    if (!sanitizedQuery && !imageBase64) return;

    const deepThinkActive = Boolean(
      isDeepThink ||
      activeMode === 'spark' ||
      activeModel === 'deep' ||
      sanitizedQuery.includes('[Deep Reasoning Mode]')
    );

    let targetSessionId = currentSessionId;
    let currentSess = sessions.find((s) => s.id === targetSessionId);

    // Auto-create session if none active
    if (!targetSessionId || !currentSess) {
      const newSession = {
        id: `session_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
        title: sanitizedQuery.slice(0, 32) + (sanitizedQuery.length > 32 ? '...' : ''),
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [],
      };
      setSessions((prev) => [newSession, ...prev]);
      setCurrentSessionId(newSession.id);
      targetSessionId = newSession.id;
      currentSess = newSession;
    }

    // Add user message to session (with image preview data URI if attached)
    const userMessage = {
      role: 'user',
      content: sanitizedQuery,
      image: imageBase64 || null,
      timestamp: Date.now(),
    };

    setSessions((prev) =>
      prev.map((s) => {
        if (s.id === targetSessionId) {
          const updatedTitle = s.title || (sanitizedQuery.slice(0, 32) + (sanitizedQuery.length > 32 ? '...' : ''));
          return {
            ...s,
            title: updatedTitle,
            updatedAt: Date.now(),
            messages: [...s.messages, userMessage],
          };
        }
        return s;
      })
    );

    setIsLoading(true);

    // Acquire fresh hardware coordinates on interaction (with 2.5s maximum wait)
    let activeLat = location.lat;
    let activeLon = location.lon;
    try {
      const fresh = await Promise.race([
        acquireFreshLocation(2500),
        new Promise((r) => setTimeout(() => r(null), 2500)),
      ]);
      if (fresh && fresh.lat !== null) {
        activeLat = fresh.lat;
        activeLon = fresh.lon;
      }
    } catch (e) {
      console.warn('Interactive geolocation check warning:', e);
    }

    // Call Gateway /api/chat with query and optional image_base64
    try {
      const res = await fetch(`${GATEWAY_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: sanitizedQuery,
          image_base64: imageBase64 || null,
          session_id: targetSessionId,
          lat: activeLat,
          lon: activeLon,
          deep_think: deepThinkActive,
        }),
      });

      const data = await res.json();
      setIsLoading(false);

      if (res.ok && data.status === 'success') {
        // Update locality if resolved by reverse-geocoding pipeline
        if (data.resolved_location && data.resolved_location.formatted) {
          updateResolvedLocality(data.resolved_location.locality || data.resolved_location.formatted);
        }

        const assistantReply = redactSensitiveIdentifiers(data.response);
        const toolsExecuted = data.tools_executed || [];

        const assistantMessage = {
          role: 'assistant',
          content: assistantReply,
          toolsExecuted: toolsExecuted,
          timestamp: Date.now(),
        };

        setSessions((prev) =>
          prev.map((s) =>
            s.id === targetSessionId
              ? { ...s, updatedAt: Date.now(), messages: [...s.messages, assistantMessage] }
              : s
          )
        );
      } else {
        const errorText = data.detail || 'Gateway processing error.';
        const assistantMessage = {
          role: 'assistant',
          content: `⚠️ **Error communicating with Nexis Gateway:** ${errorText}\n\n*Please ensure all backend microservices are active on localhost.*`,
          toolsExecuted: [],
          timestamp: Date.now(),
        };

        setSessions((prev) =>
          prev.map((s) =>
            s.id === targetSessionId
              ? { ...s, updatedAt: Date.now(), messages: [...s.messages, assistantMessage] }
              : s
          )
        );
      }
    } catch (err) {
      setIsLoading(false);
      const assistantMessage = {
        role: 'assistant',
        content: `⚠️ **Connection Offline:** Could not connect to \`${GATEWAY_URL}/api/chat\`.\n\n*Error: ${err.message}. Ensure cluster is running via \`./start_servers.sh\`.*`,
        toolsExecuted: [],
        timestamp: Date.now(),
      };

      setSessions((prev) =>
        prev.map((s) =>
          s.id === targetSessionId
            ? { ...s, updatedAt: Date.now(), messages: [...s.messages, assistantMessage] }
            : s
        )
      );
    }
  };

  // Vision Analysis Callback
  const handleVisionComplete = (analysisData) => {
    const summary = `**Prescription OCR & Vision Report:**\n\n` +
      `* **Extracted Text:** ${analysisData.extracted_text || 'Completed'}\n` +
      `* **Resolved Medication:** ${analysisData.resolved_medication || 'Processed'}\n` +
      `* **Clinical Summary:** ${analysisData.clinical_summary || 'Analysis complete.'}`;
    handleSendMessage(summary);
  };

  return (
    <div
      className="flex h-screen w-screen overflow-hidden text-[#e3e3e3] font-sans relative"
      style={{
        backgroundColor: '#131314',
        backgroundImage: 'radial-gradient(circle at 50% 65%, rgba(20, 35, 60, 0.35) 0%, #131314 70%)',
      }}
    >
      {/* Collapsible Sidebar */}
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={(id) => {
          setCurrentSessionId(id);
          if (window.innerWidth < 1024) {
            setIsSidebarOpen(false);
          }
        }}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        onRenameSession={handleRenameSession}
        onDuplicateSession={handleDuplicateSession}
        onOpenVisionModal={(file) => {
          if (file) {
            const reader = new FileReader();
            reader.onload = () => setAttachedImageForInput(reader.result);
            reader.readAsDataURL(file);
          } else {
            setIsVisionModalOpen(true);
          }
        }}
        onOpenEduModal={() => setIsEduModalOpen(true)}
        onOpenMcpModal={() => setIsMcpModalOpen(true)}
        onOpenClusterModal={() => setIsClusterModalOpen(true)}
        onOpenProfileModal={() => setIsProfileModalOpen(true)}
        onOpenVoiceModal={() => setIsVoiceModalOpen(true)}
        onPrefillPrompt={(text) => {
          setPrefillPrompt(text);
          setTimeout(() => setPrefillPrompt(''), 300);
        }}
        location={location}
        isOpen={isSidebarOpen}
        onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        activeMode={activeMode}
        onSelectMode={handleSelectMode}
        onSwitchProfile={() => handleNewChat()}
      />

      {/* Main Canvas & Input Deck */}
      <main className="flex-1 flex flex-col h-full relative overflow-hidden bg-transparent">
        {/* Top Navbar */}
        <header className="h-14 border-b border-[#282a2c]/60 bg-[#131314]/40 backdrop-blur-md flex items-center justify-between px-4 z-10">
          <div className="flex items-center gap-2.5">
            {!isSidebarOpen && (
              <button
                type="button"
                onClick={() => setIsSidebarOpen(true)}
                className="p-1.5 text-[#8e918f] hover:text-[#e3e3e3] hover:bg-[#282a2c] rounded-lg transition-colors cursor-pointer"
                title="Open sidebar"
              >
                <PanelLeft size={18} />
              </button>
            )}

            <div className="flex items-center gap-2">
              <NexisLogo size={20} glow />
              <span className="font-semibold text-base tracking-tight text-[#e3e3e3]">Nexis</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleNewChat}
              className="px-3.5 py-1.5 text-xs font-normal text-[#c4c7c5] hover:text-[#f0f4f9] hover:bg-[#282a2c] rounded-full border border-[#282a2c] transition-colors cursor-pointer"
            >
              New chat
            </button>
          </div>
        </header>

        {/* Dynamic Center Canvas: Core Chat Engine vs Spark Studio Workspace */}
        {activeMode === 'assistant' ? (
          <>
            {/* Chat Area Message Feed */}
            <ChatArea
              messages={messages}
              isLoading={isLoading}
              onSelectSuggestion={(prompt) => handleSendMessage(prompt)}
            />

            {/* Gemini-Style Floating Pill Input Deck */}
            <InputDeck
              onSendMessage={handleSendMessage}
              isLoading={isLoading}
              onOpenVisionModal={() => setIsVisionModalOpen(true)}
              activeModel={activeModel}
              onSelectModel={handleSelectModel}
              prefillPrompt={prefillPrompt}
              attachedImage={attachedImageForInput}
              onClearAttachedImage={() => setAttachedImageForInput(null)}
            />
          </>
        ) : (
          <SparkStudio onSwitchToAssistant={() => handleSelectMode('assistant')} />
        )}
      </main>

      {/* Modals */}
      <VisionModal
        isOpen={isVisionModalOpen}
        onClose={() => setIsVisionModalOpen(false)}
        onUploadComplete={handleVisionComplete}
      />

      <EduModal
        isOpen={isEduModalOpen}
        onClose={() => setIsEduModalOpen(false)}
        onInsertPrompt={(query) => handleSendMessage(query)}
      />

      <McpModal
        isOpen={isMcpModalOpen}
        onClose={() => setIsMcpModalOpen(false)}
      />

      <ClusterHealthModal
        isOpen={isClusterModalOpen}
        onClose={() => setIsClusterModalOpen(false)}
      />

      <UserProfileModal
        isOpen={isProfileModalOpen}
        onClose={() => setIsProfileModalOpen(false)}
        sessionCount={sessions.length}
        onClearAllSessions={handleClearAllSessions}
      />

      <VoiceRemindersModal
        isOpen={isVoiceModalOpen}
        onClose={() => setIsVoiceModalOpen(false)}
        onScheduleReminder={(text) => handleSendMessage(text)}
      />
    </div>
  );
}
