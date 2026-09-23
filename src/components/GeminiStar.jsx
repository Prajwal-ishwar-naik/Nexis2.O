import React from 'react';
import { NexisLogo } from './NexisLogo';

/**
 * Backwards compatibility alias for NexisLogo.
 */
export function GeminiStar(props) {
  return <NexisLogo {...props} />;
}

export default GeminiStar;

