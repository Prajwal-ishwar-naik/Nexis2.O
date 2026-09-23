import React, { useState, useRef, useEffect } from 'react';
import {
  SquarePen,
  Search,
  UploadCloud,
  BellRing,
  MoreHorizontal,
  Pencil,
  Copy,
  Trash2,
  PanelLeft,
  X,
  ChevronsUpDown,
  Plus,
  Check,
} from 'lucide-react';
import { NexisLogo } from './NexisLogo';

export function Sidebar({
  sessions = [],
  currentSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  onRenameSession,
  onDuplicateSession,
  onOpenVisionModal,
  onOpenEduModal,
  onOpenMcpModal,
  onOpenClusterModal,
  onOpenProfileModal,
  onOpenVoiceModal,
  onPrefillPrompt,
  location,
  isOpen = true,
  onToggleSidebar,
  activeMode = 'assistant',
  onSelectMode,
  onSwitchProfile,
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchActive, setIsSearchActive] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [activeMenuSessionId, setActiveMenuSessionId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const fileInputRef = useRef(null);
  const recentsContainerRef = useRef(null);
  const prevSessionsCount = useRef(sessions.length);
  const menuRef = useRef(null);

  // Auto-scroll to top when a new session is created
  useEffect(() => {
    if (sessions.length > prevSessionsCount.current) {
      recentsContainerRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    }
    prevSessionsCount.current = sessions.length;
  }, [sessions.length]);

  // Click outside to close 3-dot menu
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setActiveMenuSessionId(null);
        setConfirmDeleteId(null);
      }
    }
    if (activeMenuSessionId !== null) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [activeMenuSessionId]);

  const handleStartRename = (sess, e) => {
    e?.stopPropagation();
    setEditingSessionId(sess.id);
    setEditTitle(sess.title || 'Untitled Session');
    setActiveMenuSessionId(null);
  };

  const handleSaveRename = (sessId) => {
    const trimmed = editTitle.trim();
    if (trimmed && onRenameSession) {
      onRenameSession(sessId, trimmed);
    }
    setEditingSessionId(null);
  };

  const handleDuplicate = (sessId, e) => {
    e?.stopPropagation();
    setActiveMenuSessionId(null);
    if (onDuplicateSession) {
      onDuplicateSession(sessId);
    }
  };

  const handleDelete = (sessId, e) => {
    e?.stopPropagation();
    if (onDeleteSession) {
      onDeleteSession(sessId);
    }
    setActiveMenuSessionId(null);
    setConfirmDeleteId(null);
  };

  const filteredSessions = sessions.filter((s) => {
    if (!searchQuery.trim()) return true;
    return (s.title || '').toLowerCase().includes(searchQuery.toLowerCase());
  });

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-30 lg:hidden backdrop-blur-sm"
          onClick={onToggleSidebar}
        />
      )}

      {/* Main Sidebar Container - Gemini Dark Slate #1e1f20 with Collapsible Transition */}
      <aside
        className={`fixed lg:static top-0 bottom-0 left-0 z-40 bg-[#1e1f20] border-r border-[#282a2c] flex flex-col transition-all duration-300 ease-in-out select-none overflow-hidden ${
          isOpen
            ? 'w-68 md:w-72 translate-x-0 opacity-100'
            : 'w-0 -translate-x-full md:w-0 opacity-0 border-r-0 pointer-events-none'
        }`}
      >
        {/* Top Header: Branding + Toggle */}
        <div className="px-4 py-3.5 flex items-center justify-between border-b border-[#282a2c]/60 shrink-0">
          <div className="flex items-center gap-2.5">
            <NexisLogo size={20} glow />
            <span className="font-semibold text-lg tracking-tight text-[#e3e3e3]">Nexis</span>
          </div>

          <button
            type="button"
            onClick={onToggleSidebar}
            className="p-1.5 text-[#8e918f] hover:text-[#e3e3e3] hover:bg-[#282a2c] rounded-lg transition-colors cursor-pointer"
            title="Collapse sidebar"
          >
            <PanelLeft size={18} />
          </button>
        </div>

        {/* Mode Pill Toggle: [ Assistant | Spark ] */}
        <div className="px-3 pt-3 pb-2 shrink-0">
          <div className="flex p-0.5 rounded-full bg-[#171819] border border-[#282a2c] text-xs font-medium">
            <button
              type="button"
              onClick={() => onSelectMode && onSelectMode('assistant')}
              className={`flex-1 py-1.5 rounded-full text-center transition-all cursor-pointer ${
                activeMode === 'assistant'
                  ? 'bg-[#282a2c] text-[#f0f4f9] shadow-sm font-medium'
                  : 'text-[#8e918f] hover:text-[#c4c7c5]'
              }`}
            >
              Assistant
            </button>
            <button
              type="button"
              onClick={() => onSelectMode && onSelectMode('spark')}
              className={`flex-1 py-1.5 rounded-full text-center transition-all flex items-center justify-center cursor-pointer ${
                activeMode === 'spark'
                  ? 'bg-[#282a2c] text-[#f0f4f9] shadow-sm font-medium'
                  : 'text-[#8e918f] hover:text-[#c4c7c5]'
              }`}
            >
              Spark
            </button>
          </div>
        </div>

        {/* Hidden file input for native ingestion */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file && onOpenVisionModal) {
              onOpenVisionModal(file);
            }
          }}
          accept="image/*,.pdf"
          className="hidden"
        />

        {/* Action Links List */}
        <div className="px-3 py-1 space-y-0.5 border-b border-[#282a2c]/60 pb-2 shrink-0">
          {[
            {
              id: 'new_chat',
              label: 'New chat',
              icon: SquarePen,
              action: onNewChat,
              iconColor: 'text-[#c4c7c5] group-hover:text-white',
            },
            {
              id: 'search',
              label: 'Search chats',
              icon: Search,
              action: () => setIsSearchActive((prev) => !prev),
              iconColor: 'text-[#8e918f]',
              isActive: isSearchActive,
            },
            {
              id: 'upload_inspect',
              label: 'Upload & Inspect',
              icon: UploadCloud,
              action: () => {
                if (fileInputRef.current) {
                  fileInputRef.current.click();
                } else if (onOpenVisionModal) {
                  onOpenVisionModal();
                }
              },
              iconColor: 'text-[#4da2ff]',
            },
            {
              id: 'smart_reminders',
              label: 'Smart Reminders',
              icon: BellRing,
              action: () => onOpenVoiceModal && onOpenVoiceModal(),
              iconColor: 'text-[#9b72cf]',
            },
          ].map((item) => {
            const Icon = item.icon;
            const isItemActive = item.isActive;
            return (
              <React.Fragment key={item.id}>
                <button
                  type="button"
                  onClick={item.action}
                  title={item.title || item.label}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-colors text-left cursor-pointer group ${
                    isItemActive
                      ? 'bg-[#282a2c] text-white'
                      : 'text-[#c4c7c5] hover:text-white hover:bg-[#282a2c]'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon size={16} className={item.iconColor || 'text-[#8e918f] group-hover:text-white'} />
                    <span>{item.label}</span>
                  </div>
                  {item.badge && (
                    <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded ${item.badgeColor || 'bg-[#282a2c] text-[#8e918f]'}`}>
                      {item.badge}
                    </span>
                  )}
                </button>

                {item.id === 'search' && isSearchActive && (
                  <div className="px-1 py-1">
                    <div className="relative">
                      <input
                        type="text"
                        autoFocus
                        placeholder="Search previous chats..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full bg-[#171819] text-[#f0f4f9] text-xs rounded-lg pl-2.5 pr-7 py-1.5 border border-[#282a2c] focus:outline-none focus:border-[#4da2ff]"
                      />
                      {searchQuery && (
                        <button
                          type="button"
                          onClick={() => setSearchQuery('')}
                          className="absolute right-2 top-2 text-[#8e918f] hover:text-white cursor-pointer"
                        >
                          <X size={12} />
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Dynamic Recents List */}
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5" ref={recentsContainerRef}>
          <div className="px-3 py-1 text-[11px] font-medium text-[#8e918f] uppercase tracking-wider">
            Recent
          </div>

          {filteredSessions.length === 0 ? (
            <div className="px-3 py-5 text-center text-[#8e918f] text-xs">
              <p className="font-normal text-[#c4c7c5] mb-0.5">
                {searchQuery ? 'No matching chats' : 'No recent chats'}
              </p>
              <p className="text-[11px] text-[#8e918f]">
                {searchQuery ? 'Try a different keyword' : 'Start asking to see history here'}
              </p>
            </div>
          ) : (
            filteredSessions.map((sess) => {
              const isActive = sess.id === currentSessionId;
              const isEditing = editingSessionId === sess.id;
              const isMenuOpen = activeMenuSessionId === sess.id;
              const isConfirmingDelete = confirmDeleteId === sess.id;

              return (
                <div
                  key={sess.id}
                  onClick={() => {
                    if (!isEditing) onSelectSession(sess.id);
                  }}
                  className={`group relative flex items-center justify-between px-3 py-2 rounded-full cursor-pointer text-xs font-normal transition-all ${
                    isActive
                      ? 'bg-[#282a2c] text-[#f0f4f9]'
                      : 'text-[#c4c7c5] hover:text-[#f0f4f9] hover:bg-[#282a2c]/60'
                  }`}
                >
                  <div className="truncate flex-1 pr-2">
                    {isEditing ? (
                      <input
                        type="text"
                        autoFocus
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveRename(sess.id);
                          if (e.key === 'Escape') setEditingSessionId(null);
                        }}
                        onBlur={() => handleSaveRename(sess.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="bg-[#171819] text-white border border-[#4da2ff] rounded-md px-1.5 py-0.5 text-xs outline-none w-full"
                      />
                    ) : (
                      <span className="truncate block">{sess.title || 'New conversation'}</span>
                    )}
                  </div>

                  {/* 3-Dot Contextual Action Button */}
                  {!isEditing && (
                    <div className="relative shrink-0" ref={isMenuOpen ? menuRef : null}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveMenuSessionId(isMenuOpen ? null : sess.id);
                          setConfirmDeleteId(null);
                        }}
                        className={`p-1 rounded-full text-[#8e918f] hover:text-white transition-all cursor-pointer ${
                          isMenuOpen ? 'opacity-100 text-white' : 'opacity-0 group-hover:opacity-100'
                        }`}
                        title="Session options"
                      >
                        <MoreHorizontal size={14} />
                      </button>

                      {/* Context Menu Dropdown */}
                      {isMenuOpen && (
                        <div className="absolute right-0 top-7 z-50 w-36 bg-[#1e1f20] border border-[#2d2f31] rounded-2xl shadow-2xl p-1 text-xs text-[#e3e3e3] animate-fade-in-up">
                          {isConfirmingDelete ? (
                            <div className="p-2 text-left">
                              <p className="text-[11px] text-[#e3e3e3] font-medium mb-2">Delete chat?</p>
                              <div className="flex items-center gap-1.5 justify-end">
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setConfirmDeleteId(null);
                                  }}
                                  className="px-2 py-1 text-[10px] rounded-lg bg-[#282a2c] hover:bg-[#333538] text-[#c4c7c5] transition-colors cursor-pointer"
                                >
                                  Cancel
                                </button>
                                <button
                                  type="button"
                                  onClick={(e) => handleDelete(sess.id, e)}
                                  className="px-2 py-1 text-[10px] rounded-lg bg-red-600/80 hover:bg-red-600 text-white font-medium transition-colors cursor-pointer"
                                >
                                  Delete
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="space-y-0.5">
                              <button
                                type="button"
                                onClick={(e) => handleStartRename(sess, e)}
                                className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-[#c4c7c5] hover:text-white hover:bg-[#282a2c] rounded-xl transition-colors cursor-pointer"
                              >
                                <Pencil size={12} className="text-[#8e918f]" />
                                <span>Rename</span>
                              </button>

                              <button
                                type="button"
                                onClick={(e) => handleDuplicate(sess.id, e)}
                                className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-[#c4c7c5] hover:text-white hover:bg-[#282a2c] rounded-xl transition-colors cursor-pointer"
                              >
                                <Copy size={12} className="text-[#8e918f]" />
                                <span>Duplicate</span>
                              </button>

                              <div className="my-1 border-t border-[#282a2c]" />

                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setConfirmDeleteId(sess.id);
                                }}
                                className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-xl transition-colors cursor-pointer"
                              >
                                <Trash2 size={12} />
                                <span>Delete</span>
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Workspace / Multi-Profile Session Switcher Footer */}
        <SidebarFooter onSwitchProfile={onSwitchProfile} />
      </aside>
    </>
  );
}

/**
 * Clean Workspace / Multi-Profile Session Switcher Footer
 */
export function SidebarFooter({ onSwitchProfile }) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [newSessionName, setNewSessionName] = useState('');
  const [profiles, setProfiles] = useState(() => {
    try {
      const saved = localStorage.getItem('nexis_user_profiles');
      if (saved) return JSON.parse(saved);
    } catch (e) {
      console.error(e);
    }
    return [
      { id: '1', name: 'Prajwal Naik', initial: 'P', active: true },
      { id: '2', name: 'Academic Research', initial: 'A', active: false },
    ];
  });

  const menuRef = useRef(null);

  // Sync profiles to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('nexis_user_profiles', JSON.stringify(profiles));
    } catch (e) {
      console.error(e);
    }
  }, [profiles]);

  // Click outside listener to close popup and reset inline input
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsMenuOpen(false);
        setIsCreatingSession(false);
        setNewSessionName('');
      }
    }
    if (isMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isMenuOpen]);

  const activeProfile = profiles.find((p) => p.active) || profiles[0];

  const handleSelect = (id) => {
    setProfiles((prev) => prev.map((p) => ({ ...p, active: p.id === id })));
    setIsMenuOpen(false);
    setIsCreatingSession(false);
    setNewSessionName('');
    if (onSwitchProfile) onSwitchProfile(id);
  };

  const handleConfirmCreate = () => {
    const trimmed = newSessionName.trim();
    if (!trimmed) return;
    const newP = {
      id: Date.now().toString(),
      name: trimmed,
      initial: trimmed.charAt(0).toUpperCase(),
      active: true,
    };
    setProfiles((prev) => [...prev.map((p) => ({ ...p, active: false })), newP]);
    setIsCreatingSession(false);
    setNewSessionName('');
    setIsMenuOpen(false);
    if (onSwitchProfile) onSwitchProfile(newP.id);
  };

  return (
    <div className="relative p-3 border-t border-[#282a2c]" ref={menuRef}>
      {/* Profile Switcher Trigger */}
      <button
        type="button"
        onClick={() => {
          setIsMenuOpen(!isMenuOpen);
          setIsCreatingSession(false);
          setNewSessionName('');
        }}
        className="w-full flex items-center justify-between p-2 rounded-xl hover:bg-[#282a2c] transition-colors cursor-pointer group"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-600 to-purple-500 flex items-center justify-center text-white text-xs font-semibold shrink-0">
            {activeProfile.initial}
          </div>
          <span className="text-sm font-medium text-gray-200 truncate">
            {activeProfile.name}
          </span>
        </div>
        <ChevronsUpDown className="text-gray-400 group-hover:text-gray-200 shrink-0" size={16} />
      </button>

      {/* Upward Floating Switcher Menu */}
      {isMenuOpen && (
        <div className="absolute bottom-full left-3 right-3 mb-2 bg-[#1e1f20] border border-[#2d2f31] rounded-xl shadow-2xl p-1.5 z-50 space-y-1 animate-in fade-in zoom-in-95 duration-150">
          <div className="px-2 py-1 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
            Switch Session
          </div>

          {profiles.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => handleSelect(p.id)}
              className="w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-xs text-gray-200 hover:bg-[#282a2c] transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-2.5 truncate">
                <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-blue-600 to-purple-500 flex items-center justify-center text-white text-[10px] font-semibold">
                  {p.initial}
                </div>
                <span className="truncate">{p.name}</span>
              </div>
              {p.active && <Check className="text-blue-400 shrink-0" size={14} />}
            </button>
          ))}

          <div className="pt-1 border-t border-[#282a2c]">
            {isCreatingSession ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleConfirmCreate();
                }}
                className="flex items-center gap-1.5 p-1"
              >
                <input
                  type="text"
                  autoFocus
                  placeholder="Session name..."
                  value={newSessionName}
                  onChange={(e) => setNewSessionName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') {
                      setIsCreatingSession(false);
                      setNewSessionName('');
                    }
                  }}
                  className="flex-1 bg-[#171819] text-[#f0f4f9] text-xs rounded-lg px-2 py-1.5 border border-[#282a2c] focus:outline-none focus:border-[#4da2ff] placeholder-[#8e918f]"
                />
                <button
                  type="submit"
                  disabled={!newSessionName.trim()}
                  className="p-1.5 text-xs font-medium bg-[#4da2ff] hover:bg-[#3d8be0] disabled:opacity-40 disabled:hover:bg-[#4da2ff] text-white rounded-lg transition-colors cursor-pointer shrink-0"
                  title="Create session"
                >
                  <Check size={13} />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsCreatingSession(false);
                    setNewSessionName('');
                  }}
                  className="p-1.5 text-[#8e918f] hover:text-white rounded-lg transition-colors cursor-pointer shrink-0"
                  title="Cancel"
                >
                  <X size={13} />
                </button>
              </form>
            ) : (
              <button
                type="button"
                onClick={() => setIsCreatingSession(true)}
                className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs text-blue-400 hover:bg-[#282a2c] transition-colors cursor-pointer"
              >
                <Plus size={14} />
                <span>Add New Session</span>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
