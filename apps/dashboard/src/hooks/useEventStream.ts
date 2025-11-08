import { useEffect, useRef, useState } from 'react';

import { EventEntry, fetchEvents } from '../lib/api';

export function useEventStream(path = '/events/tail', pollInterval = 5000) {
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const pollTimer = useRef<number>();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connectWebSocket = () => {
      try {
        const base = import.meta.env.VITE_API_BASE ?? window.location.origin;
        const url = new URL(path, base);
        url.protocol = url.protocol.replace('http', 'ws');
        const socket = new WebSocket(url);
        wsRef.current = socket;

        socket.onopen = () => {
          setConnected(true);
          setError(null);
        };

        socket.onmessage = (message) => {
          setEvents((prev) => {
            const next = [...prev, { line: message.data as string }];
            return next.slice(-200);
          });
        };

        socket.onerror = () => {
          setConnected(false);
        };

        socket.onclose = () => {
          setConnected(false);
          wsRef.current = null;
          schedulePolling();
        };
      } catch (err) {
        setError((err as Error).message);
        schedulePolling();
      }
    };

    const schedulePolling = () => {
      if (pollTimer.current) {
        window.clearInterval(pollTimer.current);
      }
      void fetchEvents().then((res) => {
        setEvents(res.events);
      });
      pollTimer.current = window.setInterval(() => {
        fetchEvents()
          .then((res) => {
            setEvents(res.events);
            setError(null);
          })
          .catch((err) => setError((err as Error).message));
      }, pollInterval);
    };

    connectWebSocket();

    return () => {
      if (pollTimer.current) {
        window.clearInterval(pollTimer.current);
      }
      wsRef.current?.close();
    };
  }, [path, pollInterval]);

  return { events, connected, error };
}
