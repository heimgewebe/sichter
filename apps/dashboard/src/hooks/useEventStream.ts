import { useEffect, useRef, useState } from 'react';
import { EventEntry, fetchEvents } from '../lib/api';

function parseLine(line: string): EventEntry {
  try {
    const obj = JSON.parse(line);
    if (obj && typeof obj === 'object') {
      return { line, ts: (obj as any).ts, kind: (obj as any).type ?? (obj as any).event, payload: obj };
    }
  } catch {
    // ignore
  }
  return { line };
}

export function useEventStream(pollInterval = 5000) {
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false); // true => WebSocket; false => Polling
  const pollTimer = useRef<number>();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const base = (import.meta as any).env?.VITE_API_BASE ?? window.location.origin;

    const startPolling = () => {
      setConnected(false);
      if (pollTimer.current) window.clearInterval(pollTimer.current);
      // initial
      fetchEvents()
        .then((res) => {
          setEvents(res.events);
          setError(null);
        })
        .catch((err) => setError((err as Error).message));
      // interval
      pollTimer.current = window.setInterval(() => {
        fetchEvents()
          .then((res) => {
            setEvents(res.events);
            setError(null);
          })
          .catch((err) => setError((err as Error).message));
      }, pollInterval);
    };

    const tryWebSocket = () => {
      try {
        const url = new URL('/events/stream?replay=100&heartbeat=15', base);
        url.protocol = url.protocol.replace('http', 'ws');
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          setConnected(true);
          setError(null);
          // beim Wechsel auf WS: Polling sicher beenden
          if (pollTimer.current) window.clearInterval(pollTimer.current);
        };
        ws.onmessage = (msg) => {
          const entry = parseLine(String(msg.data ?? ''));
          setEvents((prev) => {
            const next = [...prev, entry];
            return next.slice(-200);
          });
        };
        ws.onerror = () => {
          // in den Fallback; close triggert onclose
        };
        ws.onclose = () => {
          setConnected(false);
          wsRef.current = null;
          // Fallback aktivieren
          startPolling();
        };
      } catch (err) {
        setError((err as Error).message);
        startPolling();
      }
    };

    // zuerst WS versuchen
    tryWebSocket();

    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
      wsRef.current?.close();
    };
  }, [pollInterval]);

  return { events, connected, error };
}
