"use client";

import { useState, useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { sendChatMessage } from "@/lib/api";

interface Message {
    id: string;
    role: "user" | "assistant";
    content: string;
}

const STORAGE_KEY = "lease-chat-history";

export default function QAPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    const hasMessages = messages.length > 0;

    // Load messages from localStorage on mount
    useEffect(() => {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            try {
                setMessages(JSON.parse(saved));
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
            };
            setMessages((prev) => [...prev, assistantMessage]);
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
        localStorage.removeItem(STORAGE_KEY);
    };

    // Get the most recent question for sticky display
    const lastUserMessage = [...messages].reverse().find(m => m.role === "user");
    const lastAssistantMessage = [...messages].reverse().find(m => m.role === "assistant");

    return (
        <div className="flex flex-col h-full bg-background">
            {hasMessages ? (
                <>
                    {/* Question header - scrolls away */}
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
                    <ScrollArea className="flex-1 px-6" ref={scrollRef}>
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
                                    <ReactMarkdown
                                        components={{
                                            p: ({ children }) => (
                                                <p className="text-[15px] leading-7 text-foreground mb-5">{children}</p>
                                            ),
                                            h1: ({ children }) => (
                                                <h1 className="text-xl font-semibold text-foreground mt-8 mb-4">{children}</h1>
                                            ),
                                            h2: ({ children }) => (
                                                <h2 className="text-lg font-semibold text-foreground mt-6 mb-3">{children}</h2>
                                            ),
                                            h3: ({ children }) => (
                                                <h3 className="text-base font-semibold text-foreground mt-5 mb-2">{children}</h3>
                                            ),
                                            ul: ({ children }) => (
                                                <ul className="my-4 ml-6 space-y-3 list-disc">{children}</ul>
                                            ),
                                            ol: ({ children }) => (
                                                <ol className="my-4 ml-6 space-y-3 list-decimal">{children}</ol>
                                            ),
                                            li: ({ children }) => (
                                                <li className="text-[15px] leading-7 text-foreground">{children}</li>
                                            ),
                                            strong: ({ children }) => (
                                                <strong className="font-semibold text-foreground">{children}</strong>
                                            ),
                                            em: ({ children }) => (
                                                <em className="italic">{children}</em>
                                            ),
                                            blockquote: ({ children }) => (
                                                <blockquote className="border-l-3 border-muted-foreground/40 pl-4 my-5 text-muted-foreground">{children}</blockquote>
                                            ),
                                            code: ({ children }) => (
                                                <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">{children}</code>
                                            ),
                                        }}
                                    >
                                        {lastAssistantMessage.content}
                                    </ReactMarkdown>
                                </div>
                            ) : null}
                        </div>
                    </ScrollArea>

                    {/* Input Area - STICKY at bottom */}
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
    );
}
