import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";

export type Stage = "prompt" | "result";
export type ChatRole = "user" | "agent";
export type ChatMessage = { id: string; role: ChatRole; text: string; downloadUrl?: string };

const BACKEND_URL = (import.meta as any).env?.VITE_BACKEND_URL || "http://localhost:5001";

export function useSocketRun() {
  const socketRef = useRef<Socket | null>(null);

  const [connected, setConnected] = useState(false);
  const [stage, setStage] = useState<Stage>("prompt");
  const [runId, setRunId] = useState<string | null>(null);
  const [progressMessages, setProgressMessages] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [summary, setSummary] = useState<string>("");
  const [downloadUrl, setDownloadUrl] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [awaitingUser, setAwaitingUser] = useState<boolean>(false);

  useEffect(() => {
    const socket = io(BACKEND_URL, { autoConnect: true });
    socketRef.current = socket;

    const onConnected = (payload: any) => {
      setConnected(true);
    };

    const onError = (payload: any) => {
      setError(typeof payload?.message === "string" ? payload.message : "Unknown error");
    };

    const onRunStarted = (payload: any) => {
      setRunId(payload?.run_id || null);
    };

    const appendAgent = (text: any, dl?: string) => {
      const t = typeof text === "string" ? text : JSON.stringify(text ?? {});
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "agent", text: t, downloadUrl: dl },
      ]);
    };


    const onProgress = (payload: any) => {
      // Any progress means the agent is busy; disable sending
      setAwaitingUser(false);
      // Prefer explicit message; fallback to node or snapshot parsing
      const message: string | undefined = typeof payload?.message === "string" ? payload.message : undefined;
      if (message && message.trim()) {
        setProgressMessages((prev) => [...prev, message]);
        return;
      }
      const lines: string[] = Array.isArray(payload?.snapshot) ? payload.snapshot : [];
      const nodeLine = typeof payload?.node === "string" ? payload.node : undefined;
      const readable = nodeLine || (lines.find((l) => l.startsWith("node:")) || lines[0] || "Working...");
      setProgressMessages((prev) => [...prev, readable]);
    };

    const onModReady = (payload: any) => {
      const sum = payload?.summary;
      const sumStr = typeof sum === "string" ? sum : JSON.stringify(sum ?? {});
      setSummary(sumStr);
      const dl: string = payload?.download_url || "";
      const fullDl = dl ? `${BACKEND_URL}${dl}` : "";
      setDownloadUrl(fullDl);
      // Append agent message with summary + single MDK download
      appendAgent(sumStr, fullDl || undefined);
      setStage("result");
      // After mod is ready, the graph routes to await_user_input; enable sending
      setAwaitingUser(true);
    };

    const onChatResponse = (payload: any) => {
      // Backend sends chat_response with { message } only; do NOT read summary here
      const msg: string = typeof payload?.message === "string" ? payload.message : "";
      if (msg) {
        appendAgent(msg);
      }
      // After responding, the graph typically routes back to await_user_input
      setAwaitingUser(true);
    };

    socket.on("connected", onConnected);
    socket.on("error", onError);
    socket.on("run_started", onRunStarted);
    socket.on("progress", onProgress);
    socket.on("mod_ready", onModReady);
    socket.on("chat_response", onChatResponse);

    return () => {
      socket.off("connected", onConnected);
      socket.off("error", onError);
      socket.off("run_started", onRunStarted);
      socket.off("progress", onProgress);
      socket.off("mod_ready", onModReady);
      socket.off("chat_response", onChatResponse);
      socket.disconnect();
      socketRef.current = null;
    };
  }, []);

  const startRun = useCallback((prompt: string, mcVersion?: string, author?: string) => {
    if (!prompt.trim()) return;
    setProgressMessages([]);
    setSummary("");
    setDownloadUrl("");
    setMessages([{ id: crypto.randomUUID(), role: "user", text: prompt }]);
    setError(null);
    // Immediately enter the chat view; agent is busy until ready
    setStage("result");
    setAwaitingUser(false);
    socketRef.current?.emit("start_run", { prompt, author, mc_version: mcVersion });
  }, []);

  const sendChat = useCallback((message: string) => {
    const text = message.trim();
    if (!text) return;
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text }]);
    // Reset progress and mark busy while agent processes
    setProgressMessages([]);
    setAwaitingUser(false);
    if (!runId) return;
    socketRef.current?.emit("chat", { run_id: runId, message: text });
  }, [runId]);

  return useMemo(() => ({
    connected,
    stage,
    runId,
    progressMessages,
    messages,
    summary,
    downloadUrl,
    error,
    awaitingUser,
    startRun,
    sendChat,
  }), [connected, stage, runId, progressMessages, messages, summary, downloadUrl, error, awaitingUser, startRun, sendChat]);
}

