import type { AgentLog } from "../types";

interface Props {
  logs: AgentLog[];
  loading: boolean;
  onRefresh: () => Promise<void>;
}

const agentLabels: Record<string, string> = {
  "coordinator-agent": "协调Agent",
  "paper-understanding-agent": "论文理解Agent",
  "translation-agent": "翻译Agent",
  "chat-agent": "聊天问答Agent"
};

export function AgentLogView({ logs, loading, onRefresh }: Props) {
  return (
    <section className="content-page agent-log-page">
      <header className="content-page-header">
        <div>
          <span className="eyebrow">多Agent可追溯执行</span>
          <h1>Agent 调用日志</h1>
          <p>展示协调Agent的任务路由，以及各专业Agent的执行动作与追踪编号。</p>
        </div>
        <button onClick={() => void onRefresh()} disabled={loading}>
          {loading ? "刷新中…" : "刷新日志"}
        </button>
      </header>
      <div className="agent-summary">
        {Object.entries(agentLabels).map(([agent, label]) => (
          <article key={agent}>
            <strong>{label}</strong>
            <span>{logs.filter((item) => item.agent === agent).length} 条记录</span>
          </article>
        ))}
      </div>
      <div className="log-table-wrap">
        <table className="log-table">
          <thead>
            <tr><th>时间</th><th>Agent</th><th>动作</th><th>详情</th><th>Trace ID</th></tr>
          </thead>
          <tbody>
            {[...logs].reverse().map((item, index) => (
              <tr key={`${item.trace_id}-${item.action}-${index}`}>
                <td>{new Date(item.created_at).toLocaleTimeString("zh-CN")}</td>
                <td><span className="agent-chip">{agentLabels[item.agent] ?? item.agent}</span></td>
                <td>{item.action}</td>
                <td>{item.detail}</td>
                <td><code>{item.trace_id.slice(0, 12)}…</code></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!logs.length && <p className="empty-copy">尚无日志，请先在阅读工作台生成导读、翻译或发起问答。</p>}
      </div>
    </section>
  );
}
