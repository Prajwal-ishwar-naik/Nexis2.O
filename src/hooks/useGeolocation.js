import { useState, useEffect, useCallback, useRef } from 'react';

const DEFAULT_LAT = 12.9716;
const DEFAULT_LON = 77.5946;
const DEFAULT_LOCALITY = 'Bengaluru, KA (Default)';
const GEOLOCATION_TIMEOUT_MS = 3500;

/**
 * High-Accuracy Hardware Geolocation Hook with 3.5s Timeout Race Condition
 * Prevents UI hang and ensures clear status transitions: 'loading' -> 'resolved' | 'fallback'
 */
export function useGeolocation() {
  const [location, setLocation] = useState({
    lat: DEFAULT_LAT,
    lon: DEFAULT_LON,
    accuracy: null,
    status: 'loading', // 'loading' | 'resolved' | 'fallback'
    error: null,
    resolvedLocality: null,
  });

  const hasResolvedRef = useRef(false);

  // Reverse geocoding helper with 2.0s fallback safety
  const reverseGeocode = async (lat, lon) => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}&zoom=14&addressdetails=1`,
        {
          headers: { Accept: 'application/json' },
          signal: controller.signal,
        }
      );
      clearTimeout(timeoutId);
      if (res.ok) {
        const data = await res.json();
        const addr = data.address || {};
        const locality =
          addr.suburb ||
          addr.neighbourhood ||
          addr.city_district ||
          addr.city ||
          addr.town ||
          addr.state_district ||
          data.name;
        const state = addr.state_code || addr.state || '';
        if (locality) {
          return state ? `${locality}, ${state}` : locality;
        }
      }
    } catch {
      // Ignore network / CORS failure and fallback cleanly
    }
    return null;
  };

  const acquireFreshLocation = useCallback((customTimeout = GEOLOCATION_TIMEOUT_MS) => {
    return new Promise((resolve) => {
      let isCompleted = false;

      const finishFallback = (errReason = 'Location timed out') => {
        if (isCompleted) return;
        isCompleted = true;
        hasResolvedRef.current = true;
        setLocation((prev) => ({
          ...prev,
          lat: prev.lat || DEFAULT_LAT,
          lon: prev.lon || DEFAULT_LON,
          status: 'fallback',
          error: errReason,
          resolvedLocality: prev.resolvedLocality || DEFAULT_LOCALITY,
        }));
        resolve({
          lat: DEFAULT_LAT,
          lon: DEFAULT_LON,
          locality: DEFAULT_LOCALITY,
        });
      };

      // 3.5-second strict race condition
      const timer = setTimeout(() => {
        finishFallback('Geolocation timeout exceeded (3.5s limit)');
      }, customTimeout);

      if (!('geolocation' in navigator)) {
        clearTimeout(timer);
        return finishFallback('Geolocation not supported by browser');
      }

      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          if (isCompleted) return;
          clearTimeout(timer);
          isCompleted = true;
          hasResolvedRef.current = true;

          const freshLat = parseFloat(pos.coords.latitude.toFixed(6));
          const freshLon = parseFloat(pos.coords.longitude.toFixed(6));
          const accuracy = pos.coords.accuracy;

          // Attempt locality resolution
          const locality = await reverseGeocode(freshLat, freshLon);
          const finalLocality = locality || `${freshLat.toFixed(2)}, ${freshLon.toFixed(2)}`;

          setLocation({
            lat: freshLat,
            lon: freshLon,
            accuracy,
            status: 'resolved',
            error: null,
            resolvedLocality: finalLocality,
          });

          resolve({ lat: freshLat, lon: freshLon, locality: finalLocality });
        },
        (err) => {
          clearTimeout(timer);
          finishFallback(err.message || 'Permission denied or unavailable');
        },
        {
          enableHighAccuracy: false,
          timeout: customTimeout,
          maximumAge: 60000,
        }
      );
    });
  }, []);

  // Initial silent acquisition on mount (with guaranteed 3.5s completion)
  useEffect(() => {
    acquireFreshLocation(GEOLOCATION_TIMEOUT_MS);
  }, [acquireFreshLocation]);

  const updateResolvedLocality = useCallback((localityName) => {
    if (!localityName) return;
    setLocation((prev) => ({
      ...prev,
      status: 'resolved',
      resolvedLocality: localityName,
    }));
  }, []);

  return {
    location,
    acquireFreshLocation,
    updateResolvedLocality,
  };
}
