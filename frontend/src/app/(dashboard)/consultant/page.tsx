"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  MessageCircle,
  Plus,
  Send,
  Trash2,
  GraduationCap,
  Loader2,
  AlertCircle,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  last_message_at: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

// ─── Markdown renderer (lightweight, no external dep) ────────────────────────

function renderMarkdown(text: string): string {
  return text
    // Bold: **text**
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    // Italic: *text* or _text_
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/_(.*?)_/g, "<em>$1</em>")
    // Code block: ```code```
    .replace(
      /```([\s\S]*?)```/g,
      '<pre class="bg-gray-100 rounded p-2 text-sm font-mono overflow-x-auto my-2 text-gray-800">$1</pre>'
    )
    // Inline code: `code`
    .replace(
      /`([^`]+)`/g,
      '<code class="bg-gray-100 rounded px-1 py-0.5 text-sm font-mono text-gray-800">$1</code>'
    )
    // Unordered list items: • or - or *
    .replace(/^[•\-\*] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    // Numbered list items: 1. 2. etc.
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
    // Wrap consecutive <li> in <ul>
    .replace(
      /(<li[^>]*>.*<\/li>\n?)+/g,
      (match) => `<ul class="my-2 space-y-1">${match}</ul>`
    )
    // Headers: ## and ###
    .replace(
      /^### (.+)$/gm,
      '<h4 class="font-semibold text-base mt-3 mb-1">$1</h4>'
    )
    .replace(
      /^## (.+)$/gm,
      '<h3 class="font-bold text-base mt-4 mb-1">$1</h3>'
    )
    // Line breaks
    .replace(/\n/g, "<br/>");
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function DrAvatar({ size = "md" }: { size?: "sm" | "md" }) {
  return (
    <div
      className={cn(
        "rounded-full bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center text-white font-bold shrink-0",
        size === "sm" ? "w-7 h-7 text-xs" : "w-9 h-9 text-sm"
      )}
    >
      DR
    </div>
  );
}

function MessageBubble({
  message,
  isStreaming = false,
}: {
  message: { role: "user" | "assistant"; content: string };
  isStreaming?: boolean;
}) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex gap-2.5 group", isUser ? "flex-row-reverse" : "flex-row")}>
      {!isUser && <DrAvatar size="sm" />}

      <div
        className={cn(
          "max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-blue-600 text-white rounded-tr-sm"
            : "bg-white border border-gray-100 text-gray-800 rounded-tl-sm shadow-sm"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            <div
              dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
              className="prose-sm"
            />
            {isStreaming && (
              <span className="inline-block w-1 h-4 bg-blue-500 animate-pulse ml-0.5 rounded-sm" />
            )}
          </>
        )}
      </div>

      {isUser && (
        <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 text-xs font-medium shrink-0">
          Moi
        </div>
      )}
    </div>
  );
}

function EmptyState({ onSendExample }: { onSendExample: (msg: string) => void }) {
  const examples = [
    "Je cherche une alternance en Data Science à Paris pour septembre, je suis en M1. Par où commencer ?",
    "Comment optimiser mon CV pour les ATS ? J'ai l'impression que mes candidatures ne passent pas.",
    "Quelles sont les erreurs à éviter dans une lettre de motivation pour un stage en ingénierie ?",
    "Comment négocier ma rémunération pour un CDI junior dans la tech à Paris ?",
    "Je dois préparer un entretien chez une grande banque française. Quels sont les codes à respecter ?",
    "Quelle est la différence entre un contrat d'apprentissage et un contrat de professionnalisation ?",
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 text-center">
      <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center text-white text-2xl font-bold mb-4 shadow-lg">
        DR
      </div>
      <h3 className="text-xl font-bold text-gray-900 mb-1">Dr. Rousseau</h3>
      <p className="text-sm text-gray-500 mb-2">Consultant en Carrière · Marché Français</p>
      <p className="text-sm text-gray-400 max-w-md mb-8">
        Spécialisé en alternance, stage et CDI pour les secteurs tech, finance et ingénierie.
        15 ans d&apos;expérience, 2 000+ étudiants accompagnés.
      </p>

      <p className="text-xs text-gray-400 mb-3 uppercase tracking-wide font-medium">
        Questions fréquentes
      </p>
      <div className="grid grid-cols-1 gap-2 w-full max-w-xl">
        {examples.map((ex) => (
          <button
            key={ex}
            onClick={() => onSendExample(ex)}
            className="text-left px-4 py-3 rounded-xl border border-gray-200 text-sm text-gray-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 transition-all duration-150 flex items-center gap-2"
          >
            <ChevronRight className="w-3 h-3 text-gray-400 shrink-0" />
            <span className="line-clamp-2">{ex}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ConsultantPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingContent, setStreamingContent] = useState<string>("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState("");
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [convLoading, setConvLoading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const getToken = () =>
    typeof window !== "undefined" ? localStorage.getItem("access_token") || "" : "";

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent, scrollToBottom]);

  // ── Load conversations on mount ────────────────────────────────────────────
  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/consultant/conversations?limit=50`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) return;
      const data: Conversation[] = await res.json();
      setConversations(data);
    } catch {
      // Silently fail — chatbot is optional
    }
  };

  // ── Load messages for selected conversation ────────────────────────────────
  const loadMessages = async (convId: string) => {
    setIsLoadingMessages(true);
    setMessages([]);
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/consultant/conversations/${convId}/messages`,
        { headers: { Authorization: `Bearer ${getToken()}` } }
      );
      if (!res.ok) throw new Error();
      const data: Message[] = await res.json();
      setMessages(data);
    } catch {
      toast.error("Impossible de charger les messages");
    } finally {
      setIsLoadingMessages(false);
    }
  };

  const selectConversation = (convId: string) => {
    if (isStreaming) return;
    setActiveConvId(convId);
    loadMessages(convId);
  };

  // ── Create new conversation ────────────────────────────────────────────────
  const createConversation = async (): Promise<string | null> => {
    setConvLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/consultant/conversations`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${getToken()}`,
          "Content-Type": "application/json",
        },
      });
      if (!res.ok) throw new Error();
      const data: Conversation = await res.json();
      setConversations((prev) => [data, ...prev]);
      setActiveConvId(data.id);
      setMessages([]);
      return data.id;
    } catch {
      toast.error("Impossible de créer une conversation");
      return null;
    } finally {
      setConvLoading(false);
    }
  };

  // ── Delete conversation ────────────────────────────────────────────────────
  const deleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (isStreaming && activeConvId === convId) return;
    try {
      await fetch(`${API_BASE}/api/v1/consultant/conversations/${convId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConvId === convId) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch {
      toast.error("Impossible de supprimer la conversation");
    }
  };

  // ── Send message ───────────────────────────────────────────────────────────
  const sendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;

    let convId = activeConvId;
    if (!convId) {
      convId = await createConversation();
      if (!convId) return;
    }

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    // Optimistically add user message
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);
    setStreamingContent("");

    abortRef.current = new AbortController();

    try {
      const res = await fetch(
        `${API_BASE}/api/v1/consultant/conversations/${convId}/chat`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${getToken()}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ message: trimmed }),
          signal: abortRef.current.signal,
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Erreur de connexion");
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let doneMessageId: string | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          try {
            const data = JSON.parse(raw);
            if (data.chunk) {
              fullContent += data.chunk;
              setStreamingContent(fullContent);
            } else if (data.event === "done") {
              doneMessageId = data.message_id;
            } else if (data.event === "error") {
              throw new Error(data.message || "Erreur inconnue");
            }
          } catch (parseErr) {
            if (parseErr instanceof SyntaxError) continue;
            throw parseErr;
          }
        }
      }

      // Finalise: replace streaming placeholder with permanent message
      if (fullContent) {
        const assistantMsg: Message = {
          id: doneMessageId || crypto.randomUUID(),
          role: "assistant",
          content: fullContent,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      }

      // Update conversation title in sidebar (may have been auto-set)
      await loadConversations();
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      const msg = err instanceof Error ? err.message : "Une erreur est survenue";
      toast.error(msg);
      // Remove optimistic user message on error
      setMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
    } finally {
      setIsStreaming(false);
      setStreamingContent("");
    }
  };

  // ── Keyboard handler ───────────────────────────────────────────────────────
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  // ── Auto-resize textarea ───────────────────────────────────────────────────
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  };

  // ── Time formatting ────────────────────────────────────────────────────────
  const formatTime = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffH = diffMs / 3_600_000;
    if (diffH < 1) return "À l'instant";
    if (diffH < 24) return `Il y a ${Math.floor(diffH)}h`;
    const diffD = Math.floor(diffH / 24);
    if (diffD < 7) return `Il y a ${diffD}j`;
    return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
  };

  // ─── Render ───────────────────────────────────────────────────────────────

  const displayMessages = [
    ...messages,
    ...(isStreaming && streamingContent
      ? [{ id: "streaming", role: "assistant" as const, content: streamingContent }]
      : []),
  ];

  return (
    <div className="flex h-[calc(100vh-4rem)] -m-8 overflow-hidden bg-gray-50">
      {/* ── Left panel: conversation list ──────────────────────────────────── */}
      <aside className="w-72 bg-white border-r border-gray-200 flex flex-col shrink-0">
        {/* Header */}
        <div className="p-4 border-b border-gray-100">
          <div className="flex items-center gap-2 mb-3">
            <GraduationCap className="w-5 h-5 text-blue-600" />
            <h2 className="font-semibold text-gray-800 text-sm">Consultant IA</h2>
          </div>
          <button
            onClick={createConversation}
            disabled={convLoading || isStreaming}
            className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {convLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            Nouvelle conversation
          </button>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.length === 0 ? (
            <div className="text-center py-8">
              <MessageCircle className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-xs text-gray-400">Aucune conversation</p>
            </div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => selectConversation(conv.id)}
                className={cn(
                  "group flex items-start gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-colors",
                  activeConvId === conv.id
                    ? "bg-blue-50 border border-blue-200"
                    : "hover:bg-gray-50 border border-transparent"
                )}
              >
                <MessageCircle
                  className={cn(
                    "w-4 h-4 mt-0.5 shrink-0",
                    activeConvId === conv.id ? "text-blue-600" : "text-gray-400"
                  )}
                />
                <div className="flex-1 min-w-0">
                  <p
                    className={cn(
                      "text-xs font-medium truncate",
                      activeConvId === conv.id ? "text-blue-700" : "text-gray-700"
                    )}
                  >
                    {conv.title}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {formatTime(conv.last_message_at)}
                  </p>
                </div>
                <button
                  onClick={(e) => deleteConversation(conv.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-500 text-gray-400 rounded transition-all"
                  title="Supprimer"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Dr. Rousseau info */}
        <div className="p-4 border-t border-gray-100 bg-gradient-to-r from-blue-50 to-indigo-50">
          <div className="flex items-center gap-2.5">
            <DrAvatar size="sm" />
            <div>
              <p className="text-xs font-semibold text-gray-800">Dr. Rousseau</p>
              <p className="text-xs text-gray-500">PhD · Marché français</p>
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-2 leading-relaxed">
            Alternance · Stage · CDI<br />ATS · Entretien · Réseau
          </p>
        </div>
      </aside>

      {/* ── Right panel: chat ────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat header */}
        {activeConvId && (
          <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3 shrink-0">
            <DrAvatar />
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">Dr. Rousseau</h3>
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                <p className="text-xs text-gray-500">
                  {isStreaming ? "En train d'écrire…" : "Consultant en Carrière · Marché Français"}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
          {!activeConvId ? (
            <EmptyState onSendExample={(msg) => sendMessage(msg)} />
          ) : isLoadingMessages ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : displayMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <DrAvatar />
              <p className="text-sm text-gray-500 mt-3 max-w-sm">
                Posez votre première question à Dr. Rousseau.
                <br />
                Alternance, stage, CDI, CV, entretien — il est là pour vous guider.
              </p>
            </div>
          ) : (
            displayMessages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                isStreaming={msg.id === "streaming"}
              />
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="bg-white border-t border-gray-200 px-6 py-4 shrink-0">
          {/* Gentle disclaimer */}
          {!activeConvId && (
            <p className="text-xs text-gray-400 text-center mb-3 flex items-center justify-center gap-1">
              <AlertCircle className="w-3 h-3" />
              Dr. Rousseau est un assistant IA. Vérifiez les informations légales importantes.
            </p>
          )}
          <div className="flex gap-3 items-end">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={
                activeConvId
                  ? "Posez votre question… (Entrée pour envoyer, Maj+Entrée pour sauter une ligne)"
                  : "Commencez par décrire votre situation et votre objectif…"
              }
              disabled={isStreaming}
              rows={1}
              className="flex-1 resize-none border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 bg-gray-50 placeholder:text-gray-400 leading-relaxed transition-all"
              style={{ minHeight: "44px", maxHeight: "160px" }}
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || isStreaming}
              className="p-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl transition-colors shrink-0"
              title="Envoyer (Entrée)"
            >
              {isStreaming ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2 text-center">
            Gemini 2.5 Flash · Spécialisé marché de l&apos;emploi français
          </p>
        </div>
      </div>
    </div>
  );
}
