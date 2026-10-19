import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { InputDeck } from './components/InputDeck';
import { NexisLogo } from './components/NexisLogo';
import { SparkStudio } from './components/SparkStudio';
import { ModelSelector } from './components/ModelSelector';
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
const PROFILES_STORAGE_KEY = 'nexis_user_profiles';
const ACTIVE_SESSION_STORAGE_KEY = 'nexis_active_session_id';
const ACTIVE_CHAT_STORAGE_KEY = 'nexis_active_chat_id';
const ACTIVE_MODEL_STORAGE_KEY = 'nexis_active_model';

const DEFAULT_SESSION_PROFILES = [
  { id: '1', name: 'Prajwal Naik', initial: 'P', active: true },
  { id: '2', name: 'Academic Research', initial: 'A', active: false },
];

export default function App() {
  const { location, acquireFreshLocation, updateResolvedLocality } = useGeolocation();

  // 1. Session Profiles (Workspaces)
  const [sessionProfiles, setSessionProfiles] = useState(() => {
    try {
      const raw = localStorage.getItem(PROFILES_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed;
        }
      }
    } catch (e) {
      console.error('Failed reading session profiles:', e);
    }
    return DEFAULT_SESSION_PROFILES;
  });

  // 2. Active Session ID
  const [activeSessionId, setActiveSessionId] = useState(() => {
    try {
      const saved = localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
      if (saved) return saved;
      const rawProfiles = localStorage.getItem(PROFILES_STORAGE_KEY);
      if (rawProfiles) {
        const parsed = JSON.parse(rawProfiles);
        const active = parsed.find((p) => p.active);
        if (active) return active.id;
        if (parsed[0]) return parsed[0].id;
      }
    } catch {}
    return '1';
  });

  // 3. All Chats (Parent-Child Hierarchy: each chat strictly belongs to a sessionId)
  const [allChats, setAllChats] = useState(() => {
    try {
      const raw = localStorage.getItem(SESSIONS_STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.map((c) => ({
        id: c.id || `chat_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
        sessionId: c.sessionId || '1', // Ensure legacy chats belong to session '1'
        title: c.title || 'New chat',
        messages: Array.isArray(c.messages) ? c.messages : [],
        createdAt: c.createdAt || Date.now(),
        updatedAt: c.updatedAt || c.createdAt || Date.now(),
      }));
    } catch {
      return [];
    }
  });

  // 4. Active Chat ID
  const [activeChatId, setActiveChatId] = useState(() => {
    try {
      return localStorage.getItem(ACTIVE_CHAT_STORAGE_KEY) || null;
    } catch {
      return null;
    }
  });

  // Mode state: 'assistant' | 'spark'
  const [activeMode, setActiveMode] = useState('assistant');

  // Active Model State: 'fast' | 'deep_reasoning'
  const [activeModel, setActiveModel] = useState(() => {
    const saved = localStorage.getItem(ACTIVE_MODEL_STORAGE_KEY);
    if (saved === 'deep') return 'deep_reasoning';
    return saved || 'fast';
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
  };

  const handleSelectModel = (model) => {
    const normalizedModel = model === 'deep' ? 'deep_reasoning' : model;
    setActiveModel(normalizedModel);
    // Explicitly maintain primary chat canvas session: do NOT switch activeMode or navigate away
  };

  // Derive active chat strictly scoped to the active session
  const activeChat =
    allChats.find((c) => c.id === activeChatId && c.sessionId === activeSessionId) ||
    allChats.filter((c) => c.sessionId === activeSessionId)[0] ||
    null;

  const messages = activeChat?.messages || [];

  // Helper to ensure an active chat exists and return its ID
  const ensureActiveChatId = () => {
    if (activeChatId && allChats.some((c) => c.id === activeChatId && c.sessionId === activeSessionId)) {
      return activeChatId;
    }
    const existing = allChats.find((c) => c.sessionId === activeSessionId);
    if (existing) {
      setActiveChatId(existing.id);
      return existing.id;
    }
    const newId = `chat_${Date.now()}`;
    const newChat = {
      id: newId,
      sessionId: activeSessionId || '1',
      title: 'New chat',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    setAllChats((prev) => [newChat, ...prev]);
    setActiveChatId(newId);
    return newId;
  };

  // Keep activeChatId aligned with activeChat if fallback occurred or initialize if missing
  useEffect(() => {
    if (activeChat && activeChat.id !== activeChatId) {
      setActiveChatId(activeChat.id);
    } else if (!activeChatId) {
      ensureActiveChatId();
    }
  }, [activeChat, activeChatId, activeSessionId]);

  // Sync allChats to LocalStorage (nexis_react_sessions)
  useEffect(() => {
    try {
      localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify(allChats));
    } catch (e) {
      console.error('Failed saving chats to LocalStorage:', e);
    }
  }, [allChats]);

  // Sync activeSessionId to LocalStorage
  useEffect(() => {
    try {
      if (activeSessionId) {
        localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, activeSessionId);
      }
    } catch (e) {
      console.error('Failed saving active session to LocalStorage:', e);
    }
  }, [activeSessionId]);

  // Sync activeChatId to LocalStorage
  useEffect(() => {
    try {
      if (activeChatId) {
        localStorage.setItem(ACTIVE_CHAT_STORAGE_KEY, activeChatId);
      } else {
        localStorage.removeItem(ACTIVE_CHAT_STORAGE_KEY);
      }
    } catch (e) {
      console.error('Failed saving active chat to LocalStorage:', e);
    }
  }, [activeChatId]);

  // Sync sessionProfiles to LocalStorage
  useEffect(() => {
    try {
      localStorage.setItem(PROFILES_STORAGE_KEY, JSON.stringify(sessionProfiles));
    } catch (e) {
      console.error('Failed saving session profiles to LocalStorage:', e);
    }
  }, [sessionProfiles]);

  // Sync activeModel to LocalStorage
  useEffect(() => {
    try {
      localStorage.setItem(ACTIVE_MODEL_STORAGE_KEY, activeModel);
    } catch (e) {
      console.error('Failed saving active model to LocalStorage:', e);
    }
  }, [activeModel]);

  // Clear all chats action
  const handleClearAllSessions = () => {
    setAllChats([]);
    setActiveChatId(null);
    try {
      localStorage.removeItem(SESSIONS_STORAGE_KEY);
      localStorage.removeItem(ACTIVE_CHAT_STORAGE_KEY);
    } catch (e) {
      console.error('Failed clearing chats:', e);
    }
  };

  // Backend session synchronization
  const loadSessionMessages = async (chatId) => {
    if (!chatId) return;
    try {
      const res = await fetch(`${GATEWAY_URL}/api/sessions/${chatId}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.status === 'success' && data.session && Array.isArray(data.session.messages)) {
        const formattedMessages = data.session.messages.map((m) => ({
          role: m.role,
          content: m.content,
          thought_trace: m.thought_trace || null,
          toolsExecuted: m.tool_calls || [],
          timestamp: m.timestamp ? new Date(m.timestamp).getTime() : Date.now(),
        }));
        setAllChats((prev) =>
          prev.map((c) =>
            c.id === chatId
              ? {
                  ...c,
                  title: data.session.title || c.title,
                  messages: formattedMessages.length > 0 ? formattedMessages : c.messages,
                }
              : c
          )
        );
      }
    } catch (err) {
      console.warn(`Failed to fetch messages for chat ${chatId}:`, err);
    }
  };

  // Sync sessions list from backend on mount
  useEffect(() => {
    let isMounted = true;
    const syncSessions = async () => {
      try {
        const res = await fetch(`${GATEWAY_URL}/api/sessions`);
        if (!res.ok) return;
        const data = await res.json();
        if (!isMounted || data.status !== 'success' || !Array.isArray(data.sessions)) return;

        setAllChats((prevChats) => {
          const prevMap = new Map(prevChats.map((c) => [c.id, c]));
          const merged = [...prevChats];

          for (const rem of data.sessions) {
            if (!prevMap.has(rem.session_id)) {
              merged.push({
                id: rem.session_id,
                sessionId: rem.user_session_id || '1',
                title: rem.title || 'Untitled Chat',
                createdAt: rem.created_at ? new Date(rem.created_at).getTime() : Date.now(),
                updatedAt: rem.updated_at ? new Date(rem.updated_at).getTime() : Date.now(),
                messages: [],
              });
            } else {
              const existing = prevMap.get(rem.session_id);
              if (!existing.title && rem.title) {
                existing.title = rem.title;
              }
            }
          }
          merged.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
          return merged;
        });

        // Hydrate active chat if it exists but messages are empty
        if (activeChatId) {
          const currentActive = allChats.find((c) => c.id === activeChatId);
          if (!currentActive || !currentActive.messages || currentActive.messages.length === 0) {
            loadSessionMessages(activeChatId);
          }
        }
      } catch (err) {
        console.warn('Failed to sync sessions from backend:', err);
      }
    };
    syncSessions();
    return () => {
      isMounted = false;
    };
  }, []);

  // Handle switching sessions from the dropdown / modal
  const handleSwitchSession = (targetSessionId) => {
    if (targetSessionId === activeSessionId) return;

    // 1. Update activeSessionId
    setActiveSessionId(targetSessionId);

    // Update active flag in sessionProfiles
    setSessionProfiles((prev) =>
      prev.map((p) => ({
        ...p,
        active: p.id === targetSessionId,
      }))
    );

    // 2. Find the most recent chat belonging to this selected session
    const sessionChats = allChats.filter((c) => c.sessionId === targetSessionId);
    const lastChat = sessionChats[0];

    // 3. If a chat exists, load it as activeChatId. If no chats exist for this session yet, create a fresh empty chat.
    if (lastChat) {
      setActiveChatId(lastChat.id);
      if (!lastChat.messages || lastChat.messages.length === 0) {
        loadSessionMessages(lastChat.id);
      }
    } else {
      const newChatId = `chat_${Date.now()}`;
      const freshChat = {
        id: newChatId,
        sessionId: targetSessionId,
        title: 'New chat',
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
      };
      setAllChats((prev) => [freshChat, ...prev]);
      setActiveChatId(newChatId);
    }

    // 4. Ensure UI canvas renders only the messages of the active chat
    if (window.innerWidth < 1024) {
      setIsSidebarOpen(false);
    }
  };

  // Handle "+ Add New Session"
  const handleAddNewSession = (customName) => {
    // 1. Create a new session with a unique sessionId
    const newSessionId = `session_${Date.now()}`;
    const sessionName = customName?.trim() || `Session ${sessionProfiles.length + 1}`;
    const initial = sessionName.charAt(0).toUpperCase() || 'S';

    const newProfile = {
      id: newSessionId,
      name: sessionName,
      initial: initial,
      active: true,
    };

    setSessionProfiles((prev) => [
      ...prev.map((p) => ({ ...p, active: false })),
      newProfile,
    ]);

    // 2. Set activeSessionId = newSession.id
    setActiveSessionId(newSessionId);

    // 3. Automatically create one fresh, empty chat for this new session and set it as activeChatId
    const freshChatId = `chat_${Date.now()}`;
    const freshChat = {
      id: freshChatId,
      sessionId: newSessionId,
      title: 'New chat',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    setAllChats((prev) => [freshChat, ...prev]);
    setActiveChatId(freshChatId);

    // 4. Clear the active conversation canvas so no old messages persist
    if (window.innerWidth < 1024) {
      setIsSidebarOpen(false);
    }
  };

  // Handle "+ New Chat" inside existing session
  const handleNewChat = () => {
    // 1. Create a new chat tied specifically to the current activeSessionId
    const newChatId = `chat_${Date.now()}`;
    const newChat = {
      id: newChatId,
      sessionId: activeSessionId,
      title: 'New chat',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    // 2. Switch view to this new empty chat
    setAllChats((prev) => [newChat, ...prev]);
    setActiveChatId(newChatId);

    if (window.innerWidth < 1024) {
      setIsSidebarOpen(false);
    }
  };

  // Handle chat selection
  const handleSelectChat = (chatId) => {
    setActiveChatId(chatId);
    const target = allChats.find((c) => c.id === chatId);
    if (target && (!target.messages || target.messages.length === 0)) {
      loadSessionMessages(chatId);
    }
    if (window.innerWidth < 1024) {
      setIsSidebarOpen(false);
    }
  };

  // Rename a chat
  const handleRenameChat = (chatIdToRename, newTitle) => {
    setAllChats((prev) =>
      prev.map((c) =>
        c.id === chatIdToRename
          ? { ...c, title: newTitle, updatedAt: Date.now() }
          : c
      )
    );
  };

  // Duplicate a chat
  const handleDuplicateChat = (chatIdToDuplicate) => {
    const original = allChats.find((c) => c.id === chatIdToDuplicate);
    if (!original) return;
    const cloned = {
      ...original,
      id: `chat_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
      title: `${original.title || 'New chat'} (Copy)`,
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [...original.messages],
    };
    setAllChats((prev) => [cloned, ...prev]);
    setActiveChatId(cloned.id);
  };

  // Delete a chat
  const handleDeleteChat = async (chatIdToDelete) => {
    setAllChats((prev) => prev.filter((c) => c.id !== chatIdToDelete));
    if (activeChatId === chatIdToDelete) {
      const remainingInSession = allChats.filter(
        (c) => c.sessionId === activeSessionId && c.id !== chatIdToDelete
      );
      if (remainingInSession.length > 0) {
        setActiveChatId(remainingInSession[0].id);
      } else {
        const newChatId = `chat_${Date.now()}`;
        const freshChat = {
          id: newChatId,
          sessionId: activeSessionId,
          title: 'New chat',
          messages: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };
        setAllChats((prev) => [freshChat, ...prev.filter((c) => c.id !== chatIdToDelete)]);
        setActiveChatId(newChatId);
      }
    }
    // Delete from backend SQLite asynchronously
    try {
      await fetch(`${GATEWAY_URL}/api/sessions/${chatIdToDelete}`, { method: 'DELETE' });
    } catch (e) {
      console.warn(`Failed to delete chat ${chatIdToDelete} on backend:`, e);
    }
  };

  // Dispatch message to Gateway orchestrator
  const handleSendMessage = async (
    rawQuery,
    isDeepThink = false,
    imageBase64 = null,
    modelOverride = null,
    attachedDocument = null
  ) => {
    const docObj = (attachedDocument && typeof attachedDocument === 'object')
      ? attachedDocument
      : (attachedDocument ? { filename: attachedDocument, filePath: null } : null);
    const docFilename = docObj?.filename || null;
    const docFilePath = docObj?.filePath || null;
    const isDocAttached = Boolean(docFilename);

    let sanitizedQuery = rawQuery ? redactSensitiveIdentifiers(rawQuery.trim()) : '';
    if (!sanitizedQuery && imageBase64 && !isDocAttached) {
      sanitizedQuery = 'Inspect and analyze this image in detail.';
    }
    if (!sanitizedQuery && isDocAttached) {
      sanitizedQuery = `Analyze and summarize ${docFilename}.`;
    }
    if (!sanitizedQuery && !imageBase64 && !isDocAttached) return;

    const chosenModel = modelOverride || activeModel;
    const deepThinkActive = Boolean(
      isDeepThink ||
      chosenModel === 'deep_reasoning' ||
      chosenModel === 'deep' ||
      activeModel === 'deep_reasoning' ||
      activeModel === 'deep' ||
      sanitizedQuery.includes('[Deep Reasoning Mode]')
    );
    const modelIdentifier = isDocAttached ? 'llama-3.3-70b-versatile' : (deepThinkActive ? 'deep_reasoning' : (chosenModel || 'fast'));

    let targetChatId = activeChatId || ensureActiveChatId();
    let targetChat = allChats.find((c) => c.id === targetChatId && c.sessionId === activeSessionId);

    // Auto-create chat if none active in this session
    if (!targetChatId || !targetChat) {
      targetChatId = `chat_${Date.now()}`;
      targetChat = {
        id: targetChatId,
        sessionId: activeSessionId,
        title: sanitizedQuery.slice(0, 32) + (sanitizedQuery.length > 32 ? '...' : ''),
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [],
      };
      setAllChats((prev) => [targetChat, ...prev]);
      setActiveChatId(targetChatId);
    }

    // Extract sliding window context of recent turns (last 8 messages)
    const priorTurns = (targetChat?.messages || [])
      .slice(-8)
      .map((m) => ({
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content || '',
      }));

    // Add user message to chat (with image preview data URI if attached)
    const userMessage = {
      role: 'user',
      content: sanitizedQuery,
      image: isDocAttached ? null : (imageBase64 || null),
      attachedDocument: docFilename || null,
      timestamp: Date.now(),
    };

    setAllChats((prev) =>
      prev.map((c) => {
        if (c.id === targetChatId) {
          const updatedTitle =
            !c.title || c.title === 'New chat'
              ? sanitizedQuery.slice(0, 32) + (sanitizedQuery.length > 32 ? '...' : '')
              : c.title;
          return {
            ...c,
            title: updatedTitle,
            updatedAt: Date.now(),
            messages: [...c.messages, userMessage],
          };
        }
        return c;
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

    // Call Gateway /api/chat with synchronized document context, file path, and forced text model
    try {
      const payload = {
        message: sanitizedQuery || (docFilename ? `Analyze and summarize ${docFilename}.` : 'Analyze and describe this document in detail.'),
        query: sanitizedQuery || (docFilename ? `Analyze and summarize ${docFilename}.` : 'Analyze and describe this document in detail.'),
        session_id: activeSessionId || targetChatId || 'default',
        chat_id: targetChatId || activeChatId,
        document_context: docFilename || null,
        file_path: docFilePath || null,
        attached_document: docFilename || null,
        model: modelIdentifier,
        history: priorTurns,
        workspace_id: activeSessionId,
        image: isDocAttached ? null : (imageBase64 || null),
        image_base64: isDocAttached ? null : (imageBase64 || null),
        lat: activeLat,
        lon: activeLon,
        deep_think: deepThinkActive,
      };

      const res = await fetch(`${GATEWAY_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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
        const thoughtTrace = data.thought_trace ? redactSensitiveIdentifiers(data.thought_trace) : null;

        const assistantMessage = {
          role: 'assistant',
          content: assistantReply,
          thought_trace: thoughtTrace,
          toolsExecuted: toolsExecuted,
          timestamp: Date.now(),
        };

        setAllChats((prev) =>
          prev.map((c) =>
            c.id === targetChatId
              ? { ...c, updatedAt: Date.now(), messages: [...c.messages, assistantMessage] }
              : c
          )
        );
      } else {
        const errorText = data.detail || data.error || 'Gateway processing error.';
        const assistantMessage = {
          role: 'assistant',
          content: `⚠️ **Error communicating with Nexis Gateway:** ${errorText}\n\n*Please ensure all backend microservices are active on localhost.*`,
          toolsExecuted: [],
          timestamp: Date.now(),
          isError: true,
          failedQuery: sanitizedQuery,
        };

        setAllChats((prev) =>
          prev.map((c) =>
            c.id === targetChatId
              ? { ...c, updatedAt: Date.now(), messages: [...c.messages, assistantMessage] }
              : c
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
        isError: true,
        failedQuery: sanitizedQuery,
      };

      setAllChats((prev) =>
        prev.map((c) =>
          c.id === targetChatId
            ? { ...c, updatedAt: Date.now(), messages: [...c.messages, assistantMessage] }
            : c
        )
      );
    }
  };

  // Vision Analysis Callback
  const handleVisionComplete = (analysisData) => {
    const summary =
      `**Prescription OCR & Vision Report:**\n\n` +
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
        allChats={allChats}
        activeSessionId={activeSessionId}
        activeChatId={activeChatId}
        sessionProfiles={sessionProfiles}
        onSelectChat={handleSelectChat}
        onDeleteChat={handleDeleteChat}
        onRenameChat={handleRenameChat}
        onDuplicateChat={handleDuplicateChat}
        onSwitchSession={handleSwitchSession}
        onAddNewSession={handleAddNewSession}
        // Backwards compatibility props
        sessions={allChats}
        currentSessionId={activeChatId}
        onSelectSession={handleSelectChat}
        onDeleteSession={handleDeleteChat}
        onRenameSession={handleRenameChat}
        onDuplicateSession={handleDuplicateChat}
        onSwitchProfile={handleSwitchSession}
        onNewChat={handleNewChat}
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
            <ModelSelector
              activeModel={activeModel}
              onSelectModel={handleSelectModel}
            />
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
              sessionId={activeChatId || activeSessionId}
              activeChatId={activeChatId}
              onEnsureActiveChat={ensureActiveChatId}
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
        sessionCount={allChats.filter((c) => c.sessionId === activeSessionId).length}
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
