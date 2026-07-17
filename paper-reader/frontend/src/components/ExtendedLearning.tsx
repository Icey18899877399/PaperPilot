import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { api } from "../api";
import type {
  LearningResource,
  LearningResourceType,
  LearningSearchResponse,
  Paper,
  VideoResource
} from "../types";
import { VideoLibrary } from "./VideoLibrary";

interface Props {
  papers: Paper[];
  activePaper: Paper | null;
  videos: VideoResource[];
  loading: boolean;
  onVideosChanged: () => Promise<void>;
}

type ResultFilter = "all" | LearningResourceType;
type SearchScope = "all" | "paper" | "article" | "video";

const examples: Array<{ text: string; scope?: SearchScope }> = [
  { text: "理解论文核心方法需要哪些前置知识？" },
  { text: "查找与这篇论文相关的综述和近期工作", scope: "paper" },
  { text: "在B站查找适合复习关键概念的视频或课程", scope: "video" }
];

const typeLabels: Record<LearningResourceType, string> = {
  paper: "相关论文",
  video: "视频",
  article: "文字资料",
  course: "课程",
  documentation: "文档",
  local: "自建资源"
};

const searchScopes: Array<{ value: SearchScope; label: string }> = [
  { value: "all", label: "全部" },
  { value: "paper", label: "相关论文" },
  { value: "article", label: "文字资料" },
  { value: "video", label: "视频与课程" }
];

const scopeTypes: Record<SearchScope, LearningResourceType[]> = {
  all: [],
  paper: ["paper"],
  article: ["article", "documentation"],
  video: ["video", "course"]
};

