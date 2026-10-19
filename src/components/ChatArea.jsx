import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Sparkles,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Copy,
  Check,
  Youtube,
  Brain,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
} from 'lucide-react';
import { NexisLogo } from './NexisLogo';
import { VideoCardGrid } from './VideoCard';
import {
  extractVideosFromTableNode,
  extractVideosFromUlNode,
  findYouTubeLinkInNode,
  extractYouTubeVideoId,
  extractYouTubeId,
  getNodeText,
} from '../utils/youtube';

export function ChatArea({
  messages,
  isLoading,
  onSelectSuggestion,
}) {
  const scrollEndRef = useRef(null);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8 md:px-6 flex flex-col bg-transparent">
      {messages.length === 0 ? (
        <HeroCanvas />
      ) : (
        <div className="w-full max-w-4xl mx-auto px-4 py-4 space-y-6">
          {messages.map((msg, idx) => (
            <MessageRow key={idx} message={msg} onRetry={onSelectSuggestion} />
          ))}

          {/* Modern Gemini Shimmer Stream Skeleton */}
          {isLoading && (
            <div className="flex items-start gap-4 w-full animate-in fade-in duration-300">
              {/* Nexis Avatar */}
              <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-cyan-500 to-indigo-600 flex items-center justify-center text-white text-xs font-semibold shrink-0 shadow-sm animate-pulse">
                N
              </div>

              {/* Modern Gemini Ambient Shimmer Wave */}
              <div className="flex-1 space-y-2.5 pt-1.5 max-w-lg">
                <div className="h-3 w-4/5 rounded-full bg-gradient-to-r from-[#282a2c] via-[#383a3d] to-[#282a2c] bg-[length:200%_100%] animate-shimmer" />
                <div className="h-3 w-3/5 rounded-full bg-gradient-to-r from-[#282a2c] via-[#383a3d] to-[#282a2c] bg-[length:200%_100%] animate-shimmer [animation-delay:150ms]" />
                <div className="h-3 w-2/5 rounded-full bg-gradient-to-r from-[#282a2c] via-[#383a3d] to-[#282a2c] bg-[length:200%_100%] animate-shimmer [animation-delay:300ms]" />
              </div>
            </div>
          )}

          <div ref={scrollEndRef} />
        </div>
      )}
    </div>
  );
}

/**
 * Centered Minimal Hero Canvas ("What should we focus on?")
 */
function HeroCanvas() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
      <h1 className="text-4xl md:text-5xl font-normal text-[#e3e3e3] mb-8 tracking-tight">
        What should we focus on?
      </h1>
    </div>
  );
}

/**
 * Custom ReactMarkdown renderers for YouTube cards, tables, lists, and links
 */
const markdownComponents = {
  table: ({ node, children, ...props }) => {
    const videos = extractVideosFromTableNode(node);
    if (videos.length > 0) {
      return <VideoCardGrid videos={videos} />;
    }
    return (
      <div className="overflow-x-auto my-3 rounded-xl border border-[#282a2c]">
        <table className="w-full text-left border-collapse text-xs" {...props}>
          {children}
        </table>
      </div>
    );
  },
  ul: ({ node, children, ...props }) => {
    const videos = extractVideosFromUlNode(node);
    if (videos.length > 0) {
      return <VideoCardGrid videos={videos} />;
    }
    return (
      <ul className="list-disc pl-5 my-2 space-y-1 text-[#c4c7c5]" {...props}>
        {children}
      </ul>
    );
  },
  p: ({ node, children, ...props }) => {
    const ytLink = findYouTubeLinkInNode(node);
    if (ytLink) {
      const text = getNodeText(node).trim();
      if (text === ytLink.url || text === ytLink.text || text.length <= ytLink.url.length + 10) {
        return (
          <VideoCardGrid
            videos={[
              {
                videoId: ytLink.videoId,
                url: ytLink.url,
                title: ytLink.text || 'Educational Demonstration',
                channel: 'YouTube',
              },
            ]}
          />
        );
      }
    }
    return <p {...props}>{children}</p>;
  },
  a: ({ href, children, ...props }) => {
    const videoId = extractYouTubeId(href);
    if (videoId) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 px-2.5 py-0.5 my-0.5 rounded-md bg-red-500/10 hover:bg-red-500/20 text-red-400 hover:text-red-300 border border-red-500/25 text-xs font-medium transition-colors no-underline"
          {...props}
        >
          <Youtube size={12} className="text-red-400 shrink-0" />
          <span>{children}</span>
          <ExternalLink size={11} className="opacity-70 shrink-0" />
        </a>
      );
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  },
};

/**
 * Helper to separate <think>...</think> reasoning blocks from final response
 */
function extractThinkingProcess(content) {
  if (!content || typeof content !== 'string') {
    return { thinking: null, body: content || '' };
  }
  const match = content.match(/<think>([\s\S]*?)<\/think>/i);
  if (match) {
    const thinking = match[1].trim();
    const body = content.replace(/<think>[\s\S]*?<\/think>/i, '').trim();
    return { thinking, body };
  }
  return { thinking: null, body: content };
}

