import type { VideoResource } from "../types";

interface Props {
  video: VideoResource;
}

const bilibiliSearchUrl = (video: VideoResource) => {
  const terms = [video.title, ...video.knowledge_points, ...video.keywords].filter(Boolean).slice(0, 4);
  return `https://search.bilibili.com/all?keyword=${encodeURIComponent(terms.join(" "))}`;
};

export function VideoRecommendationCard({ video }: Props) {
  return (
    <article className="video-recommendation-card title-only">
      <div className="video-recommendation-copy">
        <span className="video-label">相关B站学习视频</span>
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
        <div className="video-card-actions">
          <a href={video.file_url} target="_blank" rel="noreferrer">打开B站</a>
          <a href={bilibiliSearchUrl(video)} target="_blank" rel="noreferrer">搜索相似</a>
        </div>
      </div>
    </article>
  );
}
