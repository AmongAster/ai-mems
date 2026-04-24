export type Meme = {
  id: number;
  caption: string | null;
  source: string;
  image_url: string;
  filename?: string;
};

const API_BASE =
  (import.meta as any).env?.VITE_API_BASE?.toString() || "http://localhost:8001";

export function apiBase() {
  return API_BASE.replace(/\/+$/, "");
}

async function parseJsonSafe(res: Response) {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

export async function getRandomMeme(): Promise<Meme> {
  const res = await fetch(`${apiBase()}/memes/random`);
  if (!res.ok) throw new Error(`random: ${res.status} ${JSON.stringify(await parseJsonSafe(res))}`);
  return (await res.json()) as Meme;
}

export async function test(): Promise<any> {
  const res = await fetch(`${apiBase()}/memes/test`);
  if (!res.ok) throw new Error(`test: ${res.status} ${JSON.stringify(await parseJsonSafe(res))}`);
  return (await res.json()) as any;
}

export async function fetchLatestTelegramMeme(): Promise<Meme> {
  const res = await fetch(`${apiBase()}/telegram/fetch_latest`, { method: "POST" });
  if (!res.ok)
    throw new Error(`telegram/fetch_latest: ${res.status} ${JSON.stringify(await parseJsonSafe(res))}`);
  return (await res.json()) as Meme;
}

export async function listMemes(limit = 50): Promise<Meme[]> {
  const res = await fetch(`${apiBase()}/memes?limit=${encodeURIComponent(limit)}`);
  if (!res.ok) throw new Error(`list: ${res.status} ${JSON.stringify(await parseJsonSafe(res))}`);
  return (await res.json()) as Meme[];
}

export async function importFromStorage(): Promise<{
  scanned: number;
  created: number;
  skipped_existing: number;
  skipped_unsupported: number;
}> {
  const res = await fetch(`${apiBase()}/memes/import_from_storage`, { method: "POST" });
  if (!res.ok) throw new Error(`import: ${res.status} ${JSON.stringify(await parseJsonSafe(res))}`);
  return (await res.json()) as any;
}

export async function clearGallery(): Promise<{
  deleted_rows: number;
  removed_storage_entries: number;
}> {
  const res = await fetch(`${apiBase()}/memes/clear`, { method: "POST" });
  if (!res.ok) throw new Error(`clear: ${res.status} ${JSON.stringify(await parseJsonSafe(res))}`);
  return (await res.json()) as any;
}

export async function generateMeme(prompt: string): Promise<Meme> {
  const form = new FormData();
  form.set("prompt", prompt);
  const res = await fetch(`${apiBase()}/memes/generate`, { method: "POST", body: form });
  if (!res.ok)
    throw new Error(`generate: ${res.status} ${JSON.stringify(await parseJsonSafe(res))}`);
  return (await res.json()) as Meme;
}

export async function uploadMeme(file: File, caption?: string): Promise<Meme> {
  const form = new FormData();
  form.set("file", file);
  if (caption) form.set("caption", caption);
  const res = await fetch(`${apiBase()}/memes/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`upload: ${res.status} ${JSON.stringify(await parseJsonSafe(res))}`);
  return (await res.json()) as Meme;
}

