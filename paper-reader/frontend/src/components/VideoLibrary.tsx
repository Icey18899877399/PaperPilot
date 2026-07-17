import { FormEvent, useMemo, useState } from "react";

import { api } from "../api";
import type { VideoResource, VideoUpdatePayload } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

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
  keywords: string;
  tags: string;
  knowledgePoints: string;
  localPath: string;
}

const emptyForm: FormState = {
  title: "",
  description: "",
  source: "本地维护",
  keywords: "",
  tags: "",
  knowledgePoints: "",
  localPath: ""
};

const join = (items: string[]) => items.join("，");
const split = (value: string) => value.split(/[,，;；\n]+/).map((item) => item.trim()).filter(Boolean);

export function VideoLibrary({ videos, loading, onChanged, embedded = false }: Props) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [pendingRemove, setPendingRemove] = useState<VideoResource | null>(null);
  const [alsoDeleteFile, setAlsoDeleteFile] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [formVersion, setFormVersion] = useState(0);

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
    setVideoFile(null);
    setCoverFile(null);
    setError("");
    setFormVersion((value) => value + 1);
  };

  const beginEdit = (video: VideoResource) => {
    setEditingId(video.id);
    setForm({
      title: video.title,
      description: video.description,
      source: video.source,
      keywords: join(video.keywords),
      tags: join(video.tags),
      knowledgePoints: join(video.knowledge_points),
      localPath: video.local_path
    });
    setVideoFile(null);
    setCoverFile(null);
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.title.trim() || submitting) return;
    if (!editingId && !videoFile && !form.localPath.trim()) {
      setError("请上传MP4文件，或填写后端视频目录中已有的本地MP4文件名/路径。");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      if (editingId) {
        const payload: VideoUpdatePayload = {
          title: form.title.trim(),
          description: form.description.trim(),
          source: form.source.trim() || "本地维护",
          keywords: split(form.keywords),
          tags: split(form.tags),
          knowledge_points: split(form.knowledgePoints)
        };
        await api.updateVideo(editingId, payload);
      } else {
        const body = new FormData();
        body.append("title", form.title.trim());
        body.append("description", form.description.trim());
        body.append("source", form.source.trim() || "本地维护");
        body.append("keywords", form.keywords);
        body.append("tags", form.tags);
        body.append("knowledge_points", form.knowledgePoints);
        body.append("local_path", form.localPath.trim());
        if (videoFile) body.append("file", videoFile);
        if (coverFile) body.append("cover", coverFile);
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

  const confirmRemove = async () => {
    const video = pendingRemove;
    if (!video) return;
    setRemoving(true);
    setError("");
    try {
      await api.deleteVideo(video.id, alsoDeleteFile);
      if (editingId === video.id) reset();
      if (previewId === video.id) setPreviewId(null);
      setPendingRemove(null);
      await onChanged();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setRemoving(false);
    }
  };

  return (
    <section className={embedded ? "video-management-page embedded" : "content-page video-management-page"}>
      {!embedded && <header className="content-page-header">
        <div>
          <span className="eyebrow">US-08 · 本地视频资源管理</span>
          <h1>学习视频库</h1>
          <p>维护MP4、封面、来源、关键词、标签与关联知识点；聊天Agent仅依据这些元数据推荐视频。</p>
        </div>
        <span className="ready-badge">{videos.length} 个资源</span>
      </header>}

      <form className="video-admin-form" onSubmit={submit}>
        <div className="video-form-heading">
          <div>
            <strong>{editingVideo ? `编辑：${editingVideo.title}` : "新增视频资源"}</strong>
            <small>{editingVideo ? "编辑元数据不会替换现有MP4文件。" : "支持上传MP4，或登记后端视频目录中已有文件。"}</small>
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
            <span>简介</span>
            <textarea value={form.description} onChange={(event) => change("description", event.target.value)} rows={3} />
          </label>
          <label>
            <span>关键词（逗号分隔）</span>
            <input value={form.keywords} onChange={(event) => change("keywords", event.target.value)} placeholder="transformer，attention，注意力" />
          </label>
          <label>
            <span>标签（逗号分隔）</span>
            <input value={form.tags} onChange={(event) => change("tags", event.target.value)} placeholder="深度学习，NLP" />
          </label>
          <label className="wide-field">
            <span>关联知识点（逗号分隔） *</span>
            <input value={form.knowledgePoints} onChange={(event) => change("knowledgePoints", event.target.value)} placeholder="Transformer，Self-Attention" required />
          </label>
          {!editingVideo && (
            <>
              <label>
                <span>上传MP4</span>
                <input key={`video-${formVersion}`} type="file" accept="video/mp4,.mp4" onChange={(event) => setVideoFile(event.target.files?.[0] ?? null)} />
              </label>
              <label>
                <span>上传封面（可选）</span>
                <input key={`cover-${formVersion}`} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={(event) => setCoverFile(event.target.files?.[0] ?? null)} />
              </label>
              <label className="wide-field">
                <span>或登记本地MP4路径/文件名</span>
                <input value={form.localPath} onChange={(event) => change("localPath", event.target.value)} placeholder="例如 transformer-demo.mp4" />
              </label>
            </>
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
                <span className="video-label">本地MP4资源</span>
                <h3>{video.title}</h3>
                <p>{video.description || "暂无简介"}</p>
                <dl>
                  <div><dt>来源</dt><dd>{video.source}</dd></div>
                  <div><dt>知识点</dt><dd>{video.knowledge_points.join("、") || "未填写"}</dd></div>
                  <div><dt>本地文件</dt><dd title={video.local_path}>{video.local_path}</dd></div>
                </dl>
                <div className="video-meta-row">
                  {[...video.keywords, ...video.tags].slice(0, 6).map((item) => <span key={item}>{item}</span>)}
                </div>
                <div className="video-card-actions">
                  <button type="button" onClick={() => setPreviewId(previewId === video.id ? null : video.id)}>
                    {previewId === video.id ? "收起预览" : "预览播放"}
                  </button>
                  <button type="button" onClick={() => beginEdit(video)}>编辑</button>
                  <button
                    type="button"
                    className="danger-action"
                    onClick={() => {
                      setAlsoDeleteFile(false);
                      setPendingRemove(video);
                    }}
                  >删除</button>
                </div>
              </div>
              {previewId === video.id && (
                video.file_url.startsWith("demo://") ? (
                  <div className="demo-video-placeholder"><span>▶</span><strong>演示视频资源</strong><small>静态站点不包含本地 MP4 文件。</small></div>
                ) : (
                  <video className="video-library-player" controls autoPlay preload="metadata">
                    <source src={video.file_url} type="video/mp4" />
                    当前浏览器不支持视频播放。
                  </video>
                )
              )}
            </article>
          ))}
        </div>
      )}
      {!loading && !videos.length && (
        <p className="empty-copy">视频目录为空，请使用上方表单上传或登记MP4资源。</p>
      )}
      <ConfirmDialog
        open={pendingRemove !== null}
        title={`删除视频「${pendingRemove?.title ?? ""}」？`}
        body={
          <>
            <p style={{ margin: 0 }}>删除后聊天推荐将不再出现该视频。</p>
            <label>
              <input
                type="checkbox"
                checked={alsoDeleteFile}
                onChange={(event) => setAlsoDeleteFile(event.target.checked)}
              />
              同时删除后端本地 MP4 文件（不勾选则仅移除目录记录）
            </label>
          </>
        }
        confirmText="删除"
        danger
        busy={removing}
        onConfirm={() => void confirmRemove()}
        onCancel={() => setPendingRemove(null)}
      />
    </section>
  );
}