/**
 * Collapsible Thinking Process Accordion for Deep Reasoning mode.
 */
function ThinkingAccordion({ thinking }) {
  const [isOpen, setIsOpen] = useState(false);
  if (!thinking) return null;

  return (
    <div className="mb-3 rounded-2xl bg-[#1e1f20] border border-[#2d2f31] overflow-hidden text-xs shadow-sm">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-2.5 flex items-center justify-between text-[#c4c7c5] hover:text-[#f0f4f9] hover:bg-[#282a2c] transition-colors"
      >
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-[#9b72cf] animate-pulse-subtle" />
          <span className="font-normal text-xs text-[#c4c7c5]">
            Thought for a few seconds ({isOpen ? 'Collapse' : 'Expand'})
          </span>
        </div>
        {isOpen ? (
          <ChevronUp size={13} className="text-[#8e918f]" />
        ) : (
          <ChevronDown size={13} className="text-[#8e918f]" />
        )}
      </button>

      {isOpen && (
        <div className="p-4 bg-[#141414] border-t border-[#282a2c] text-[#a8adb7] text-xs font-mono leading-relaxed whitespace-pre-wrap max-h-72 overflow-y-auto">
          {thinking}
        </div>
      )}
    </div>
  );
}

/**
 * Individual message row with markdown rendering and tools executed pills
 */
function MessageRow({ message, onRetry }) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [rating, setRating] = useState(null);
  const extracted = !isUser
    ? extractThinkingProcess(message.content)
    : { thinking: null, body: message.content };
  const thinking = message.thought_trace || extracted.thinking;
  const body = message.thought_trace ? message.content : extracted.body;

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <div className="flex justify-end w-full animate-fade-in-up">
        <div className="max-w-[80%] md:max-w-[70%] bg-[#282a2c] text-[#f0f4f9] px-5 py-3 rounded-3xl shadow-sm text-sm leading-relaxed whitespace-pre-wrap space-y-2.5">
          {message.image && (
            <div className="rounded-2xl overflow-hidden max-w-xs border border-white/10 shadow-md">
              <img
                src={message.image}
                alt="Uploaded attachment"
                className="w-full max-h-60 object-contain bg-black/40"
              />
            </div>
          )}
          <p>{message.content}</p>
        </div>
      </div>
    );
  }

  const isErrorMessage = Boolean(
    message.isError ||
    message.failedQuery ||
    message.content?.includes("Connection Offline") ||
    message.content?.includes("Gateway Processing Error") ||
    message.content?.includes("Error communicating with Nexis Gateway")
  );

  return (
    <div className="flex gap-4 w-full justify-start items-start animate-fade-in-up group">
      <div className="w-8 h-8 rounded-full bg-[#1e1f20] border border-[#2d2f31] flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
        <NexisLogo size={18} glow />
      </div>

      <div className="flex-1 w-full text-[#e3e3e3] text-sm leading-relaxed overflow-x-auto space-y-3">
        {thinking && <ThinkingAccordion thinking={thinking} />}
        <div className="prose-dark leading-relaxed w-full">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {body}
          </ReactMarkdown>
        </div>

        {/* Actionable Retry Trigger on Connection Offline or Server Error */}
        {isErrorMessage && onRetry && (
          <div className="pt-0.5">
            <button
              type="button"
              onClick={() => onRetry(message.failedQuery || 'Retry sending query')}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/35 text-amber-300 hover:text-amber-200 text-xs font-medium transition-all cursor-pointer shadow-sm"
              title="Retry sending message to Nexis Gateway"
            >
              <RotateCcw size={12} />
              <span>Retry Request</span>
            </button>
          </div>
        )}

        {/* Action bar with Copy and Feedback micro-interactions */}
        <div className="flex items-center gap-1.5 pt-1 opacity-90 md:opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <button
            type="button"
            onClick={handleCopy}
            className="text-[11px] text-[#8e918f] hover:text-[#e3e3e3] flex items-center gap-1.5 transition-all px-2.5 py-1 rounded-full hover:bg-[#282a2c]"
            title="Copy message to clipboard"
          >
            {copied ? <Check size={12} className="text-[#4da2ff]" /> : <Copy size={12} />}
            <span>{copied ? 'Copied!' : 'Copy'}</span>
          </button>

          <button
            type="button"
            onClick={() => setRating(rating === 'up' ? null : 'up')}
            className={`p-1.5 rounded-full transition-all ${
              rating === 'up'
                ? 'text-[#4da2ff] bg-[#4da2ff]/10'
                : 'text-[#8e918f] hover:text-[#e3e3e3] hover:bg-[#282a2c]'
            }`}
            title="Good response"
          >
            <ThumbsUp size={13} />
          </button>

          <button
            type="button"
            onClick={() => setRating(rating === 'down' ? null : 'down')}
            className={`p-1.5 rounded-full transition-all ${
              rating === 'down'
                ? 'text-rose-400 bg-rose-500/10'
                : 'text-[#8e918f] hover:text-[#e3e3e3] hover:bg-[#282a2c]'
            }`}
            title="Bad response"
          >
            <ThumbsDown size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
