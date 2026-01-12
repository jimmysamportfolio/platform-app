"use client";

import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowUp, X, ExternalLink } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { sendChatMessage, ChatResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface Message {
    id: string;
    role: "user" | "assistant";
    content: string;
    confidence?: number;
    sources?: string[];
}

interface DocumentPreview {
    name: string;
    url: string | null;
    loading: boolean;
    searchTerm?: string;
}

const STORAGE_KEY = "lease-chat-history";

export default function QAPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [lastSources, setLastSources] = useState<string[]>([]);
    const scrollRef = useRef<HTMLDivElement>(null);

    // Document preview state
    const [preview, setPreview] = useState<DocumentPreview | null>(null);

    const hasMessages = messages.length > 0;

    // Load messages from localStorage on mount
    useEffect(() => {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                setMessages(parsed);
                // Restore last sources from the most recent assistant message
                const lastAssistant = [...parsed].reverse().find((m: Message) => m.role === "assistant");
                if (lastAssistant?.sources) {
                    setLastSources(lastAssistant.sources);
                }
            } catch {
                // Invalid JSON, ignore
            }
        }
    }, []);

    // Save messages to localStorage when they change
    useEffect(() => {
        if (messages.length > 0) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
        }
    }, [messages]);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    // Open document preview with optional search term
    const openDocumentPreview = useCallback(async (documentName: string, searchTerm?: string) => {
        setPreview({ name: documentName, url: null, loading: true, searchTerm });

        try {
            const proxyUrl = `/api/documents/${encodeURIComponent(documentName)}`;
            const response = await fetch(proxyUrl);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const blob = await response.blob();
            let blobUrl = URL.createObjectURL(blob);

            // Add search fragment for PDF navigation
            if (searchTerm) {
                blobUrl += `#search=${encodeURIComponent(searchTerm)}`;
            }

            setPreview({ name: documentName, url: blobUrl, loading: false, searchTerm });
        } catch (error) {
            console.error("Failed to load document:", error);
            setPreview({ name: documentName, url: null, loading: false, searchTerm });
        }
    }, []);

    // Close preview panel
    const closePreview = () => {
        if (preview?.url) {
            URL.revokeObjectURL(preview.url.split('#')[0]);
        }
        setPreview(null);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;

        const userMessage: Message = {
            id: Date.now().toString(),
            role: "user",
            content: input.trim(),
        };

        setMessages((prev) => [...prev, userMessage]);
        setInput("");
        setIsLoading(true);

        try {
            const response = await sendChatMessage(userMessage.content);
            const assistantMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: "assistant",
                content: response.answer,
                confidence: response.confidence,
                sources: response.sources,
            };
            setMessages((prev) => [...prev, assistantMessage]);
            setLastSources(response.sources || []);
        } catch (error) {
            const errorMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: "assistant",
                content: `Error: ${error instanceof Error ? error.message : "Failed to connect to server"}`,
            };
            setMessages((prev) => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    };

    const clearHistory = () => {
        setMessages([]);
        setLastSources([]);
        localStorage.removeItem(STORAGE_KEY);
    };

    // Get the most recent messages for display
    const lastUserMessage = [...messages].reverse().find(m => m.role === "user");
    const lastAssistantMessage = [...messages].reverse().find(m => m.role === "assistant");

    // Markdown components with section link support
    const markdownComponents = useMemo(() => ({
        p: ({ children }: { children?: React.ReactNode }) => (
            <p className="text-[15px] leading-7 text-foreground mb-5">{children}</p>
        ),
        h1: ({ children }: { children?: React.ReactNode }) => (
            <h1 className="text-xl font-semibold text-foreground mt-8 mb-4">{children}</h1>
        ),
        h2: ({ children }: { children?: React.ReactNode }) => (
            <h2 className="text-lg font-semibold text-foreground mt-6 mb-3">{children}</h2>
        ),
        h3: ({ children }: { children?: React.ReactNode }) => (
            <h3 className="text-base font-semibold text-foreground mt-5 mb-2">{children}</h3>
        ),
        ul: ({ children }: { children?: React.ReactNode }) => (
            <ul className="my-4 ml-6 space-y-3 list-disc">{children}</ul>
        ),
        ol: ({ children }: { children?: React.ReactNode }) => (
            <ol className="my-4 ml-6 space-y-3 list-decimal">{children}</ol>
        ),
        li: ({ children }: { children?: React.ReactNode }) => (
            <li className="text-[15px] leading-7 text-foreground">{children}</li>
        ),
        strong: ({ children }: { children?: React.ReactNode }) => (
            <strong className="font-semibold text-foreground">{children}</strong>
        ),
        em: ({ children }: { children?: React.ReactNode }) => (
            <em className="italic">{children}</em>
        ),
        blockquote: ({ children }: { children?: React.ReactNode }) => (
            <blockquote className="border-l-3 border-muted-foreground/40 pl-4 my-5 text-muted-foreground">{children}</blockquote>
        ),
        code: ({ children }: { children?: React.ReactNode }) => (
            <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">{children}</code>
        ),
    }), []);


    return (
        <div className="flex h-screen bg-background overflow-hidden">
            {/* Main chat area */}
            <div className={`flex flex-col transition-all duration-300 overflow-hidden ${preview ? 'w-1/2' : 'w-full'}`}>
                {hasMessages ? (
                    <>
                        {/* Question header */}
                        {lastUserMessage && (
                            <div className="bg-background px-6 py-4">
                                <div className="max-w-3xl mx-auto flex justify-end">
                                    <div className="max-w-[80%] px-4 py-3 rounded-2xl bg-muted text-foreground text-sm">
                                        <p className="whitespace-pre-wrap">{lastUserMessage.content}</p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Scrollable answer area */}
                        <ScrollArea className="flex-1 px-6 overflow-y-auto" ref={scrollRef}>
                            <div className="max-w-3xl mx-auto pb-4">
                                {isLoading ? (
                                    <div className="py-4">
                                        <div className="flex gap-1.5">
                                            <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "0ms" }} />
                                            <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "150ms" }} />
                                            <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "300ms" }} />
                                        </div>
                                    </div>
                                ) : lastAssistantMessage ? (
                                    <div className="answer-content">
                                        <ReactMarkdown components={markdownComponents}>
                                            {lastAssistantMessage.content}
                                        </ReactMarkdown>
                                        {/* Source documents */}
                                        {lastSources.length > 0 && (
                                            <div className="mt-4 pt-4 border-t border-muted">
                                                <p className="text-xs text-muted-foreground mb-2">Sources:</p>
                                                <div className="flex flex-wrap gap-2">
                                                    {lastSources.map((source, i) => (
                                                        <button
                                                            key={i}
                                                            onClick={() => openDocumentPreview(source)}
                                                            className="text-xs px-2 py-1 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors"
                                                        >
                                                            {source.replace(/\.[^.]+$/, '').slice(0, 40)}...
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {/* Confidence indicator */}
                                        {lastAssistantMessage.confidence !== undefined && (
                                            <div className="mt-4 pt-4 border-t border-muted">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-xs text-muted-foreground">Confidence:</span>
                                                    <div className="flex items-center gap-1.5">
                                                        <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
                                                            <div
                                                                className={`h-full rounded-full transition-all ${lastAssistantMessage.confidence >= 80
                                                                    ? 'bg-green-500'
                                                                    : lastAssistantMessage.confidence >= 60
                                                                        ? 'bg-yellow-500'
                                                                        : 'bg-orange-500'
                                                                    }`}
                                                                style={{ width: `${lastAssistantMessage.confidence}%` }}
                                                            />
                                                        </div>
                                                        <span className={`text-xs font-medium ${lastAssistantMessage.confidence >= 80
                                                            ? 'text-green-600'
                                                            : lastAssistantMessage.confidence >= 60
                                                                ? 'text-yellow-600'
                                                                : 'text-orange-600'
                                                            }`}>
                                                            {lastAssistantMessage.confidence}%
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ) : null}
                            </div>
                        </ScrollArea>

                        {/* Input Area */}
                        <div className="sticky bottom-0 z-10 p-6 pt-4 bg-background">
                            <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
                                <div className="relative">
                                    <input
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyDown={handleKeyDown}
                                        placeholder="Ask another question..."
                                        disabled={isLoading}
                                        className="w-full h-14 pl-5 pr-14 text-base bg-muted border-0 rounded-full focus:outline-none"
                                    />
                                    <button
                                        type="submit"
                                        disabled={isLoading || !input.trim()}
                                        className="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-full bg-primary text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                                    >
                                        <ArrowUp className="w-5 h-5" />
                                    </button>
                                </div>
                            </form>
                            <div className="max-w-3xl mx-auto mt-2 text-center">
                                <button
                                    onClick={clearHistory}
                                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    Clear history
                                </button>
                            </div>
                        </div>
                    </>
                ) : (
                    /* Empty state - centered input */
                    <div className="flex-1 flex items-center justify-center p-6">
                        <div className="w-full max-w-2xl">
                            <h2 className="text-xl font-medium text-foreground text-center mb-6">
                                Ask about your leases
                            </h2>
                            <form onSubmit={handleSubmit}>
                                <div className="relative">
                                    <input
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyDown={handleKeyDown}
                                        placeholder="What would you like to know?"
                                        disabled={isLoading}
                                        className="w-full h-16 pl-6 pr-16 text-base bg-muted border-0 rounded-full focus:outline-none"
                                    />
                                    <button
                                        type="submit"
                                        disabled={isLoading || !input.trim()}
                                        className="absolute right-2.5 top-1/2 -translate-y-1/2 w-11 h-11 flex items-center justify-center rounded-full bg-primary text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                                    >
                                        <ArrowUp className="w-5 h-5" />
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </div>

            {/* Document preview panel (right side) - fixed position */}
            {preview && (
                <div className="w-1/2 border-l border-border flex flex-col bg-background">
                    {/* Header */}
                    <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                        <div className="flex-1 min-w-0 mr-4">
                            <h3 className="text-sm font-medium truncate">{preview.name}</h3>
                            {preview.searchTerm && (
                                <p className="text-xs text-muted-foreground">Searching: {preview.searchTerm}</p>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => preview.url && window.open(preview.url.split('#')[0], "_blank")}
                                disabled={!preview.url}
                            >
                                <ExternalLink className="w-4 h-4" />
                            </Button>
                            <Button variant="ghost" size="sm" onClick={closePreview}>
                                <X className="w-4 h-4" />
                            </Button>
                        </div>
                    </div>
                    {/* Document content */}
                    <div className="flex-1 min-h-0">
                        {preview.loading ? (
                            <div className="flex items-center justify-center h-full">
                                <div className="text-muted-foreground">Loading document...</div>
                            </div>
                        ) : preview.url ? (
                            <iframe
                                src={preview.url}
                                className="w-full h-full border-0"
                                title={preview.name}
                            />
                        ) : (
                            <div className="flex items-center justify-center h-full">
                                <div className="text-muted-foreground">Failed to load document</div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
