/**
 * QuickChatPage — standalone chat using local Ollama.
 * No API key needed. Connects to Ollama at localhost:11434.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Typography } from "@nous-research/ui";
import { cn } from "@/lib/utils";
import { Send, Settings2, Trash2, X } from "lucide-react";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

const ENDPOINT_KEY = "hermes_chat_endpoint";
const MODEL_KEY = "hermes_chat_model";
const DEFAULT_ENDPOINT = "http://localhost:11434";
const DEFAULT_MODEL = "hermes3:latest";
const SYSTEM_PROMPT =
  "You are Hermes, a helpful AI assistant created by Nous Research. You are knowledgeable, concise, and friendly.";

function stored(key: string, fallback: string): string {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}

export default function QuickChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [endpoint, setEndpoint] = useState(() => stored(ENDPOINT_KEY, DEFAULT_ENDPOINT));
  const [model, setModel] = useState(() => stored(MODEL_KEY, DEFAULT_MODEL));
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Fetch available Ollama models on mount
  useEffect(() => {
    fetch(`${endpoint}/api/tags`)
      .then(r => r.json())
      .then(data => {
        const names = (data.models ?? []).map((m: { name: string }) => m.name);
        setModels(names);
        if (names.length > 0 && !names.includes(model)) {
          // If current model not found, check for hermes variants
          const hermes = names.find((n: string) => n.toLowerCase().includes("hermes"));
          if (hermes) setModel(hermes);
        }
      })
      .catch(() => setModels([]));
  }, [endpoint]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!showSettings) inputRef.current?.focus();
  }, [showSettings]);

  const saveSettings = () => {
    try {
      localStorage.setItem(ENDPOINT_KEY, endpoint);
      localStorage.setItem(MODEL_KEY, model);
    } catch { /* ignore */ }
    setShowSettings(false);
  };

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;

    setError(null);
    const userMsg: Message = { role: "user", content: text };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput("");
    setStreaming(true);

    const assistantMsg: Message = { role: "assistant", content: "" };
    setMessages([...history, assistantMsg]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${endpoint}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          messages: [{ role: "system", content: SYSTEM_PROMPT }, ...history],
          stream: true,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(`Ollama error ${res.status}: ${errBody.slice(0, 200)}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response stream");
      const decoder = new TextDecoder();
      let acc = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n").filter(l => l.trim());
        for (const line of lines) {
          try {
            const parsed = JSON.parse(line);
            const content = parsed.message?.content;
            if (content) {
              acc += content;
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: "assistant", content: acc };
                return updated;
              });
            }
          } catch { /* skip */ }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        const msg = (err as Error).message;
        if (msg.includes("Failed to fetch") || msg.includes("ECONNREFUSED")) {
          setError("Can't connect to Ollama. Make sure it's running: ollama serve");
        } else {
          setError(msg);
        }
        setMessages(prev => prev.slice(0, -1));
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [input, streaming, endpoint, model, messages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const clearChat = () => { setMessages([]); setError(null); };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 normal-case">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <Typography
          className="font-bold text-[1.125rem] leading-[0.95] tracking-[0.04em] text-midground"
          style={{ mixBlendMode: "plus-lighter" }}
        >
          Quick Chat
        </Typography>
        <div className="flex items-center gap-1.5">
          {models.length > 0 && (
            <span className="text-[0.6rem] tracking-wider text-midground/30 mr-2">
              {model} • {models.length} models available
            </span>
          )}
          <Button ghost size="icon" onClick={clearChat} title="Clear chat"
            className="text-midground/50 hover:text-midground">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
          <Button ghost size="icon" onClick={() => setShowSettings(!showSettings)} title="Settings"
            className={cn("text-midground/50 hover:text-midground", showSettings && "text-midground")}>
            <Settings2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="rounded-lg border border-current/20 bg-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold tracking-wider text-midground/60 uppercase">Ollama Configuration</span>
            <Button ghost size="icon" onClick={() => setShowSettings(false)}
              className="text-midground/40 hover:text-midground h-6 w-6">
              <X className="h-3 w-3" />
            </Button>
          </div>
          <div className="space-y-1.5">
            <label className="text-[0.7rem] font-medium text-midground/50 tracking-wider uppercase">Endpoint</label>
            <input value={endpoint} onChange={e => setEndpoint(e.target.value)}
              placeholder="http://localhost:11434"
              className={cn(
                "w-full rounded border border-current/15 bg-black/20 px-3 py-2",
                "text-sm text-midground placeholder:text-midground/25",
                "outline-none focus:border-current/30",
              )} />
          </div>
          <div className="space-y-1.5">
            <label className="text-[0.7rem] font-medium text-midground/50 tracking-wider uppercase">Model</label>
            {models.length > 0 ? (
              <select value={model} onChange={e => setModel(e.target.value)}
                className={cn(
                  "w-full rounded border border-current/15 bg-black/20 px-3 py-2",
                  "text-sm text-midground outline-none focus:border-current/30",
                )}>
                {models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            ) : (
              <input value={model} onChange={e => setModel(e.target.value)}
                placeholder="hermes3"
                className={cn(
                  "w-full rounded border border-current/15 bg-black/20 px-3 py-2",
                  "text-sm text-midground placeholder:text-midground/25",
                  "outline-none focus:border-current/30",
                )} />
            )}
          </div>
          <Button onClick={saveSettings}
            className="w-full rounded border border-current/20 bg-midground/10 py-2 text-xs font-bold tracking-wider text-midground hover:bg-midground/20">
            Save
          </Button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive normal-case">
          {error}
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto space-y-3 pr-1"
        style={{ scrollbarWidth: "thin", scrollbarColor: "rgba(240,230,210,0.1) transparent" }}>
        {messages.length === 0 && !showSettings && (
          <div className="flex flex-1 items-center justify-center h-full pt-20">
            <div className="text-center space-y-2">
              <p className="text-lg font-bold text-midground/20 tracking-wider">Start a conversation</p>
              <p className="text-xs text-midground/15 normal-case">Type a message below to chat with {model}</p>
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={cn("flex gap-2.5", m.role === "user" ? "justify-end" : "justify-start")}>
            {m.role === "assistant" && (
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-midground/10 text-[0.55rem] font-bold text-midground/60">H</div>
            )}
            <div className={cn(
              "max-w-[85%] rounded-lg px-3.5 py-2.5 text-sm leading-relaxed",
              m.role === "user"
                ? "bg-midground/10 border border-midground/15 text-midground/90"
                : "bg-card border border-current/10 text-midground/75",
            )} style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {m.content || (streaming && i === messages.length - 1 ? "..." : "")}
            </div>
          </div>
        ))}
      </div>

      {/* Input */}
      <div className="flex gap-2 items-end">
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message Hermes..."
          rows={1}
          className={cn(
            "flex-1 resize-none rounded-lg border border-current/15 bg-black/20",
            "px-3.5 py-2.5 text-sm text-midground",
            "placeholder:text-midground/25",
            "outline-none focus:border-current/30",
            "max-h-32 normal-case",
          )}
          style={{ scrollbarWidth: "thin" }}
        />
        <Button onClick={streaming ? () => abortRef.current?.abort() : send}
          className={cn(
            "shrink-0 rounded-lg border px-3 py-2.5",
            streaming
              ? "border-destructive/30 bg-destructive/10 text-destructive hover:bg-destructive/20"
              : "border-current/20 bg-midground/10 text-midground hover:bg-midground/20",
          )}>
          {streaming ? <X className="h-4 w-4" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}
