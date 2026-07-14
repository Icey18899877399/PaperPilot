import { FormEvent, useState } from "react";

import { api } from "../api";

interface Props {
  paperId?: string;
}

export function TranslationPanel({ paperId }: Props) {
  const [source, setSource] = useState("");
  const [translated, setTranslated] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = source.trim();
    if (!paperId || !text || loading) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.translate(paperId, text);
      setTranslated(result.translated_text);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="translation-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">翻译Agent</span>
          <h2>中英对照</h2>
        </div>
      </div>
      <form onSubmit={submit}>
        <label>
          原文
          <textarea
            rows={4}
            value={source}
            onChange={(event) => setSource(event.target.value)}
            placeholder={paperId ? "粘贴论文段落进行学术翻译…" : "请先选择论文"}
            disabled={!paperId}
          />
        </label>
        <button disabled={!paperId || !source.trim() || loading} type="submit">
          {loading ? "翻译中…" : "翻译为中文"}
        </button>
      </form>
      {error && <p className="inline-error">{error}</p>}
      {translated && (
        <div className="translation-result">
          <strong>译文</strong>
          <p>{translated}</p>
        </div>
      )}
    </section>
  );
}