export function ExtendedLearning({
  papers,
  activePaper,
  videos,
  loading,
  onVideosChanged
}: Props) {
  const readyPapers = useMemo(
    () => papers.filter((item) => item.status === "ready"),
    [papers]
  );
  const [paperId, setPaperId] = useState(
    activePaper?.status === "ready" ? activePaper.id : ""
  );
  const [query, setQuery] = useState("");
  const [searchScope, setSearchScope] = useState<SearchScope>("all");
  const [result, setResult] = useState<LearningSearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<ResultFilter>("all");

  useEffect(() => {
    if (activePaper?.status === "ready") setPaperId(activePaper.id);
  }, [activePaper?.id, activePaper?.status]);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!query.trim() || searching) return;
    const hasVideoIntent = /b站|bilibili|视频|课程|教程/i.test(query);
    const hasPaperIntent = /论文|综述|近期工作|相关工作|survey|paper|related work/i.test(query);
    const effectiveScope = hasVideoIntent
      ? "video"
      : hasPaperIntent && searchScope === "video"
        ? "paper"
        : searchScope;
    if (effectiveScope !== searchScope) setSearchScope(effectiveScope);
    setSearching(true);
    setError("");
    setFilter("all");
    try {
      setResult(
        await api.searchLearning(
          query.trim(),
          paperId || null,
          scopeTypes[effectiveScope]
        )
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSearching(false);
    }
  };

  const visibleResources = result?.resources.filter(
    (item) => filter === "all" || item.resource_type === filter
  ) ?? [];
  const availableFilters = useMemo(() => {
    const values = new Set(result?.resources.map((item) => item.resource_type) ?? []);
    return ["all", ...Array.from(values)] as ResultFilter[];
  }, [result]);

  return (
    <section className="content-page extended-learning-page">
      <header className="learning-hero">
        <div>
          <span className="eyebrow">围绕论文继续学习</span>
          <h1>拓展学习</h1>
          <p>从当前论文和问题出发，检索相关论文、文字资料、B站视频、公开视频和课程资源。</p>
        </div>
        <div className="learning-hero-status">
          <strong>全站</strong>
          <span>B站公开视频 + 公开视频/课程入口 + {videos.length} 项收藏链接</span>
        </div>
      </header>

      <form className="learning-search-panel" onSubmit={(event) => void submit(event)}>
        <div className="learning-context-row">
          <label>
            <span>关联论文</span>
            <select value={paperId} onChange={(event) => setPaperId(event.target.value)}>
              <option value="">不限定论文，按问题检索</option>
              {readyPapers.map((item) => (
                <option key={item.id} value={item.id}>{item.filename}</option>
              ))}
            </select>
          </label>
          <div className="learning-type-selector" aria-label="检索范围">
            <span>检索范围（单选）</span>
            {searchScopes.map((scope) => (
              <button
                key={scope.value}
                type="button"
                aria-pressed={searchScope === scope.value}
                className={searchScope === scope.value ? "active" : ""}
                onClick={() => setSearchScope(scope.value)}
              >
                {scope.label}
              </button>
            ))}
          </div>
        </div>
        <div className="learning-query-row">
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：这篇论文的方法需要哪些前置知识？请查找相关综述、教程和视频。"
            rows={3}
          />
          <button className="learning-search-button" type="submit" disabled={!query.trim() || searching}>
            {searching ? "检索中…" : "开始检索"}
          </button>
        </div>
        <div className="learning-examples">
          <span>示例</span>
          {examples.map((example) => (
            <button
              key={example.text}
              type="button"
              onClick={() => {
                setQuery(example.text);
                if (example.scope) setSearchScope(example.scope);
              }}
            >
              {example.text}
            </button>
          ))}
        </div>
      </form>

      {error && <div className="error-banner">{error}</div>}

      {result && (
        <>
          <section className="learning-search-summary">
            <header>
              <h2>检索摘要</h2>
              <span>{result.resources.length} 项结果</span>
            </header>
            <p>{result.summary}</p>
            {result.learning_path.length > 0 && (
              <div className="learning-sequence">
                <strong>建议阅读顺序</strong>
                <ol>
                  {result.learning_path.map((step) => <li key={step}>{step}</li>)}
                </ol>
              </div>
            )}
            <div className="learning-source-status">
              <strong>来源状态</strong>
              {result.providers.map((provider) => (
                <span
                  key={provider.provider}
                  className={provider.success ? "source-ok" : "source-error"}
                  title={provider.message}
                >
                  {provider.provider}：{provider.enabled
                    ? (provider.success ? "可用" : "已降级")
                    : provider.message || "未启用"}
                </span>
              ))}
            </div>
          </section>

          <nav className="learning-result-filters" aria-label="检索结果筛选">
            {availableFilters.map((value) => (
              <button
                type="button"
                key={value}
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
              >
                {value === "all" ? "全部结果" : typeLabels[value]}
              </button>
            ))}
          </nav>

          <section className="learning-results-section">
            <header>
              <h2>检索结果</h2>
              <span>按相关性排列</span>
            </header>
            <ol className="learning-resource-list">
              {visibleResources.map((resource, index) => (
                <LearningResourceRow
                  key={resource.id}
                  resource={resource}
                  index={index + 1}
                />
              ))}
            </ol>
          </section>
          {!visibleResources.length && (
            <p className="empty-copy">当前范围没有返回资源，请调整问题或检索范围。</p>
          )}
        </>
      )}

      <details className="local-resource-manager">
        <summary>
          <span><strong>收藏的B站视频</strong><small>可选维护常用链接；公开搜索会自动覆盖B站全站视频。</small></span>
          <span>{videos.length} 项收藏</span>
        </summary>
        <VideoLibrary
          embedded
          videos={videos}
          loading={loading}
          onChanged={onVideosChanged}
        />
      </details>
    </section>
  );
}

function LearningResourceRow({
  resource,
  index
}: {
  resource: LearningResource;
  index: number;
}) {
  return (
    <li className="learning-resource-row">
      <span className="learning-resource-index">{String(index).padStart(2, "0")}</span>
      {resource.thumbnail_url && !resource.source.includes("B站") && <img src={resource.thumbnail_url} alt="" />}
      <div className="learning-resource-main">
        <div className="learning-resource-meta">
          <span>{typeLabels[resource.resource_type]}</span>
          <span>{resource.source}</span>
          {resource.published_year && <span>{resource.published_year}</span>}
        </div>
        <h3>
          <a href={resource.url} target="_blank" rel="noreferrer">{resource.title}</a>
        </h3>
        {resource.authors.length > 0 && (
          <p className="learning-authors">{resource.authors.slice(0, 4).join("、")}</p>
        )}
        <p className="learning-resource-description">
          {resource.description || "来源未提供摘要，可打开原始页面查看。"}
        </p>
        <p className="learning-match-reason">
          <strong>匹配依据：</strong>{resource.relevance_reason}
        </p>
      </div>
      <a className="learning-resource-open" href={resource.url} target="_blank" rel="noreferrer">
        {resource.local ? "打开" : "原文"} ↗
      </a>
    </li>
  );
}
