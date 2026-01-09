"use client";

import { useEffect, useState, useCallback } from "react";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
    WS_BASE_URL,
    PendingFile,
    getPendingFiles,
    processIngestion,
} from "@/lib/api";
import { FileTextIcon, ZapIcon, LayersIcon, LoaderIcon } from "lucide-react";

export function IngestionModal() {
    const [isOpen, setIsOpen] = useState(false);
    const [pendingFile, setPendingFile] = useState<PendingFile | null>(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const [processingMode, setProcessingMode] = useState<string | null>(null);

    // Check for pending files once on mount (in case files were detected before WebSocket connected)
    const checkPendingFiles = useCallback(async () => {
        try {
            const response = await getPendingFiles();
            if (response.pending_files.length > 0 && !isProcessing) {
                setPendingFile(response.pending_files[0]);
                setIsOpen(true);
            }
        } catch (error) {
            console.error("Failed to check pending files:", error);
        }
    }, [isProcessing]);

    useEffect(() => {
        // Check immediately on mount
        checkPendingFiles();

        // Set up WebSocket connection for real-time notifications
        let ws: WebSocket | null = null;
        let reconnectTimeout: NodeJS.Timeout;

        const connectWebSocket = () => {
            try {
                ws = new WebSocket(`${WS_BASE_URL}/ws/ingestion`);

                ws.onopen = () => {
                    console.log("📡 Ingestion WebSocket connected");
                };

                ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.type === "new_file" && !isProcessing) {
                            setPendingFile({
                                file_path: data.file_path,
                                file_name: data.file_name,
                                detected_at: new Date().toISOString(),
                            });
                            setIsOpen(true);
                        }
                    } catch (e) {
                        console.error("Failed to parse WebSocket message:", e);
                    }
                };

                ws.onclose = () => {
                    console.log("📡 WebSocket disconnected, reconnecting...");
                    reconnectTimeout = setTimeout(connectWebSocket, 3000);
                };

                ws.onerror = (error) => {
                    console.error("WebSocket error:", error);
                };
            } catch (error) {
                console.error("Failed to connect WebSocket:", error);
                reconnectTimeout = setTimeout(connectWebSocket, 3000);
            }
        };

        connectWebSocket();

        return () => {
            if (ws) ws.close();
            clearTimeout(reconnectTimeout);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleProcess = async (mode: "full" | "clause_only") => {
        if (!pendingFile) return;

        const filePath = pendingFile.file_path;
        const fileName = pendingFile.file_name;

        // Close modal immediately
        setIsOpen(false);
        setPendingFile(null);

        // Process in background (fire and forget)
        processIngestion(filePath, mode)
            .then((result) => {
                if (result.success) {
                    console.log(`✅ Successfully processed: ${result.file_name}`);
                } else {
                    console.error(`❌ Failed: ${result.error}`);
                }
            })
            .catch((error) => {
                console.error(`❌ Processing failed for ${fileName}:`, error);
            });
    };

    if (!pendingFile) return null;

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !isProcessing && setIsOpen(open)}>
            <DialogContent
                showCloseButton={!isProcessing}
                className="!max-w-[600px] !w-[600px] p-0"
            >
                <div className="p-6">
                    <DialogHeader className="mb-4">
                        <DialogTitle className="flex items-center gap-2 text-lg">
                            <FileTextIcon className="h-5 w-5 text-primary flex-shrink-0" />
                            New Document Detected
                        </DialogTitle>
                        <DialogDescription className="mt-2">
                            A new file has been added to the input folder. Choose how to process it.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="rounded-lg border bg-muted/50 p-4 mb-6 overflow-hidden">
                        <p className="font-medium text-sm truncate max-w-full" title={pendingFile.file_name}>
                            {pendingFile.file_name}
                        </p>
                    </div>

                    <div className="flex flex-col gap-3">
                        <Button
                            variant="outline"
                            size="lg"
                            className="w-full justify-center"
                            onClick={() => handleProcess("clause_only")}
                            disabled={isProcessing}
                        >
                            {isProcessing && processingMode === "clause_only" ? (
                                <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <ZapIcon className="mr-2 h-4 w-4" />
                            )}
                            Quick Extract
                            <span className="ml-2 text-xs text-muted-foreground">(Clauses only)</span>
                        </Button>
                        <Button
                            size="lg"
                            className="w-full justify-center"
                            onClick={() => handleProcess("full")}
                            disabled={isProcessing}
                        >
                            {isProcessing && processingMode === "full" ? (
                                <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <LayersIcon className="mr-2 h-4 w-4" />
                            )}
                            Full Extraction
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
