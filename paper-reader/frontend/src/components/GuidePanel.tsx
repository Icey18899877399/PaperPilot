import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import { api } from "../api";
import type { Guide, GuidePromptInfo, GuideSection } from "../types";

interface Props {
  guide: Guide | null;
  loading: boolean;
  streamStatus?: string;
  disabled: boolean;
  onGenerate: (promptKey?: string) => Promise<void>;
  onLocate?: (page: number) => void;
  onAsk?: (question: string) => void;
}

const NOT_STATED = "原文未说明";

// 轻量内联SVG小图标，随小标题文字颜色（currentColor）自适应，无需引入图标库
const SparkIcon = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
    strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M13 2 4 13h7l-1 9 9-11h-7l1-9z" />
  </svg>
);

const OverviewIcon = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
    strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 5h16M4 10h16M4 15h11M4 20h8" />
  </svg>
);

const TagIcon = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
    strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20.6 13.4 12 22l-9-9V4h9l8.6 8.6a1.4 1.4 0 0 1 0 2z" />
    <circle cx="7.5" cy="7.5" r="1.3" />
  </svg>
);

// 九项字段各自的小图标（14px，stroke=currentColor，随标题色自适应）
const iconAttrs = {
  viewBox: "0 0 24 24",
  width: 14,
  height: 14,
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

const BackgroundIcon = () => (
  <svg {...iconAttrs}>
    <path d="M12 21s-7-6.3-7-11a7 7 0 0 1 14 0c0 4.7-7 11-7 11z" />
    <circle cx="12" cy="10" r="2.4" />
  </svg>
);
const QuestionIcon = () => (
  <svg {...iconAttrs}>
    <circle cx="12" cy="12" r="9" />
    <path d="M9.2 9.3a2.8 2.8 0 0 1 5.5.7c0 1.9-2.7 2.5-2.7 2.5" />
    <path d="M12 17h.01" />
  </svg>
);
const MethodIcon = () => (
  <svg {...iconAttrs}>
    <path d="M6 3v6M6 15v6M18 3v10M18 19v2M12 3v2M12 11v10" />
    <circle cx="6" cy="12" r="2.2" />
    <circle cx="18" cy="16" r="2.2" />
    <circle cx="12" cy="8" r="2.2" />
  </svg>
);
const ExperimentIcon = () => (
  <svg {...iconAttrs}>
    <path d="M9 3h6M10 3v6l-5.2 8.8A2 2 0 0 0 6.5 21h11a2 2 0 0 0 1.7-3.2L14 9V3" />
    <path d="M7.5 15h9" />
  </svg>
);
const ResultsIcon = () => (
  <svg {...iconAttrs}>
    <path d="M3 21h18" />
    <path d="M7 21v-7M12 21V4M17 21v-11" />
  </svg>
);
const InnovationIcon = () => (
  <svg {...iconAttrs}>
    <path d="M12 2a6 6 0 0 0-4 10.5c.9.9 1.5 1.8 1.5 2.5h5c0-.7.6-1.6 1.5-2.5A6 6 0 0 0 12 2z" />
    <path d="M9.5 20h5M10.5 22h3" />
  </svg>
);
const LimitationIcon = () => (
  <svg {...iconAttrs}>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4M12 17h.01" />
  </svg>
);

// US-02九项结构化导读的展示顺序、标题与图标（须在图标定义之后声明）
const SECTION_LABELS: Array<[keyof Guide, string, () => ReactElement]> = [
  ["background", "研究背景", BackgroundIcon],
  ["research_question", "研究问题", QuestionIcon],
  ["method", "核心方法", MethodIcon],
  ["experiment", "实验设计", ExperimentIcon],
  ["results", "主要结果", ResultsIcon],
  ["innovations", "创新点", InnovationIcon],
  ["limitations", "局限性", LimitationIcon],
];

function isSection(value: unknown): value is GuideSection {
  return Boolean(value) && typeof (value as GuideSection).content === "string";
}

function isMissing(section: GuideSection): boolean {
  return section.content === NOT_STATED || section.content.includes("暂无法生成");
}

export function GuidePanel({
  guide,
  loading,
  streamStatus,
  disabled,
  onGenerate,
  onLocate,
  onAsk,
}: Props) {
  const [prompts, setPrompts] = useState<GuidePromptInfo[]>([]);
  const [promptKey, setPromptKey] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    api
      .guidePrompts()
      .then((items) => {
        if (cancelled) return;
        setPrompts(items);
        const fallback = items.find((item) => item.is_default) ?? items[0];
        if (fallback) setPromptKey((current) => current || fallback.key);
      })
      .catch(() => setPrompts([]));
    return () => {
      cancelled = true;
    };
  }, []);

  const sections = guide
    ? SECTION_LABELS.flatMap(([field, label, Icon]) => {
        const value = guide[field];
        return isSection(value)
          ? ([[label, value, Icon]] as Array<[string, GuideSection, () => ReactElement]>)
          : [];
      })
    : [];
  const hasStructuredGuide = sections.length > 0 && Boolean(guide?.one_liner);
  const activePrompt = prompts.find((item) => item.key === promptKey);

  return (
    <section className="guide-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">论文理解Agent</span>
          <h2>智能导读</h2>
        </div>
        <div className="guide-actions">
          {prompts.length > 0 && (
            <select
              className="guide-prompt-select"
              value={promptKey}
              disabled={loading}
              onChange={(event) => setPromptKey(event.target.value)}
              aria-label="导读风格"
              title={activePrompt ? `${activePrompt.description}（面向${activePrompt.audience}）` : undefined}
            >
              {prompts.map((item) => (
                <option value={item.key} key={item.key}>
                  {item.name}
                </option>
              ))}
            </select>
          )}
          <button
            disabled={disabled || loading}
            onClick={() => void onGenerate(promptKey || undefined)}
          >
            {loading ? "生成中…" : guide ? "重新生成" : "生成导读"}
          </button>
        </div>
      </div>
      {loading && streamStatus && (
        <div className="guide-stream-status" role="status">
          <span />
          {streamStatus}
        </div>
      )}
      {!guide ? (
        <p className="muted">上传论文后，由论文理解Agent提取研究问题、方法与阅读重点。</p>
      ) : (
        <div className="guide-content">
          {guide.generator === "fallback" && (
            <p className="guide-degraded-tip">
              当前为无模型降级模式，以下内容为原文提取，配置模型后可重新生成完整导读。
            </p>
          )}
          {guide.one_liner && (
            <section className="guide-block">
              <div className="guide-subhead">
                <SparkIcon />
                <span>一句话概括</span>
              </div>
              <p className="guide-one-liner">{guide.one_liner}</p>
            </section>
          )}
          <section className="guide-block">
            <div className="guide-subhead">
              <OverviewIcon />
              <span>论文综述</span>
            </div>
            <p className="guide-overview">{guide.overview}</p>
          </section>
          {(guide.keywords?.length ?? 0) > 0 && (
            <section className="guide-block">
              <div className="guide-subhead">
                <TagIcon />
                <span>关键词</span>
              </div>
              <div className="guide-keywords">
                {guide.keywords!.map((keyword) => (
                  <span className="guide-keyword" key={keyword}>{keyword}</span>
                ))}
              </div>
            </section>
          )}
          {hasStructuredGuide && (
            <div className="guide-sections">
              {sections.map(([label, section, Icon]) => (
                <article
                  className={`guide-section${isMissing(section) ? " guide-section-missing" : ""}`}
                  key={label}
                >
                  <h3><Icon /><span>{label}</span></h3>
                  <p className={isMissing(section) ? "muted" : ""}>
                    {isMissing(section)
                      ? `${section.content} —— 系统不做推测补写。`
                      : section.content}
                  </p>
                  {section.citations.length > 0 && (
                    <div className="guide-citations">
                      {section.citations.map((citation, index) => (
                        <button
                          key={`${citation.section}-${citation.page}-${index}`}
                          className="guide-citation"
                          type="button"
                          disabled={!citation.page || !onLocate}
                          title={citation.section ? `跳转到 ${citation.section}` : undefined}
                          onClick={() => {
                            if (citation.page && onLocate) onLocate(citation.page);
                          }}
                        >
                          {citation.section ? `${citation.section} · ` : ""}
                          {citation.page ? `第${citation.page}页` : "章节引用"}
                        </button>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
          <div className="guide-footer-grid">
            <div>
              <h3>阅读重点</h3>
              <ol className="guide-key-points">
                {guide.key_points.map((point) => <li key={point}>{point}</li>)}
              </ol>
            </div>
            <div>
              <h3>建议思考{onAsk ? " · 点击可直接提问" : ""}</h3>
              <div className="guide-questions">
                {guide.reading_questions.map((item) =>
                  onAsk ? (
                    <button
                      className="guide-question"
                      type="button"
                      key={item}
                      onClick={() => onAsk(item)}
                    >
                      <span>{item}</span>
                      <svg viewBox="0 0 24 24" width="15" height="15" fill="none"
                        stroke="currentColor" strokeWidth={2} strokeLinecap="round"
                        strokeLinejoin="round" aria-hidden="true">
                        <path d="M5 12h14M13 6l6 6-6 6" />
                      </svg>
                    </button>
                  ) : (
                    <p key={item}>{item}</p>
                  ),
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
