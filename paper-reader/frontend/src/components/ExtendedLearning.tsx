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

const examples = [
  "帮我找理解论文核心方法所需的入门资料",
  "推荐与这篇论文最相关的综述和近期工作",
  "有没有适合复习关键概念的视频或课程？"
];

const typeLabels: Record<LearningResourceType, string> = {
  paper: "相关论文",
  video: "视频",
  article: "文字资料",
  course: "课程",
  documentation: "文档",
  local: "本地资源"
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
  const [selectedTypes, setSelectedTypes] = useState<LearningResourceType[]>([
    "paper",
    "video",
    "article"
  ]);
  const [result, setResult] = useState<LearningSearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<ResultFilter>("all");

  useEffect(() => {
    if (activePaper?.status === "ready") setPaperId(activePaper.id);
  }, [activePaper?.id, activePaper?.status]);

  const toggleType = (type: LearningResourceType) => {
    setSelectedTypes((current) =>
      current.includes(type)
        ? current.filter((item) => item !== type)
        : [...current, type]
    );
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!query.trim() || searching) return;
    setSearching(true);
    setError("");
    setFilter("all");
    try {
      setResult(await api.searchLearning(query.trim(), paperId || null, selectedTypes));
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
          <span className="eyebrow">EXPANSION LEARNING AGENT</span>
          <h1>拓展学习</h1>
          <p>从当前论文出发，由AI拆解学习目标，并检索相关论文、文字资料、视频课程和本地资源。</p>
        </div>
        <div className="learning-hero-status">
          <strong>{videos.length}</strong>
          <span>项本地视频可参与推荐</span>
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
          <div className="learning-type-selector" aria-label="资源类型">
            <span>检索类型</span>
            {(["paper", "article", "video", "course"] as LearningResourceType[]).map((type) => (
              <button
                key={type}
                type="button"
                className={selectedTypes.includes(type) ? "active" : ""}
                onClick={() => toggleType(type)}
              >
                {typeLabels[type]}
              </button>
            ))}
          </div>
        </div>
        <div className="learning-query-row">
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：这篇论文的方法需要哪些前置知识？请推荐相关综述、教程和视频。"
            rows={3}
          />
          <button className="learning-search-button" type="submit" disabled={!query.trim() || searching}>
            {searching ? "AI检索中…" : "AI查询学习资料"}
          </button>
        </div>
        <div className="learning-examples">
          <span>可以这样问</span>
          {examples.map((example) => (
            <button key={example} type="button" onClick={() => setQuery(example)}>{example}</button>
          ))}
        </div>
      </form>

      {error && <div className="error-banner">{error}</div>}

      {!result && !searching && (
        <div className="learning-capabilities">
          <article><span>01</span><strong>理解当前论文</strong><p>结合论文标题、相关段落和用户问题生成检索词，不再只依赖手工标签。</p></article>
          <article><span>02</span><strong>跨来源发现</strong><p>统一查询学术论文、本地视频和可配置的视频平台，并保留真实来源链接。</p></article>
          <article><span>03</span><strong>形成学习路径</strong><p>AI只基于检索到的候选资源整理先学什么、再看什么以及为什么相关。</p></article>
        </div>
      )}

      {result && (
        <>
          <section className="learning-guidance-card">
            <div className="learning-guidance-heading">
              <div>
                <span className="eyebrow">AI LEARNING GUIDE</span>
                <h2>拓展学习建议</h2>
              </div>
              <span className="learning-result-count">{result.resources.length} 项可追溯资源</span>
            </div>
            <p>{result.summary}</p>
            <ol>
              {result.learning_path.map((step) => <li key={step}>{step}</li>)}
            </ol>
            <div className="learning-provider-row">
              {result.providers.map((provider) => (
                <span
                  key={provider.provider}
                  className={provider.success ? "provider-ok" : "provider-error"}
                  title={provider.message}
                >
                  {provider.provider} · {provider.enabled ? (provider.success ? "已连接" : "已降级") : provider.message || "未启用"}
                </span>
              ))}
            </div>
          </section>

          <nav className="learning-result-filters" aria-label="拓展学习资源筛选">
            {availableFilters.map((value) => (
              <button
                type="button"
                key={value}
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
              >
                {value === "all" ? "全部资源" : typeLabels[value]}
              </button>
            ))}
          </nav>

          <div className="learning-resource-grid">
            {visibleResources.map((resource) => (
              <LearningResourceCard key={resource.id} resource={resource} />
            ))}
          </div>
          {!visibleResources.length && <p className="empty-copy">当前筛选条件下没有返回资源，请调整问题或资源类型。</p>}
        </>
      )}

      <details className="local-resource-manager">
        <summary>
          <span><strong>本地视频资源</strong><small>上传、编辑或登记已有MP4，作为拓展学习的私有资料来源。</small></span>
          <span>{videos.length} 项</span>
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

function LearningResourceCard({ resource }: { resource: LearningResource }) {
  return (
    <article className="learning-resource-card">
      {resource.thumbnail_url ? (
        <img src={resource.thumbnail_url} alt="" />
      ) : (
        <div className={`learning-resource-placeholder type-${resource.resource_type}`}>
          {resource.resource_type === "paper" ? "PDF" : resource.resource_type === "video" ? "▶" : "TXT"}
        </div>
      )}
      <div className="learning-resource-content">
        <div className="learning-resource-meta">
          <span>{typeLabels[resource.resource_type]}</span>
          <span>{resource.source}</span>
          {resource.published_year && <span>{resource.published_year}</span>}
        </div>
        <h3>{resource.title}</h3>
        {resource.authors.length > 0 && <p className="learning-authors">{resource.authors.slice(0, 4).join("、")}</p>}
        <p>{resource.description || "该来源暂未提供摘要，可打开原始页面查看完整内容。"}</p>
        <div className="learning-reason"><strong>为什么推荐</strong><span>{resource.relevance_reason}</span></div>
        {resource.tags.length > 0 && (
          <div className="learning-resource-tags">
            {resource.tags.slice(0, 5).map((tag) => <span key={tag}>{tag}</span>)}
          </div>
        )}
        <a href={resource.url} target="_blank" rel="noreferrer">
          {resource.local ? "打开本地资源" : "查看原始来源"} ↗
        </a>
      </div>
    </article>
  );
}
