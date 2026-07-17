interface Props {
  page: number;
  pageCount: number;
  language?: "source" | "translation";
  width?: number;
  highlighted?: boolean;
}

const sections = [
  ["Abstract", "Academic reading involves PDF parsing, structural extraction, method comprehension, translation, and evidence-grounded question answering. PaperPilot organizes these steps as a traceable multi-agent workflow."],
  ["1. Background", "PaperPilot decomposes paper reading into traceable parsing, understanding, translation, and question-answering tasks. A coordinator agent recognizes intent before dispatching work."],
  ["2. System Architecture", "The reading workspace connects to a unified API. Specialized agents share a structured paper index with page and bounding-box metadata."],
  ["3. Structured Parsing", "The parsing layer preserves text, figures, tables, equations, page numbers, and in-page positions as a common evidence foundation."],
  ["4. Agent Collaboration", "A question passes through intent recognition, evidence retrieval, response composition, and citation delivery. Every operation records a trace identifier."],
  ["5. Hybrid Retrieval", "The system combines semantic similarity with keyword matching and constrains generated answers to retrieved evidence."],
  ["6. Traceable Answers", "Retrieved chunks carry page numbers, content types, and coordinates. Clicking a citation moves the reader to the matching evidence."],
  ["7. Module Responsibilities", "The coordinator routes tasks while the question-answering agent retrieves evidence and returns answers with citations."],
  ["8. Validation", "The validation flow covers loading, parsing, guided reading, question answering, citation location, bilingual reading, and agent logs."],
  ["9. Discussion", "Multi-agent decomposition improves modularity and observability, while requiring shared context and consistent error handling."],
  ["10. Limitations", "The static demonstration does not execute MinerU or model calls. Full functionality requires the FastAPI backend and model services."],
  ["Conclusion", "PaperPilot presents a deployable academic reading workflow that improves transparency through source evidence and execution traces."],
];

const translations = [
  "学术阅读涉及 PDF 解析、结构提取、方法理解、翻译和基于证据的问答。PaperPilot 将这些步骤组织为可追踪的多 Agent 工作流。",
  "PaperPilot 将论文阅读分解为解析、理解、翻译和问答任务，由协调 Agent 识别意图并分派任务。",
  "阅读工作台连接统一 API，各专业 Agent 共享包含页码和位置数据的结构化论文索引。",
  "解析层保留正文、图片、表格、公式及其页码和页内位置，为证据检索提供统一基础。",
  "一次问答依次经过意图识别、证据检索、回答组织和引用回传，并记录追踪编号。",
  "系统结合语义相似度与关键词匹配，并限制回答只能使用检索到的论文证据。",
  "检索切片携带页码、内容类型和坐标；点击引用后，阅读器会跳转到相应证据。",
  "协调 Agent 负责任务路由，问答 Agent 负责检索证据并返回带引用的答案。",
  "验证流程覆盖论文载入、解析、导读、问答、引用定位、双语阅读与 Agent 日志。",
  "多 Agent 拆分提高模块化和可观测性，同时需要统一上下文与错误处理。",
  "静态演示不执行 MinerU 或模型调用，完整功能仍需 FastAPI 后端及模型服务。",
  "PaperPilot 通过原文证据和执行日志提升学术阅读工作流的透明度。",
];

export function DemoPaperPage({ page, pageCount, language = "source", width = 680, highlighted = false }: Props) {
  const index = Math.min(Math.max(page - 1, 0), sections.length - 1);
  const [heading, source] = sections[index];
  const copy = language === "translation" ? translations[index] : source;

  return (
    <article className="demo-paper-sheet" style={{ width }}>
      <header><span>PaperPilot Research Preview</span><b>{page} / {pageCount}</b></header>
      {page === 1 && <h1>{language === "translation" ? "面向可追溯学术阅读的多 Agent 协作系统" : "A Traceable Multi-Agent System for Academic Reading"}</h1>}
      <h2>{language === "translation" ? `第 ${page} 页译文` : heading}</h2>
      <p className={highlighted ? "demo-target-copy" : ""}>{copy}</p>
      <p>{language === "translation" ? "本页面使用内置示例材料展示双语阅读、结构化解析与原文引用定位之间的关系。" : "This built-in sample demonstrates the relationship between structured parsing, retrieval, and source-grounded answers."}</p>
      <div className="demo-paper-diagram"><span>User query</span><i>→</i><span>Coordinator</span><i>→</i><span>Specialist agent</span><i>→</i><span>Evidence answer</span></div>
      <footer>PaperPilot · GitHub Pages Demo</footer>
    </article>
  );
}
