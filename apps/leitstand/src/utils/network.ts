const LOOPBACK_RANGES = ['127.', '::1', 'localhost'];

export function isLoopbackAddress(addr: string): boolean {
  return LOOPBACK_RANGES.some((prefix) => addr.startsWith(prefix));
}
