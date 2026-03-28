import { readFile } from 'fs/promises';

export async function readJsonFile<T = unknown>(filePath: string): Promise<T> {
  const raw = await readFile(filePath, 'utf-8');
  return JSON.parse(raw) as T;
}
