import React, { useState } from 'react';
import { Play, ExternalLink, CheckCircle2, Youtube } from 'lucide-react';
import { getYouTubeThumbnailUrl } from '../utils/youtube';

/**
 * Single interactive YouTube video card.
 * Features 16:9 thumbnail with hover zoom, play icon overlay, 2-line truncated title,
 * channel metadata badge, and direct YouTube external link.
 */
export function VideoCard({ video }) {
  const [thumbQuality, setThumbQuality] = useState('hqdefault');
  const [hasError, setHasError] = useState(false);

  const videoId = video.videoId;
  const thumbnailUrl = videoId
    ? getYouTubeThumbnailUrl(videoId, thumbQuality)
    : '';

  const handleImageError = () => {
    if (thumbQuality === 'hqdefault') {
      setThumbQuality('mqdefault');
    } else if (thumbQuality === 'mqdefault') {
      setThumbQuality('default');
    } else {
      setHasError(true);
    }
  };

  return (
    <div className="group flex flex-col bg-[#1e1e1e] border border-[#2e2e2e] hover:border-neutral-500/50 rounded-xl overflow-hidden shadow-lg hover:shadow-2xl transition-all duration-300">
      {/* 16:9 Thumbnail preview container */}
      <a
        href={video.url}
        target="_blank"
        rel="noopener noreferrer"
        className="relative block aspect-video w-full overflow-hidden bg-black/50 cursor-pointer"
        title={`Watch "${video.title}" on YouTube`}
      >
        {!hasError && thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt={video.title || 'YouTube Tutorial'}
            onError={handleImageError}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center bg-[#181818] text-neutral-500">
            <Youtube size={32} className="text-red-500/80 mb-1" />
            <span className="text-[11px] font-medium">YouTube Preview</span>
          </div>
        )}

        {/* Ambient Dark Gradient */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent pointer-events-none" />

        {/* Centered Play Button Overlay */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-11 h-11 rounded-full bg-black/60 backdrop-blur-sm border border-white/20 flex items-center justify-center text-white shadow-xl group-hover:scale-110 group-hover:bg-red-600 group-hover:border-red-500 transition-all duration-300">
            <Play size={18} className="fill-white translate-x-0.5" />
          </div>
        </div>

        {/* YouTube Top Badge */}
        <div className="absolute top-2.5 left-2.5 px-2 py-0.5 rounded-md bg-black/75 backdrop-blur-md text-[10px] font-semibold text-white/90 border border-white/10 flex items-center gap-1 shadow-sm">
          <Youtube size={12} className="text-red-500" />
          <span>YouTube</span>
        </div>
      </a>

      {/* Video Metadata Container */}
      <div className="p-3.5 flex flex-col flex-1 justify-between gap-3 bg-[#1e1e1e]">
        <div>
          <a
            href={video.url}
            target="_blank"
            rel="noopener noreferrer"
            title={video.title}
            className="block font-bold text-white hover:text-red-400 text-sm leading-snug line-clamp-2 transition-colors"
          >
            {video.title || 'Educational Demonstration'}
          </a>

          {video.channel && (
            <div className="flex items-center gap-1.5 mt-1.5 text-xs text-neutral-400">
              <span className="truncate max-w-[200px]">{video.channel}</span>
              <CheckCircle2 size={12} className="text-neutral-500 shrink-0" />
            </div>
          )}
        </div>

        {/* Direct Link Action */}
        <div className="pt-2 border-t border-[#2a2a2a] flex items-center justify-between">
          <a
            href={video.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-red-400 hover:text-red-300 font-medium flex items-center gap-1.5 group/link transition-colors"
          >
            <span>Watch on YouTube</span>
            <ExternalLink size={12} className="group-hover/link:translate-x-0.5 transition-transform" />
          </a>
        </div>
      </div>
    </div>
  );
}

/**
 * Responsive grid container for video cards.
 * 1-column on mobile, 2-column on tablet, 3-column on desktop.
 */
export function VideoCardGrid({ videos }) {
  if (!videos || videos.length === 0) return null;

  return (
    <div className="my-4 w-full">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
        {videos.map((vid, idx) => (
          <VideoCard key={vid.videoId || vid.url || idx} video={vid} />
        ))}
      </div>
    </div>
  );
}
