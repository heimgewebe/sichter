import { useEffect, useRef, useState } from 'react';

import { EventEntry, fetchEvents } from '../lib/api';

export function useEventStream(pollInterval = 5000) {
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const pollTimer = useRef<number>();

  useEffect(() => {
    const schedulePolling = () => {
      // Clear any existing timer
      if (pollTimer.current) {
        window.clearInterval(pollTimer.current);
      }

      const poll = () => {
        fetchEvents()
          .then((res) => {
            setEvents(res.events);
            setError(null);
            setConnected(true);
          })
          .catch((err) => {
            setError((err as Error).message);
            setConnected(false);
          });
      };

      // Initial poll
      poll();

      // Set up interval polling
      pollTimer.current = window.setInterval(poll, pollInterval);
    };

    schedulePolling();

    // Cleanup on unmount
    return () => {
      if (pollTimer.current) {
        window.clearInterval(pollTimer.current);
      }
    };
  }, [pollInterval]);

  return { events, connected, error };
}
