import { useState } from "react";

import type { VideoResource } from "../types";

interface Props {
  video: VideoResource;
}

export function VideoRecommendationCard({ video }: Props) {
  const [playing, setPlaying] = useState(false);
  const isDemoVideo = video.file_url.startsWith("demo://");

  return (
    <article className="video-recommendation-card">
      <img
        className="video-cover"
        src={video.cover_url || "/media/videos/default-video-cover.svg"}
        alt={`${video.title}封面`}
      />
      <div className="video-recommendation-copy">
        <span className="video-label">相关学习视频</span>
        <strong>{video.title}</strong>
        <p>{video.description}</p>
        {video.recommendation_reason && (
          <small className="video-reason">推荐理由：{video.recommendation_reason}</small>
        )}
        <div className="video-meta-row">
          {video.knowledge_points.slice(0, 3).map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
        <button
          className="primary-action compact-action"
          type="button"
          onClick={() => setPlaying((value) => !value)}
        >
          {playing ? "收起视频" : "播放视频"}
        </button>
      </div>
      {playing && (
        isDemoVideo ? (
          <div className="demo-video-placeholder"><span>▶</span><strong>演示视频资源</strong><small>完整部署后可在网页内播放视频。</small></div>
        ) : (
          <video className="recommended-video-player" controls autoPlay preload="metadata">
            <source src={video.file_url} type="video/mp4" />
            当前浏览器不支持视频播放。
          </video>
        )
      )}
    </article>
  );
}
