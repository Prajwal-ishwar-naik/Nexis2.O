/**
 * Nexis AI - YouTube Video Utilities
 * Robust video ID extraction, thumbnail generation, and AST node parsing for markdown rendering.
 */

/**
 * Extracts 11-character YouTube video ID from various YouTube URL formats.
 * Supports:
 * - https://www.youtube.com/watch?v=VIDEO_ID
 * - https://youtu.be/VIDEO_ID
 * - https://www.youtube.com/embed/VIDEO_ID
 * - https://www.youtube.com/shorts/VIDEO_ID
 * - https://m.youtube.com/watch?v=VIDEO_ID
 * - Query params, timestamps, embed paths, and raw IDs
 */
export function extractYouTubeVideoId(url) {
  if (!url || typeof url !== 'string') return null;
  const cleanUrl = url.trim();

  const patterns = [
    /(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|shorts\/|watch\?v=|watch\?.+&v=))([\w-]{11})/i,
    /^([\w-]{11})$/
  ];

  for (const pattern of patterns) {
    const match = cleanUrl.match(pattern);
    if (match && match[1]) {
      return match[1];
    }
  }

  try {
    const parsed = new URL(cleanUrl.startsWith('http') ? cleanUrl : `https://${cleanUrl}`);
    if (parsed.hostname.includes('youtube.com')) {
      const v = parsed.searchParams.get('v');
      if (v && /^[\w-]{11}$/.test(v)) return v;
      const pathParts = parsed.pathname.split('/').filter(Boolean);
      const lastPart = pathParts[pathParts.length - 1];
      if (lastPart && /^[\w-]{11}$/.test(lastPart)) return lastPart;
    } else if (parsed.hostname === 'youtu.be') {
      const path = parsed.pathname.slice(1);
      if (path && /^[\w-]{11}$/.test(path)) return path;
    }
  } catch {
    // Ignore URL parse error
  }

  return null;
}

/**
 * Extracts YouTube video ID using exact regex specification.
 */
export function extractYouTubeId(url) {
  if (!url) return null;
  const regExp = /(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=))([\w-]{11})/;
  const match = url.match(regExp);
  return match ? match[1] : extractYouTubeVideoId(url);
}

/**
 * Checks if a string contains or is a valid YouTube URL.
 */
export function isYouTubeUrl(url) {
  return Boolean(extractYouTubeVideoId(url));
}

/**
 * Returns high-quality YouTube thumbnail preview URL.
 */
export function getYouTubeThumbnailUrl(videoId, quality = 'hqdefault') {
  if (!videoId) return '';
  return `https://img.youtube.com/vi/${videoId}/${quality}.jpg`;
}

/**
 * Extracts plain text from an AST node recursively.
 */
export function getNodeText(node) {
  if (!node) return '';
  if (node.type === 'text') return node.value || '';
  if (node.children && Array.isArray(node.children)) {
    return node.children.map(getNodeText).join('');
  }
  return '';
}

/**
 * Recursively locates a YouTube link and its associated anchor text within an AST node.
 */
export function findYouTubeLinkInNode(node) {
  if (!node) return null;

  if (node.type === 'element' && node.tagName === 'a') {
    const href = node.properties && node.properties.href;
    const videoId = extractYouTubeVideoId(href);
    if (videoId) {
      return {
        url: href,
        videoId,
        text: getNodeText(node).trim()
      };
    }
  }

  if (node.type === 'text') {
    const val = node.value || '';
    if (val.includes('youtube.com') || val.includes('youtu.be')) {
      const match = val.match(/(https?:\/\/[^\s)]+)/);
      if (match) {
        const videoId = extractYouTubeVideoId(match[1]);
        if (videoId) {
          return {
            url: match[1],
            videoId,
            text: ''
          };
        }
      }
    }
  }

  if (node.children && Array.isArray(node.children)) {
    for (const child of node.children) {
      const found = findYouTubeLinkInNode(child);
      if (found) return found;
    }
  }

  return null;
}

