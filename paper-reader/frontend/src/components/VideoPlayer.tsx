import type { VideoResource } from "../types";

interface Props {
  video: VideoResource;
}

export function VideoPlayer({ video }: Props) {
  return (
    <article className="video-card">
      <div className="video-copy">
        <span className="video-label">相关B站学习视频</span>
        <strong>{video.title}</strong>
        <p>{video.description}</p>
      </div>
      <a className="primary-action compact-action" href={video.file_url} target="_blank" rel="noreferrer">
        打开B站
      </a>
    </article>
  );
}
