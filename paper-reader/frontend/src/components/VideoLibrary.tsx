import { FormEvent, useMemo, useState } from "react";

import { api } from "../api";
import type { VideoResource, VideoUpdatePayload } from "../types";

interface Props {
  videos: VideoResource[];
  loading: boolean;
  onChanged: () => Promise<void>;
  embedded?: boolean;
}

interface FormState {
  title: string;
  description: string;
  source: string;
  videoUrl: string;
  coverUrl: string;
  keywords: string;
  tags: string;
  knowledgePoints: string;
}

const emptyForm: FormState = {
  title: "",
  description: "",
  source: "B站搜索",
  videoUrl: "",
  coverUrl: "",
  keywords: "",
  tags: "",
  knowledgePoints: ""
};

const join = (items: string[]) => items.join("，");
const split = (value: string) => value.split(/[,，;；\n]+/).map((item) => item.trim()).filter(Boolean);
const bilibiliSearchUrl = (video: VideoResource) => {
  const terms = [video.title, ...video.knowledge_points, ...video.keywords].filter(Boolean).slice(0, 4);
  return `https://search.bilibili.com/all?keyword=${encodeURIComponent(terms.join(" "))}`;
};

export function VideoLibrary({ videos, loading, onChanged, embedded = false }: Props) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const editingVideo = useMemo(
    () => videos.find((item) => item.id === editingId) ?? null,
    [editingId, videos]
  );

  const change = (key: keyof FormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const reset = () => {
    setEditingId(null);
    setForm(emptyForm);
    setError("");
  };

  const beginEdit = (video: VideoResource) => {
    setEditingId(video.id);
    setForm({
      title: video.title,
      description: video.description,
      source: video.source,
      videoUrl: video.file_url,
      coverUrl: video.cover_url.startsWith("/media/videos/") ? "" : video.cover_url,
      keywords: join(video.keywords),
      tags: join(video.tags),
      knowledgePoints: join(video.knowledge_points)
    });
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.title.trim() || submitting) return;

    setSubmitting(true);
    setError("");
    try {
      if (editingId) {
        const payload: VideoUpdatePayload = {
          title: form.title.trim(),
          description: form.description.trim(),
          source: form.source.trim() || "B站搜索",
          file_url: form.videoUrl.trim(),
          keywords: split(form.keywords),
          tags: split(form.tags),
          knowledge_points: split(form.knowledgePoints)
        };
        await api.updateVideo(editingId, payload);
      } else {
        const body = new FormData();
        body.append("title", form.title.trim());
        body.append("description", form.description.trim());
        body.append("source", form.source.trim() || "B站搜索");
        body.append("file_url", form.videoUrl.trim());
        body.append("cover_url", form.coverUrl.trim());
        body.append("keywords", form.keywords);
        body.append("tags", form.tags);
        body.append("knowledge_points", form.knowledgePoints);
        await api.createVideo(body);
      }
      reset();
      await onChanged();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (video: VideoResource) => {
    const confirmed = window.confirm(`确定删除视频资源“${video.title}”吗？`);
    if (!confirmed) return;
    setError("");
    try {
      await api.deleteVideo(video.id);
      if (editingId === video.id) reset();
      await onChanged();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  return (
    <section className={embedded ? "video-management-page embedded" : "content-page video-management-page"}>
      {!embedded && <header className="content-page-header">
        <div>
          <span className="eyebrow">US-08 · B站视频资源管理</span>
          <h1>学习视频库</h1>
          <p>维护B站视频链接、搜索词、来源、关键词、标签与关联知识点；聊天Agent按元数据推荐可打开的B站资源。</p>
        </div>
        <span className="ready-badge">{videos.length} 个资源</span>
      </header>}

      <form className="video-admin-form" onSubmit={submit}>
        <div className="video-form-heading">
          <div>
            <strong>{editingVideo ? `编辑：${editingVideo.title}` : "新增B站视频资源"}</strong>
            <small>{editingVideo ? "可更新B站链接或搜索入口。" : "链接留空时，会根据标题和知识点生成B站搜索入口。"}</small>
          </div>
          {editingVideo && <button type="button" onClick={reset}>取消编辑</button>}
        </div>

        <div className="video-form-grid">
          <label>
            <span>标题 *</span>
            <input value={form.title} onChange={(event) => change("title", event.target.value)} required />
          </label>
          <label>
            <span>来源说明 *</span>
            <input value={form.source} onChange={(event) => change("source", event.target.value)} required />
          </label>
          <label className="wide-field">
            <span>B站视频链接或搜索词</span>
            <input
              value={form.videoUrl}
              onChange={(event) => change("videoUrl", event.target.value)}
              placeholder="例如 https://www.bilibili.com/video/...，或 Transformer 注意力 教程"
            />
          </label>
          <label className="wide-field">
            <span>简介</span>
            <textarea value={form.description} onChange={(event) => change("description", event.target.value)} rows={3} />
          </label>
          <label>
            <span>关键词（逗号分隔）</span>
            <input value={form.keywords} onChange={(event) => change("keywords", event.target.value)} placeholder="transformer，attention，注意力" />
          </label>
          <label>
            <span>标签（逗号分隔）</span>
            <input value={form.tags} onChange={(event) => change("tags", event.target.value)} placeholder="深度学习，NLP，论文精读" />
          </label>
          <label className="wide-field">
            <span>关联知识点（逗号分隔） *</span>
            <input value={form.knowledgePoints} onChange={(event) => change("knowledgePoints", event.target.value)} placeholder="Transformer，Self-Attention" required />
          </label>
          {!editingVideo && (
            <label className="wide-field">
              <span>封面图片链接（可选）</span>
              <input value={form.coverUrl} onChange={(event) => change("coverUrl", event.target.value)} placeholder="可粘贴B站封面或其他HTTP(S)图片链接" />
            </label>
          )}
        </div>

        {error && <div className="video-form-error">{error}</div>}
        <button className="primary-action" type="submit" disabled={submitting}>
          {submitting ? "保存中…" : editingVideo ? "保存修改" : "新增视频"}
        </button>
      </form>

      {loading ? (
        <p className="empty-copy">正在读取视频目录…</p>
      ) : (
        <div className="video-resource-grid">
          {videos.map((video) => (
            <article className="video-resource-card" key={video.id}>
              <img src={video.cover_url || "/media/videos/default-video-cover.svg"} alt={`${video.title}封面`} />
              <div className="video-resource-body">
                <span className="video-label">B站视频/搜索入口</span>
                <h3>{video.title}</h3>
                <p>{video.description || "暂无简介"}</p>
                <dl>
                  <div><dt>来源</dt><dd>{video.source}</dd></div>
                  <div><dt>知识点</dt><dd>{video.knowledge_points.join("、") || "未填写"}</dd></div>
                  <div><dt>链接</dt><dd title={video.file_url}>{video.file_url}</dd></div>
                </dl>
                <div className="video-meta-row">
                  {[...video.keywords, ...video.tags].slice(0, 6).map((item) => <span key={item}>{item}</span>)}
                </div>
                <div className="video-card-actions">
                  <a href={video.file_url} target="_blank" rel="noreferrer">打开B站</a>
                  <a href={bilibiliSearchUrl(video)} target="_blank" rel="noreferrer">搜索相似</a>
                  <button type="button" onClick={() => beginEdit(video)}>编辑</button>
                  <button type="button" className="danger-action" onClick={() => void remove(video)}>删除</button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
      {!loading && !videos.length && (
        <p className="empty-copy">视频目录为空，请使用上方表单新增B站链接或搜索入口。</p>
      )}
    </section>
  );
}