/**
 * Extracts structured video items from a markdown table AST node.
 * Handles cases where columns represent Title, Link, Channel in various arrangements.
 */
export function extractVideosFromTableNode(node) {
  const rows = [];
  function collectRows(n) {
    if (!n) return;
    if (n.type === 'element' && n.tagName === 'tr') {
      rows.push(n);
      return;
    }
    if (n.children && Array.isArray(n.children)) {
      n.children.forEach(collectRows);
    }
  }
  collectRows(node);

  const videos = [];
  for (const row of rows) {
    const cells = (row.children || []).filter(c => c.type === 'element' && c.tagName === 'td');
    if (cells.length === 0) continue; // skip table header (th)

    let ytLink = null;
    let linkColIdx = -1;
    const cellTexts = [];

    cells.forEach((cell, idx) => {
      const found = findYouTubeLinkInNode(cell);
      if (found && !ytLink) {
        ytLink = found;
        linkColIdx = idx;
      }
      cellTexts.push(getNodeText(cell).trim());
    });

    if (ytLink) {
      let title = '';
      let channel = '';

      const linkText = ytLink.text;
      const isGeneric =
        !linkText ||
        linkText.startsWith('http') ||
        /^(watch|watch here|watch video|view|video|link|click here|youtube)$/i.test(linkText);

      if (linkColIdx === 1) {
        // Table: [Title] | [Link] | [Channel]
        title = cellTexts[0] || (!isGeneric ? linkText : 'Video Tutorial');
        channel = cellTexts[2] || '';
      } else if (linkColIdx === 0) {
        // Table: [Link] | [Title/Channel] | ...
        title = !isGeneric ? linkText : (cellTexts[1] || 'Video Tutorial');
        channel = (!isGeneric ? cellTexts[1] : cellTexts[2]) || '';
      } else {
        // Table: [Title] | [Channel] | [Link]
        title = cellTexts[0] || (!isGeneric ? linkText : 'Video Tutorial');
        channel = cellTexts[1] || '';
      }

      // Clean up channel name if it repeats or contains url
      if (channel.includes('http')) channel = '';

      videos.push({
        videoId: ytLink.videoId,
        url: ytLink.url,
        title: title || 'Educational Demonstration',
        channel: channel || 'YouTube Channel'
      });
    }
  }

  return videos;
}

/**
 * Extracts structured video items from a markdown UL list AST node.
 * Handles formats like:
 * - [Video Title](https://www.youtube.com/watch?v=VIDEO_ID) by Channel Name
 * - [Video Title](https://www.youtube.com/watch?v=VIDEO_ID) - Channel Name
 */
export function extractVideosFromUlNode(node) {
  const lis = (node.children || []).filter(c => c.type === 'element' && c.tagName === 'li');
  if (lis.length === 0) return [];

  const videos = [];
  for (const li of lis) {
    const ytLink = findYouTubeLinkInNode(li);
    if (!ytLink) continue;

    const fullLiText = getNodeText(li).trim();
    let title = ytLink.text;
    let channel = '';

    const byMatch = fullLiText.match(/(?:by|–|-|\|)\s+([^,.\n]+)$/i);
    if (byMatch && byMatch[1]) {
      channel = byMatch[1].trim();
    }

    const isGeneric =
      !title ||
      title.startsWith('http') ||
      /^(watch|watch here|watch video|video|link|click here|youtube)$/i.test(title);

    if (isGeneric) {
      let cleaned = fullLiText.replace(ytLink.url, '').trim();
      if (byMatch) cleaned = cleaned.replace(byMatch[0], '').trim();
      if (cleaned) title = cleaned;
    }

    videos.push({
      videoId: ytLink.videoId,
      url: ytLink.url,
      title: title || 'Educational Demonstration',
      channel: channel || 'YouTube Channel'
    });
  }

  // Only consider it a video list if at least half of the items are videos
  if (videos.length > 0 && videos.length >= Math.ceil(lis.length / 2)) {
    return videos;
  }

  return [];
}
