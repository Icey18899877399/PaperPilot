import type { VideoResource } from "../types";

interface Props {
  video: VideoResource;
}

export function VideoPlayer({ video }: Props) {
  return (
    <article className="video-card">
      <div className="video-copy">
        <span className="video-label">相关学习视频</span>
        <strong>{video.title}</strong>
        <p>{video.description}</p>
      </div>
      <video controls preload="metadata">
        <source src={video.file_url} type="video/mp4" />
        当前浏览器不支持视频播放。
      </video>
    </article>
  );
}

