import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function App() {
  const [apiStatus, setApiStatus] = useState("확인 중");

  useEffect(() => {
    fetch("/api/health")
      .then((response) => {
        if (!response.ok) throw new Error("API health check failed");
        return response.json() as Promise<{ status: string }>;
      })
      .then(({ status }) => setApiStatus(status))
      .catch(() => setApiStatus("연결 실패"));
  }, []);

  return (
    <main>
      <h1>SeSAC Team 1</h1>
      <p>Docker 개발환경이 실행 중입니다.</p>
      <p>
        Backend: <strong>{apiStatus}</strong>
      </p>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
