import type { VideoResource } from "../types";
import { VideoPlayer } from "./VideoPlayer";

interface Props {
  videos: VideoResource[];
  loading: boolean;
}

export function VideoLibrary({ videos, loading }: Props) {
  return (
    <section className="content-page">
      <header className="content-page-header">
        <div>
          <span className="eyebrow">本地视频资源</span>
          <h1>学习视频库</h1>
          <p>聊天Agent根据问题关键词推荐资源，视频直接在网页内本地播放。</p>
        </div>
      </header>
      {loading ? (
        <p className="empty-copy">正在读取视频目录…</p>
      ) : (
        <div className="video-grid">
          {videos.map((video) => <VideoPlayer key={video.id} video={video} />)}
        </div>
      )}
      {!loading && !videos.length && (
        <p className="empty-copy">视频目录为空，请将MP4放入后端视频目录并维护catalog.json。</p>
      )}
    </section>
  );
}
