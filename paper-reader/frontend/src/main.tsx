import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import App from "./App";
import "./styles/base.css";
import "./styles.css";
import "./styles/chat.css";
import "./styles/notebooklm-theme.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
