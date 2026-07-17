import { useRef, useState } from "react";

const MAX_PDF_SIZE_MB = 50;
const MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024;

interface Props {
  uploading: boolean;
  onUpload: (file: File) => Promise<void>;
}

export function UploadPanel({ uploading, onUpload }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [validationError, setValidationError] = useState("");

  const accept = async (file?: File) => {
    if (!file) return;
    setValidationError("");
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setValidationError("仅支持PDF格式的论文文件");
      return;
    }
    if (file.size > MAX_PDF_SIZE_BYTES) {
      setValidationError(`PDF文件不能超过${MAX_PDF_SIZE_MB}MB`);
      return;
    }
    await onUpload(file);
  };

  return (
    <section
      className={`upload-box ${dragging ? "is-dragging" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        void accept(event.dataTransfer.files[0]);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        hidden
        onChange={(event) => {
          void accept(event.target.files?.[0]);
          event.currentTarget.value = "";
        }}
      />
      <span className="upload-icon">＋</span>
      <strong>{uploading ? "正在解析论文…" : "上传论文 PDF"}</strong>
      <span>点击选择或拖拽文件，最大{MAX_PDF_SIZE_MB}MB</span>
      <button disabled={uploading} onClick={() => inputRef.current?.click()}>
        选择文件
      </button>
      {validationError && <small className="upload-error">{validationError}</small>}
    </section>
  );
}
