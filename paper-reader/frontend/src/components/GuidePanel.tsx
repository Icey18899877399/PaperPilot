import type { Guide } from "../types";

interface Props {
  guide: Guide | null;
  loading: boolean;
  disabled: boolean;
  onGenerate: () => Promise<void>;
}

export function GuidePanel({ guide, loading, disabled, onGenerate }: Props) {
  return (
    <section className="guide-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">论文理解Agent</span>
          <h2>智能导读</h2>
        </div>
        <button disabled={disabled || loading} onClick={() => void onGenerate()}>
          {loading ? "生成中…" : guide ? "重新生成" : "生成导读"}
        </button>
      </div>
      {!guide ? (
        <p className="muted">上传论文后，由论文理解Agent提取研究问题、方法与阅读重点。</p>
      ) : (
        <div className="guide-content">
          <p>{guide.overview}</p>
          <h3>阅读重点</h3>
          <ul>{guide.key_points.map((point) => <li key={point}>{point}</li>)}</ul>
          <h3>建议思考</h3>
          <ul>{guide.reading_questions.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
    </section>
  );
}

