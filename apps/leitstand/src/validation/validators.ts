export function validatePlexerReport(data: unknown): void {
  if (!data || typeof data !== 'object') {
    throw new Error('Invalid plexer report: must be an object');
  }
}
