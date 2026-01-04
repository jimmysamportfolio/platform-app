"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Search, Eye } from "lucide-react";
import { getDocuments, getDocumentContent, LeaseDocument } from "@/lib/api";

export default function DocumentsPage() {
    const [documents, setDocuments] = useState<LeaseDocument[]>([]);
    const [filteredDocs, setFilteredDocs] = useState<LeaseDocument[]>([]);
    const [search, setSearch] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    const [viewerOpen, setViewerOpen] = useState(false);
    const [viewingDoc, setViewingDoc] = useState<{ filename: string; content: string } | null>(null);
    const [viewerLoading, setViewerLoading] = useState(false);

    useEffect(() => {
        async function fetchDocuments() {
            try {
                const response = await getDocuments();
                setDocuments(response.documents);
                setFilteredDocs(response.documents);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load documents");
            } finally {
                setIsLoading(false);
            }
        }
        fetchDocuments();
    }, []);

    useEffect(() => {
        if (!search.trim()) {
            setFilteredDocs(documents);
        } else {
            const searchLower = search.toLowerCase();
            setFilteredDocs(
                documents.filter(
                    (doc) =>
                        doc.tenant_name?.toLowerCase().includes(searchLower) ||
                        doc.trade_name?.toLowerCase().includes(searchLower)
                )
            );
        }
    }, [search, documents]);

    const handleViewDocument = async (doc: LeaseDocument) => {
        setViewerLoading(true);
        setViewerOpen(true);
        try {
            const content = await getDocumentContent(doc.document_name);
            setViewingDoc(content);
        } catch (err) {
            setViewingDoc({
                filename: doc.document_name,
                content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
            });
        } finally {
            setViewerLoading(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-full bg-muted/30">
                <div className="text-muted-foreground text-sm">Loading...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-full bg-muted/30">
                <div className="text-sm text-muted-foreground">{error}</div>
            </div>
        );
    }

    return (
        <ScrollArea className="h-full">
            <div className="p-6 bg-muted/30 min-h-full">
                {/* Search */}
                <div className="mb-4 relative max-w-sm">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                        placeholder="Search tenants..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="pl-9 bg-card"
                    />
                </div>

                {/* Documents Table */}
                <Card className="bg-card">
                    <CardHeader>
                        <CardTitle className="text-base">
                            Documents {filteredDocs.length !== documents.length && `(${filteredDocs.length})`}
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {filteredDocs.length === 0 ? (
                            <p className="text-muted-foreground text-sm text-center py-8">
                                No documents found
                            </p>
                        ) : (
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Tenant</TableHead>
                                        <TableHead>Property</TableHead>
                                        <TableHead>Term</TableHead>
                                        <TableHead>Expiration</TableHead>
                                        <TableHead className="text-right">Actions</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {filteredDocs.map((doc) => (
                                        <TableRow key={doc.id}>
                                            <TableCell className="font-medium">
                                                {doc.trade_name || doc.tenant_name}
                                            </TableCell>
                                            <TableCell className="text-muted-foreground">
                                                {doc.property_address}
                                            </TableCell>
                                            <TableCell>{doc.term_years} yrs</TableCell>
                                            <TableCell>{doc.expiration_date}</TableCell>
                                            <TableCell className="text-right">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => handleViewDocument(doc)}
                                                >
                                                    <Eye className="w-4 h-4 mr-1" />
                                                    View
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        )}
                    </CardContent>
                </Card>
            </div>

            <Dialog open={viewerOpen} onOpenChange={setViewerOpen}>
                <DialogContent className="max-w-4xl max-h-[80vh]">
                    <DialogHeader>
                        <DialogTitle className="text-sm font-medium">
                            {viewingDoc?.filename || "Loading..."}
                        </DialogTitle>
                    </DialogHeader>
                    <ScrollArea className="h-[60vh] mt-4">
                        {viewerLoading ? (
                            <div className="text-muted-foreground text-sm">Loading...</div>
                        ) : (
                            <pre className="text-xs whitespace-pre-wrap font-mono bg-muted p-4 rounded">
                                {viewingDoc?.content}
                            </pre>
                        )}
                    </ScrollArea>
                </DialogContent>
            </Dialog>
        </ScrollArea>
    );
}
