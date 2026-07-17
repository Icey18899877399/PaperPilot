import { Transformer } from "markmap-lib";
import { Markmap } from "markmap-view";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import type { MindMap, Paper } from "../types";

interface Props {
  paper: Paper | null;
}

export function MindMapView({ paper }: Props) {
  const [mindMap, setMindMap] = useState<MindMap | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const svgRef = useRef<SVGSVGElement | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const markmapRef = useRef<Markmap | null>(null);
  const transformer = useMemo(() => new Transformer(), []);

  useEffect(() => {
    setMindMap(null);
    setError("");
    if (!paper || paper.status !== "ready") return;
    let cancelled = false;
    setLoading(true);
    api.cachedMindMap(paper.id)
      .then((cached) => {
        if (cancelled || !cached) return;
        setMindMap(cached);
      })
      .catch((reason) => {
        if (!cancelled) setError((reason as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [paper?.id]);

  const generate = async () => {
    if (!paper || paper.status !== "ready" || loading) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.createMindMap(paper.id, Boolean(mindMap));
      setMindMap(result);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!mindMap || !svgRef.current) return;
    const lines = [`# ${mindMap.center}`];
    mindMap.branches.forEach((branch) => {
      lines.push(`## ${branch.label}`);
      branch.subbranches?.forEach((subbranch) => {
        lines.push(`### ${subbranch.label}`);
        subbranch.children.forEach((child) => lines.push(`#### ${child}`));
      });
      branch.children.forEach((child) => lines.push(`### ${child}`));
    });
    const root = transformer.transform(lines.join("\n")).root;
    if (!markmapRef.current) {
      markmapRef.current = Markmap.create(svgRef.current, {
        autoFit: true,
        duration: 260,
        fitRatio: 0.95,
        initialExpandLevel: 2,
        maxInitialScale: 1.3,
        maxWidth: 220,
        nodeMinHeight: 28,
        paddingX: 12,
        spacingHorizontal: 70,
        spacingVertical: 16,
        toggleRecursively: true
      }, root);
    } else {
      void markmapRef.current
        .setData(root, { autoFit: true, initialExpandLevel: 2 })
        .then(() => markmapRef.current?.fit());
    }
  }, [mindMap, transformer]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !mindMap) return;
    let timer = window.setTimeout(() => void markmapRef.current?.fit(), 100);
    const observer = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void markmapRef.current?.fit(), 90);
    });
    observer.observe(canvas);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, [mindMap]);

  useEffect(() => () => markmapRef.current?.destroy(), []);

  return (
    <section className="content-page mind-map-page">
      <header className="content-page-header">
        <div>
          <span className="eyebrow">论文理解Agent</span>
          <h1>论文思维导图</h1>
          <p>{paper ? paper.filename : "请先选择一篇论文"}</p>
        </div>
        <button
          onClick={() => void generate()}
          disabled={!paper || paper.status !== "ready" || loading}
        >
          {loading ? "读取或生成中…" : mindMap ? "重新生成" : "生成思维导图"}
        </button>
      </header>
      {error && <div className="error-banner">{error}</div>}
      {!mindMap ? (
        <div className="mind-map-empty">
          <div className="mind-map-placeholder">研究问题<br />核心方法<br />实验结果</div>
          <p>点击“生成思维导图”，由论文理解Agent整理全文知识结构。</p>
        </div>
      ) : (
        <div className="mindmap-visual-shell">
          <div className="mindmap-toolbar">
            <div>
              <strong>{mindMap.title}</strong>
              <span>画布会自动适配窗口；点击节点圆点可展开或折叠，拖动可平移</span>
            </div>
            <div className="mindmap-actions">
              <button type="button" title="放大思维导图" aria-label="放大思维导图" onClick={() => void markmapRef.current?.rescale(1.15)}>＋</button>
              <button type="button" title="缩小思维导图" aria-label="缩小思维导图" onClick={() => void markmapRef.current?.rescale(0.87)}>－</button>
            </div>
          </div>
          <div className="mindmap-svg-wrap" ref={canvasRef}>
            <svg ref={svgRef} aria-label={`${mindMap.center}思维导图`} />
          </div>
        </div>
      )}
    </section>
  );
}
