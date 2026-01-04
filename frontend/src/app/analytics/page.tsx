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
import { getPortfolioSummary, getDocumentContent, PortfolioSummary } from "@/lib/api";
import { TrendingUp, Search, SlidersHorizontal, ArrowUpDown, ChevronDown } from "lucide-react";

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

    // Document viewer state
    const [viewerOpen, setViewerOpen] = useState(false);
    const [viewingDoc, setViewingDoc] = useState<{ filename: string; content: string } | null>(null);
    const [viewerLoading, setViewerLoading] = useState(false);

    useEffect(() => {
        async function fetchData() {
            try {
                const summary = await getPortfolioSummary();
                setData(summary);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load data");
            } finally {
                setIsLoading(false);
            }
        }
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
        setViewerLoading(true);
        setViewerOpen(true);
        try {
            const docName = lease.trade_name || lease.tenant;
            const content = await getDocumentContent(docName);
            setViewingDoc(content);
        } catch (err) {
            setViewingDoc({
                filename: lease.trade_name || lease.tenant,
                content: `Error loading document: ${err instanceof Error ? err.message : "Unknown error"}`,
            });
        } finally {
            setViewerLoading(false);
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
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                            {/* Search, Filter, Sort controls - LEFT */}
                            <div className="flex items-center gap-2">
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

                            {/* Title - RIGHT */}
                            <CardTitle className="text-base">Lease Breakdown</CardTitle>
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
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filteredLeases.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                                            No leases found
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    filteredLeases.map((lease) => (
                                        <TableRow
                                            key={lease.id}
                                            className="cursor-pointer hover:bg-muted/50 transition-colors"
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
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            </div>

            {/* Document Viewer Dialog */}
            <Dialog open={viewerOpen} onOpenChange={setViewerOpen}>
                <DialogContent className="max-w-4xl max-h-[85vh]">
                    <DialogHeader>
                        <DialogTitle className="text-base font-medium">
                            {viewingDoc?.filename || "Loading..."}
                        </DialogTitle>
                    </DialogHeader>
                    <ScrollArea className="h-[65vh] mt-4">
                        {viewerLoading ? (
                            <div className="text-muted-foreground text-sm">Loading document...</div>
                        ) : (
                            <pre className="text-sm whitespace-pre-wrap font-mono bg-muted p-4 rounded-lg">
                                {viewingDoc?.content}
                            </pre>
                        )}
                    </ScrollArea>
                </DialogContent>
            </Dialog>
        </ScrollArea>
    );
}
