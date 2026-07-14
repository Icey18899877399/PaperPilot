import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "react-pdf/dist/Page/TextLayer.css";

import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
