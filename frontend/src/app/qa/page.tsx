"use client";

import { useState, useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowUp } from "lucide-react";
import { sendChatMessage } from "@/lib/api";

interface Message {
    id: string;
    role: "user" | "assistant";
    content: string;
}

export default function QAPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    const hasMessages = messages.length > 0;

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

    return (
        <div className="flex flex-col h-full bg-muted/30">
            {hasMessages ? (
                <>
                    <ScrollArea className="flex-1 p-6" ref={scrollRef}>
                        <div className="max-w-3xl mx-auto space-y-4 pb-4">
                            {messages.map((message) => (
                                <div
                                    key={message.id}
                                    className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                                >
                                    <div
                                        className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm ${message.role === "user"
                                            ? "bg-primary text-primary-foreground"
                                            : "bg-card text-foreground border border-border"
                                            }`}
                                    >
                                        <p className="whitespace-pre-wrap">{message.content}</p>
                                    </div>
                                </div>
                            ))}
                            {isLoading && (
                                <div className="flex justify-start">
                                    <div className="bg-card border border-border px-4 py-3 rounded-2xl">
                                        <div className="flex gap-1.5">
                                            <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "0ms" }} />
                                            <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "150ms" }} />
                                            <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "300ms" }} />
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </ScrollArea>

                    {/* Input Area - at bottom */}
                    <div className="p-6 pt-2">
                        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
                            <div className="relative">
                                <input
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyDown={handleKeyDown}
                                    placeholder="Ask about your leases..."
                                    disabled={isLoading}
                                    className="w-full h-14 pl-5 pr-14 text-base bg-card border border-border rounded-full focus:outline-none focus:border-border"
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
                                    className="w-full h-16 pl-6 pr-16 text-base bg-card border border-border rounded-full focus:outline-none focus:border-border"
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
