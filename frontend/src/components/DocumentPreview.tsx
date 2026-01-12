"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { X, ExternalLink } from "lucide-react";

interface DocumentPreviewModalProps {
    /** Document name to display in header */
    documentName: string | null;
    /** Whether the preview is open */
    open: boolean;
    /** Callback when open state changes */
    onOpenChange: (open: boolean) => void;
    /** Optional search term to highlight in PDF */
    searchTerm?: string;
}

/**
 * Reusable document preview modal component.
 * Fetches and displays PDF documents via Next.js proxy.
 */
export function DocumentPreviewModal({
    documentName,
    open,
    onOpenChange,
    searchTerm,
}: DocumentPreviewModalProps) {
    const [url, setUrl] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch document when opened
    useEffect(() => {
        if (!open || !documentName) {
            return;
        }

        let cancelled = false;

        async function fetchDocument() {
            setLoading(true);
            setError(null);
            setUrl(null);

            try {
                const proxyUrl = `/api/documents/${encodeURIComponent(documentName!)}`;
                const response = await fetch(proxyUrl);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                const blob = await response.blob();
                let blobUrl = URL.createObjectURL(blob);

                // Add search fragment for PDF navigation
                if (searchTerm) {
                    blobUrl += `#search=${encodeURIComponent(searchTerm)}`;
                }

                if (!cancelled) {
                    setUrl(blobUrl);
                    setLoading(false);
                }
            } catch (err) {
                console.error("Failed to load document:", err);
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : "Failed to load document");
                    setLoading(false);
                }
            }
        }

        fetchDocument();

        return () => {
            cancelled = true;
        };
    }, [open, documentName, searchTerm]);

    // Cleanup blob URL on close
    const handleClose = (newOpen: boolean) => {
        if (!newOpen && url) {
            URL.revokeObjectURL(url.split('#')[0]);
            setUrl(null);
            setLoading(false);
            setError(null);
        }
        onOpenChange(newOpen);
    };

    const openInNewTab = () => {
        if (url) {
            window.open(url.split('#')[0], "_blank");
        }
    };

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="!max-w-none w-[95vw] h-[95vh] p-0 flex flex-col">
                <DialogHeader className="px-6 py-4 border-b flex-shrink-0">
                    <div className="flex items-center justify-between">
                        <DialogTitle className="text-base font-medium truncate pr-4">
                            {documentName || "Document"}
                        </DialogTitle>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={openInNewTab}
                            disabled={!url}
                        >
                            Open in New Tab
                        </Button>
                    </div>
                </DialogHeader>
                <div className="flex-1 min-h-0">
                    {loading ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="text-muted-foreground">Loading document...</div>
                        </div>
                    ) : error || !url ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="text-muted-foreground">
                                {error || "Failed to load document"}
                            </div>
                        </div>
                    ) : (
                        <iframe
                            src={url}
                            className="w-full h-full border-0"
                            title={documentName || "Document"}
                        />
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}


interface DocumentPreviewPanelProps {
    /** Document name to display in header */
    documentName: string | null;
    /** Whether the preview is open */
    open: boolean;
    /** Callback to close the panel */
    onClose: () => void;
    /** Optional search term to highlight in PDF */
    searchTerm?: string;
}

/**
 * Reusable document preview panel component (sidebar).
 * Fetches and displays PDF documents via Next.js proxy.
 */
export function DocumentPreviewPanel({
    documentName,
    open,
    onClose,
    searchTerm,
}: DocumentPreviewPanelProps) {
    const [url, setUrl] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch document when opened
    useEffect(() => {
        if (!open || !documentName) {
            return;
        }

        let cancelled = false;

        async function fetchDocument() {
            setLoading(true);
            setError(null);
            setUrl(null);

            try {
                const proxyUrl = `/api/documents/${encodeURIComponent(documentName!)}`;
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

                if (!cancelled) {
                    setUrl(blobUrl);
                    setLoading(false);
                }
            } catch (err) {
                console.error("Failed to load document:", err);
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : "Failed to load document");
                    setLoading(false);
                }
            }
        }

        fetchDocument();

        return () => {
            cancelled = true;
        };
    }, [open, documentName, searchTerm]);

    // Cleanup and close
    const handleClose = () => {
        if (url) {
            URL.revokeObjectURL(url.split('#')[0]);
        }
        setUrl(null);
        setLoading(false);
        setError(null);
        onClose();
    };

    const openInNewTab = () => {
        if (url) {
            window.open(url.split('#')[0], "_blank");
        }
    };

    if (!open) return null;

    return (
        <div className="w-1/2 border-l border-border flex flex-col bg-background">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <div className="flex-1 min-w-0 mr-4">
                    <h3 className="text-sm font-medium truncate">{documentName}</h3>
                    {searchTerm && (
                        <p className="text-xs text-muted-foreground">Searching: {searchTerm}</p>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={openInNewTab}
                        disabled={!url}
                    >
                        <ExternalLink className="w-4 h-4" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={handleClose}>
                        <X className="w-4 h-4" />
                    </Button>
                </div>
            </div>
            {/* Document content */}
            <div className="flex-1 min-h-0">
                {loading ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-muted-foreground">Loading document...</div>
                    </div>
                ) : error || !url ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-muted-foreground">
                            {error || "Failed to load document"}
                        </div>
                    </div>
                ) : (
                    <iframe
                        src={url}
                        className="w-full h-full border-0"
                        title={documentName || "Document"}
                    />
                )}
            </div>
        </div>
    );
}
