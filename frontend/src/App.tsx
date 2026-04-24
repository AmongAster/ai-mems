import { useEffect, useMemo, useState } from "react";
import {
  Meme,
  apiBase,
  generateMeme,
  getRandomMeme,
  importFromStorage,
  listMemes,
  uploadMeme,
} from "./api";

type Toast = { kind: "ok" | "err"; text: string } | null;

function formatSource(s?: string) {
  if (!s) return "—";
  if (s === "ai") return "AI";
  if (s === "upload") return "Upload";
  if (s === "import") return "Import";
  return s;
}

export default function App() {
  const [current, setCurrent] = useState<Meme | null>(null);
  const [gallery, setGallery] = useState<Meme[]>([]);
  const [prompt, setPrompt] = useState("Сделай мем про дедлайны и кофе");
  const [caption, setCaption] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast>(null);

  const imageUrl = useMemo(() => {
    if (!current) return null;
    return `${apiBase()}${current.image_url}`;
  }, [current]);

  async function refreshGallery() {
    const memes = await listMemes(50);
    setGallery(memes);
  }

  async function action(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setToast(null);
    try {
      await fn();
      setToast({ kind: "ok", text: "Готово" });
    } catch (e: any) {
      setToast({ kind: "err", text: e?.message || String(e) });
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    action("init", async () => {
      await refreshGallery();
      const r = await getRandomMeme();
      setCurrent(r);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page">
      <header className="header">
        <div className="brand">
          <div className="logo">ai</div>
          <div className="titles">
            <div className="title">ai-mems</div>
            <div className="subtitle">
              Backend: <span className="mono">{apiBase()}</span> · Swagger:{" "}
              <a className="link" href={`${apiBase()}/docs`} target="_blank" rel="noreferrer">
                /docs
              </a>
            </div>
          </div>
        </div>
        <div className="actions">
          <button
            className="btn primary"
            disabled={!!busy}
            onClick={() =>
              action("random", async () => {
                const r = await getRandomMeme();
                setCurrent(r);
                await refreshGallery();
              })
            }
          >
            {busy === "random" ? "..." : "Рандомный мем"}
          </button>

          <button
            className="btn"
            disabled={!!busy}
            onClick={() =>
              action("import", async () => {
                await importFromStorage();
                await refreshGallery();
              })
            }
          >
            {busy === "import" ? "..." : "Импорт из storage"}
          </button>
        </div>
      </header>

      <main className="grid">
        <section className="card hero">
          <div className="cardHeader">
            <div className="cardTitle">Просмотр</div>
            <div className="pill">{current ? formatSource(current.source) : "—"}</div>
          </div>

          <div className="viewer">
            {imageUrl ? (
              <img className="img" src={imageUrl} alt="meme" />
            ) : (
              <div className="placeholder">Нажми “Рандомный мем”</div>
            )}
          </div>

          <div className="meta">
            <div className="metaRow">
              <span className="metaKey">id</span>
              <span className="mono">{current?.id ?? "—"}</span>
            </div>
            <div className="metaRow">
              <span className="metaKey">caption</span>
              <span className="metaVal">{current?.caption ?? "—"}</span>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="cardHeader">
            <div className="cardTitle">AI генерация</div>
            <div className="hint">POST /memes/generate</div>
          </div>

          <label className="field">
            <div className="label">Промпт</div>
            <textarea
              className="input textarea"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Например: сделай мем про учебу и понедельник"
              rows={4}
            />
          </label>

          <button
            className="btn primary"
            disabled={!!busy || prompt.trim().length === 0}
            onClick={() =>
              action("generate", async () => {
                const r = await generateMeme(prompt.trim());
                setCurrent(r);
                await refreshGallery();
              })
            }
          >
            {busy === "generate" ? "..." : "Сгенерировать мем"}
          </button>
        </section>

        <section className="card">
          <div className="cardHeader">
            <div className="cardTitle">Загрузка</div>
            <div className="hint">POST /memes/upload</div>
          </div>

          <label className="field">
            <div className="label">Файл</div>
            <input
              className="input"
              type="file"
              accept="image/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>

          <label className="field">
            <div className="label">Подпись (опционально)</div>
            <input
              className="input"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Например: мой мем"
            />
          </label>

          <button
            className="btn"
            disabled={!!busy || !file}
            onClick={() =>
              action("upload", async () => {
                if (!file) return;
                const r = await uploadMeme(file, caption.trim() || undefined);
                setCurrent(r);
                setCaption("");
                setFile(null);
                await refreshGallery();
              })
            }
          >
            {busy === "upload" ? "..." : "Загрузить"}
          </button>
        </section>

        <section className="card gallery">
          <div className="cardHeader">
            <div className="cardTitle">Галерея</div>
            <div className="hint">{gallery.length} шт.</div>
          </div>

          <div className="thumbs">
            {gallery.map((m) => {
              const url = `${apiBase()}${m.image_url}`;
              const active = current?.id === m.id;
              return (
                <button
                  key={m.id}
                  className={`thumb ${active ? "active" : ""}`}
                  onClick={() => setCurrent(m)}
                  title={`id=${m.id} · ${formatSource(m.source)}`}
                >
                  <img src={url} alt={`meme ${m.id}`} />
                  <div className="thumbBar">
                    <span className="mono">#{m.id}</span>
                    <span className="pill small">{formatSource(m.source)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      </main>

      <footer className="footer">
        <div className="left">
          {toast ? (
            <div className={`toast ${toast.kind}`}>
              <span className="dot" />
              <span className="text">{toast.text}</span>
            </div>
          ) : (
            <div className="muted">Готов к работе.</div>
          )}
        </div>
        <div className="right muted">
          {busy ? (
            <span>
              Запрос: <span className="mono">{busy}</span>
            </span>
          ) : (
            <span>—</span>
          )}
        </div>
      </footer>
    </div>
  );
}

