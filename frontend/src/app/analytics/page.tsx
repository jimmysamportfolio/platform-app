"use client";

import { useEffect, useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuRadioGroup,
    DropdownMenuRadioItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { getPortfolioSummary, deleteDocument, PortfolioSummary } from "@/lib/api";
import { TrendingUp, Search, SlidersHorizontal, ArrowUpDown, ChevronDown, Trash2 } from "lucide-react";

function formatCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined || isNaN(value)) return "$0";
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(value);
}

function formatNumber(value: number | null | undefined): string {
    if (value === null || value === undefined || isNaN(value)) return "0";
    return new Intl.NumberFormat("en-US").format(Math.round(value));
}

type SortOption = "tenant" | "expiry" | "sqft" | "deposit";

export default function AnalyticsPage() {
    const [data, setData] = useState<PortfolioSummary | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    // Search, filter, sort state
    const [search, setSearch] = useState("");
    const [filterBuilding, setFilterBuilding] = useState<string>("all");
    const [sortBy, setSortBy] = useState<SortOption>("tenant");

    // Delete state
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [deletingDoc, setDeletingDoc] = useState<{ name: string; display: string } | null>(null);
    const [isDeleting, setIsDeleting] = useState(false);

    // Document preview state
    const [previewOpen, setPreviewOpen] = useState(false);
    const [previewDoc, setPreviewDoc] = useState<{ name: string; url: string | null; loading?: boolean } | null>(null);

    async function fetchData() {
        setIsLoading(true);
        try {
            const summary = await getPortfolioSummary();
            setData(summary);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load data");
        } finally {
            setIsLoading(false);
        }
    }

    useEffect(() => {
        fetchData();
    }, []);

    // Get unique buildings for filter
    const buildings = useMemo(() => {
        if (!data?.lease_breakdown) return [];
        const unique = [...new Set(data.lease_breakdown.map(l => l.property).filter(Boolean))];
        return unique.sort();
    }, [data]);

    // Filtered and sorted leases
    const filteredLeases = useMemo(() => {
        if (!data?.lease_breakdown) return [];

        let result = [...data.lease_breakdown];

        // Apply search
        if (search.trim()) {
            const searchLower = search.toLowerCase();
            result = result.filter(
                l =>
                    l.tenant?.toLowerCase().includes(searchLower) ||
                    l.trade_name?.toLowerCase().includes(searchLower) ||
                    l.property?.toLowerCase().includes(searchLower)
            );
        }

        // Apply building filter
        if (filterBuilding !== "all") {
            result = result.filter(l => l.property === filterBuilding);
        }

        // Apply sort
        result.sort((a, b) => {
            switch (sortBy) {
                case "expiry":
                    return (a.end_date || "").localeCompare(b.end_date || "");
                case "sqft":
                    return (b.sqft || 0) - (a.sqft || 0);
                case "deposit":
                    return (b.deposit || 0) - (a.deposit || 0);
                default:
                    return (a.trade_name || a.tenant || "").localeCompare(b.trade_name || b.tenant || "");
            }
        });

        return result;
    }, [data, search, filterBuilding, sortBy]);

    const handleRowClick = async (lease: PortfolioSummary["lease_breakdown"][0]) => {
        // Fetch PDF as blob to avoid cross-origin iframe issues
        setPreviewDoc({ name: lease.document_name, url: null, loading: true });
        setPreviewOpen(true);

        try {
            // Use local Next.js proxy to fetch document
            const proxyUrl = `/api/documents/${encodeURIComponent(lease.document_name)}`;
            const response = await fetch(proxyUrl);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const blob = await response.blob();
            const blobUrl = URL.createObjectURL(blob);
            setPreviewDoc({ name: lease.document_name, url: blobUrl, loading: false });
        } catch (error) {
            console.error("Failed to load document:", error);
            setPreviewDoc({ name: lease.document_name, url: null, loading: false });
        }
    };

    const handleDeleteClick = (e: React.MouseEvent, lease: PortfolioSummary["lease_breakdown"][0]) => {
        e.stopPropagation(); // Prevent row click

        // Use the exact document name for deletion
        setDeletingDoc({ name: lease.document_name, display: lease.trade_name || lease.tenant });
        setDeleteOpen(true);
    };

    const confirmDelete = async () => {
        if (!deletingDoc || isDeleting) return;

        // Close modal immediately to prevent multiple clicks
        setIsDeleting(true);
        setDeleteOpen(false);

        try {
            await deleteDocument(deletingDoc.name);
            setDeletingDoc(null);
            fetchData(); // Refresh list
        } catch (err) {
            alert("Failed to delete: " + (err instanceof Error ? err.message : "Unknown error"));
        } finally {
            setIsDeleting(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-muted-foreground text-sm">Loading...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-sm text-muted-foreground">{error}</div>
            </div>
        );
    }

    if (!data) return null;


    return (
        <ScrollArea className="h-full">
            <div className="p-6 bg-background min-h-full">
                {/* Metric Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between pb-2">
                            <CardTitle className="text-sm font-medium text-muted-foreground">
                                Total Leases
                            </CardTitle>
                            <TrendingUp className="w-4 h-4 text-muted-foreground" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-semibold">{data.total_leases}</div>
                            <p className="text-xs text-muted-foreground mt-1">Active leases</p>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between pb-2">
                            <CardTitle className="text-sm font-medium text-muted-foreground">
                                Total Area
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-semibold">{formatNumber(data.total_sqft)}</div>
                            <p className="text-xs text-muted-foreground mt-1">Square feet</p>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between pb-2">
                            <CardTitle className="text-sm font-medium text-muted-foreground">
                                Security Deposits
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-semibold">{formatCurrency(data.total_deposits)}</div>
                            <p className="text-xs text-muted-foreground mt-1">Total held</p>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between pb-2">
                            <CardTitle className="text-sm font-medium text-muted-foreground">
                                Avg Rent/SF
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-semibold">{formatCurrency(data.average_rent_psf)}</div>
                            <p className="text-xs text-muted-foreground mt-1">Per square foot</p>
                        </CardContent>
                    </Card>
                </div>

                {/* Lease Breakdown */}
                <Card>
                    <CardHeader className="pb-4">
                        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                            {/* Title - LEFT */}
                            <CardTitle className="text-base whitespace-nowrap">Lease Breakdown</CardTitle>

                            {/* Search, Filter, Sort controls - RIGHT of Title */}
                            <div className="flex items-center gap-2 w-full sm:w-auto">
                                {/* Search */}
                                <div className="relative">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                    <Input
                                        placeholder="Search..."
                                        value={search}
                                        onChange={(e) => setSearch(e.target.value)}
                                        className="pl-9 w-48 h-9 bg-muted border-0 focus-visible:ring-0"
                                    />
                                </div>

                                {/* Filter by Building */}
                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                        <Button variant="ghost" size="sm" className="h-9 gap-1 bg-muted hover:bg-muted/80 focus-visible:ring-0">
                                            <SlidersHorizontal className="w-4 h-4" />
                                            Filter
                                            <ChevronDown className="w-3 h-3" />
                                        </Button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="start" className="w-56">
                                        <DropdownMenuRadioGroup value={filterBuilding} onValueChange={setFilterBuilding}>
                                            <DropdownMenuRadioItem value="all">All Buildings</DropdownMenuRadioItem>
                                            {buildings.map((building) => (
                                                <DropdownMenuRadioItem key={building} value={building || ""}>
                                                    {building}
                                                </DropdownMenuRadioItem>
                                            ))}
                                        </DropdownMenuRadioGroup>
                                    </DropdownMenuContent>
                                </DropdownMenu>

                                {/* Sort */}
                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                        <Button variant="ghost" size="sm" className="h-9 gap-1 bg-muted hover:bg-muted/80 focus-visible:ring-0">
                                            <ArrowUpDown className="w-4 h-4" />
                                            Sort
                                            <ChevronDown className="w-3 h-3" />
                                        </Button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="start" className="w-48">
                                        <DropdownMenuRadioGroup value={sortBy} onValueChange={(v) => setSortBy(v as SortOption)}>
                                            <DropdownMenuRadioItem value="tenant">Tenant Name</DropdownMenuRadioItem>
                                            <DropdownMenuRadioItem value="expiry">Expiry Date</DropdownMenuRadioItem>
                                            <DropdownMenuRadioItem value="sqft">Area (SF)</DropdownMenuRadioItem>
                                            <DropdownMenuRadioItem value="deposit">Deposit</DropdownMenuRadioItem>
                                        </DropdownMenuRadioGroup>
                                    </DropdownMenuContent>
                                </DropdownMenu>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Tenant</TableHead>
                                    <TableHead>Property</TableHead>
                                    <TableHead className="text-right">Area</TableHead>
                                    <TableHead className="text-right">Term</TableHead>
                                    <TableHead className="text-right">Deposit</TableHead>
                                    <TableHead>Expiration</TableHead>
                                    <TableHead className="w-[50px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filteredLeases.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                                            No leases found
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    filteredLeases.map((lease) => (
                                        <TableRow
                                            key={lease.id}
                                            className="cursor-pointer hover:bg-muted/50 transition-colors group"
                                            onClick={() => handleRowClick(lease)}
                                        >
                                            <TableCell className="font-medium">
                                                {lease.trade_name || lease.tenant}
                                            </TableCell>
                                            <TableCell className="text-muted-foreground">
                                                {lease.property || "-"}
                                            </TableCell>
                                            <TableCell className="text-right">
                                                {formatNumber(lease.sqft)} SF
                                            </TableCell>
                                            <TableCell className="text-right">
                                                {lease.term_years || "-"} yrs
                                            </TableCell>
                                            <TableCell className="text-right">
                                                {formatCurrency(lease.deposit)}
                                            </TableCell>
                                            <TableCell>{lease.end_date || "-"}</TableCell>
                                            <TableCell>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="opacity-0 group-hover:opacity-100 h-8 w-8 text-muted-foreground hover:text-destructive"
                                                    onClick={(e) => handleDeleteClick(e, lease)}
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table >
                    </CardContent >
                </Card >
            </div >

            {/* Delete Confirmation Dialog */}
            < Dialog open={deleteOpen} onOpenChange={setDeleteOpen} >
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete Lease?</DialogTitle>
                    </DialogHeader>
                    <div className="py-4 text-sm text-muted-foreground">
                        Are you sure you want to delete the lease for <span className="font-medium text-foreground">{deletingDoc?.display}</span>? This action cannot be undone.
                    </div>
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" onClick={() => setDeleteOpen(false)}>Cancel</Button>
                        <Button variant="destructive" onClick={confirmDelete}>Delete</Button>
                    </div>
                </DialogContent>
            </Dialog >

            {/* Document Preview Modal */}
            <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
                <DialogContent className="!max-w-none w-[95vw] h-[95vh] p-0 flex flex-col">
                    <DialogHeader className="px-6 py-4 border-b flex-shrink-0">
                        <div className="flex items-center justify-between">
                            <DialogTitle className="text-base font-medium truncate pr-4">
                                {previewDoc?.name || "Document"}
                            </DialogTitle>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => previewDoc?.url && window.open(previewDoc.url, "_blank")}
                            >
                                Open in New Tab
                            </Button>
                        </div>
                    </DialogHeader>
                    <div className="flex-1 min-h-0">
                        {previewDoc?.loading ? (
                            <div className="flex items-center justify-center h-full">
                                <div className="text-muted-foreground">Loading document...</div>
                            </div>
                        ) : previewDoc?.url ? (
                            <iframe
                                src={previewDoc.url}
                                className="w-full h-full border-0"
                                title={previewDoc.name}
                            />
                        ) : (
                            <div className="flex items-center justify-center h-full">
                                <div className="text-muted-foreground">Failed to load document</div>
                            </div>
                        )}
                    </div>
                </DialogContent>
            </Dialog>
        </ScrollArea >
    );
}
