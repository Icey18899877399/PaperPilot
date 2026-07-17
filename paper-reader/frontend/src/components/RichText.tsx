import { Fragment } from "react";

interface Props {
  text: string;
  className?: string;
}

/**
 * 极简、XSS 安全的富文本渲染：按行分段，把 **加粗** 段渲染为 <strong>。
 * 不用 dangerouslySetInnerHTML、不引入 markdown 库——仅覆盖 AI 回答里最常见的
 * 加粗强调（参考 NotebookLM 的信息层级排版），突出关键结论。
 */
export function RichText({ text, className }: Props) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  return (
    <div className={className ? `rich-text ${className}` : "rich-text"}>
      {lines.map((line, lineIndex) => {
        if (!line.trim()) return <br key={lineIndex} />;
        const segments = line.split(/(\*\*[^*]+\*\*)/g);
        return (
          <p key={lineIndex}>
            {segments.map((segment, index) => {
              const bold = /^\*\*[^*]+\*\*$/.test(segment);
              return bold ? (
                <strong key={index}>{segment.slice(2, -2)}</strong>
              ) : (
                <Fragment key={index}>{segment}</Fragment>
              );
            })}
          </p>
        );
      })}
    </div>
  );
}
