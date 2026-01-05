"use client";

import { useEffect, useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    getLeasesGrouped,
    compareClauses,
    PropertyGroup,
    LeaseOption,
    ClauseData,
} from "@/lib/api";
import { Search, ChevronDown, X, Building2, FileText } from "lucide-react";

// Human-readable clause type labels
const CLAUSE_LABELS: Record<string, string> = {
    definitions: "Definitions",
    rent_payment: "Rent & Payment",
    security_deposit: "Security Deposit",
    maintenance_repairs: "Maintenance & Repairs",
    insurance: "Insurance",
    default_remedies: "Default & Remedies",
    termination: "Termination",
    assignment_subletting: "Assignment & Subletting",
    use_restrictions: "Use Restrictions",
    environmental: "Environmental",
    indemnification: "Indemnification",
    general_provisions: "General Provisions",
    schedules_exhibits: "Schedules & Exhibits",
    parties_recitals: "Parties & Recitals",
    other: "Other",
};

export default function ClauseComparisonPage() {
    // Data state
    const [properties, setProperties] = useState<PropertyGroup[]>([]);
    const [comparisons, setComparisons] = useState<Record<string, ClauseData[]>>({});
    const [selectedLeases, setSelectedLeases] = useState<LeaseOption[]>([]);

    // UI state
    const [isLoading, setIsLoading] = useState(true);
    const [isComparing, setIsComparing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState("");
    const [pickerOpen, setPickerOpen] = useState(false);

    // Load leases on mount
    useEffect(() => {
        async function loadLeases() {
            try {
                const data = await getLeasesGrouped();
                setProperties(data.properties);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load leases");
            } finally {
                setIsLoading(false);
            }
        }
        loadLeases();
    }, []);

    // Filter properties/leases by search
    const filteredProperties = useMemo(() => {
        if (!searchQuery.trim()) return properties;

        const query = searchQuery.toLowerCase();
        return properties
            .map((prop) => ({
                ...prop,
                leases: prop.leases.filter(
                    (l) =>
                        l.tenant_name.toLowerCase().includes(query) ||
                        l.trade_name?.toLowerCase().includes(query) ||
                        prop.property_address.toLowerCase().includes(query)
                ),
            }))
            .filter((prop) => prop.leases.length > 0);
    }, [properties, searchQuery]);

    // Check if a lease is selected
    const isSelected = (leaseId: number) =>
        selectedLeases.some((l) => l.id === leaseId);

    // Toggle lease selection
    const toggleLease = (lease: LeaseOption) => {
        if (isSelected(lease.id)) {
            setSelectedLeases((prev) => prev.filter((l) => l.id !== lease.id));
        } else {
            setSelectedLeases((prev) => [...prev, lease]);
        }
    };

    // Remove a selected lease
    const removeLease = (leaseId: number) => {
        setSelectedLeases((prev) => prev.filter((l) => l.id !== leaseId));
    };

    // Compare selected leases
    const handleCompare = async () => {
        if (selectedLeases.length < 2) return;

        setIsComparing(true);
        try {
            const result = await compareClauses(selectedLeases.map((l) => l.id));
            setComparisons(result.comparisons);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Comparison failed");
        } finally {
            setIsComparing(false);
        }
    };

    // Get clause types that have data
    const clauseTypes = useMemo(() => {
        return Object.keys(comparisons).sort((a, b) => {
            // Sort by predefined order
            const order = Object.keys(CLAUSE_LABELS);
            return order.indexOf(a) - order.indexOf(b);
        });
    }, [comparisons]);

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

    return (
        <ScrollArea className="h-full">
            <div className="p-6 bg-background min-h-full">
                {/* Lease Picker Card */}
                <Card className="mb-6">
                    <CardHeader className="pb-4">
                        <CardTitle className="text-base">Select Leases to Compare</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-wrap items-center gap-3">
                            {/* Lease Picker Popover */}
                            <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        className="h-9 gap-2 min-w-[200px] justify-between"
                                    >
                                        <span className="text-muted-foreground">Add leases...</span>
                                        <ChevronDown className="w-4 h-4" />
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-80 p-0" align="start">
                                    {/* Search */}
                                    <div className="p-3 border-b">
                                        <div className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                            <Input
                                                placeholder="Search tenants or properties..."
                                                value={searchQuery}
                                                onChange={(e) => setSearchQuery(e.target.value)}
                                                className="pl-9 h-9"
                                            />
                                        </div>
                                    </div>

                                    {/* Property Groups */}
                                    <ScrollArea className="h-72">
                                        <div className="p-2">
                                            {filteredProperties.length === 0 ? (
                                                <div className="text-sm text-muted-foreground text-center py-4">
                                                    No leases found
                                                </div>
                                            ) : (
                                                filteredProperties.map((prop) => (
                                                    <div key={prop.property_address} className="mb-3">
                                                        {/* Property Header */}
                                                        <div className="flex items-center gap-2 px-2 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                                                            <Building2 className="w-3 h-3" />
                                                            {prop.property_address}
                                                        </div>

                                                        {/* Leases */}
                                                        {prop.leases.map((lease) => (
                                                            <button
                                                                key={lease.id}
                                                                onClick={() => toggleLease(lease)}
                                                                className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors ${isSelected(lease.id)
                                                                    ? "bg-primary/10 text-primary"
                                                                    : "hover:bg-muted"
                                                                    }`}
                                                            >
                                                                <div
                                                                    className={`w-4 h-4 border rounded flex items-center justify-center ${isSelected(lease.id)
                                                                        ? "bg-primary border-primary"
                                                                        : "border-muted-foreground/30"
                                                                        }`}
                                                                >
                                                                    {isSelected(lease.id) && (
                                                                        <svg
                                                                            className="w-3 h-3 text-primary-foreground"
                                                                            fill="none"
                                                                            viewBox="0 0 24 24"
                                                                            stroke="currentColor"
                                                                        >
                                                                            <path
                                                                                strokeLinecap="round"
                                                                                strokeLinejoin="round"
                                                                                strokeWidth={2}
                                                                                d="M5 13l4 4L19 7"
                                                                            />
                                                                        </svg>
                                                                    )}
                                                                </div>
                                                                <span>
                                                                    {lease.trade_name || lease.tenant_name}
                                                                </span>
                                                            </button>
                                                        ))}
                                                    </div>
                                                ))
                                            )}
                                        </div>
                                    </ScrollArea>
                                </PopoverContent>
                            </Popover>

                            {/* Selected Leases as Badges */}
                            {selectedLeases.map((lease) => (
                                <div
                                    key={lease.id}
                                    className="flex items-center gap-1 px-3 py-1.5 bg-muted rounded-full text-sm"
                                >
                                    <span>{lease.trade_name || lease.tenant_name}</span>
                                    <button
                                        onClick={() => removeLease(lease.id)}
                                        className="ml-1 hover:text-destructive transition-colors"
                                    >
                                        <X className="w-3 h-3" />
                                    </button>
                                </div>
                            ))}

                            {/* Compare Button */}
                            <Button
                                onClick={handleCompare}
                                disabled={selectedLeases.length < 2 || isComparing}
                                className="ml-auto"
                            >
                                {isComparing ? "Comparing..." : "Compare Clauses"}
                            </Button>
                        </div>

                        {selectedLeases.length < 2 && selectedLeases.length > 0 && (
                            <p className="text-xs text-muted-foreground mt-2">
                                Select at least 2 leases to compare
                            </p>
                        )}
                    </CardContent>
                </Card>

                {/* Comparison Table */}
                {clauseTypes.length > 0 && (
                    <Card>
                        <CardHeader className="pb-4">
                            <CardTitle className="text-base flex items-center gap-2">
                                <FileText className="w-4 h-4" />
                                Clause Comparison
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="rounded-md border overflow-hidden">
                                <Table>
                                    <TableHeader>
                                        <TableRow className="bg-muted/50">
                                            <TableHead className="w-48 font-semibold">
                                                Clause Type
                                            </TableHead>
                                            {selectedLeases.map((lease) => (
                                                <TableHead key={lease.id} className="min-w-[250px]">
                                                    <div className="font-semibold">
                                                        {lease.trade_name || lease.tenant_name}
                                                    </div>
                                                </TableHead>
                                            ))}
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {clauseTypes.map((clauseType) => (
                                            <TableRow key={clauseType}>
                                                <TableCell className="font-medium align-top bg-muted/30">
                                                    {CLAUSE_LABELS[clauseType] || clauseType}
                                                </TableCell>
                                                {selectedLeases.map((lease) => {
                                                    const clauseData = comparisons[clauseType]?.find(
                                                        (c) => c.lease_id === lease.id
                                                    );

                                                    return (
                                                        <TableCell
                                                            key={lease.id}
                                                            className="align-top"
                                                        >
                                                            {clauseData ? (
                                                                <div className="space-y-2">
                                                                    {clauseData.article_reference && (
                                                                        <div className="text-xs text-muted-foreground">
                                                                            {clauseData.article_reference}
                                                                        </div>
                                                                    )}
                                                                    <p className="text-sm">
                                                                        {clauseData.summary}
                                                                    </p>
                                                                    {clauseData.key_terms && (
                                                                        <div className="flex flex-wrap gap-1 mt-2">
                                                                            {clauseData.key_terms
                                                                                .split(",")
                                                                                .map((term, i) => (
                                                                                    <span
                                                                                        key={i}
                                                                                        className="inline-block px-2 py-0.5 bg-primary/10 text-primary text-xs rounded"
                                                                                    >
                                                                                        {term.trim()}
                                                                                    </span>
                                                                                ))}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            ) : (
                                                                <span className="text-muted-foreground text-sm italic">
                                                                    Not found
                                                                </span>
                                                            )}
                                                        </TableCell>
                                                    );
                                                })}
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Empty State */}
                {clauseTypes.length === 0 && selectedLeases.length >= 2 && !isComparing && (
                    <Card>
                        <CardContent className="py-12 text-center">
                            <FileText className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                            <p className="text-muted-foreground">
                                No clause data available for the selected leases.
                            </p>
                            <p className="text-sm text-muted-foreground mt-1">
                                Clause data is extracted during document ingestion.
                            </p>
                        </CardContent>
                    </Card>
                )}

                {/* Initial State */}
                {selectedLeases.length === 0 && (
                    <Card>
                        <CardContent className="py-12 text-center">
                            <Building2 className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                            <p className="text-muted-foreground">
                                Select leases above to compare their clauses side-by-side.
                            </p>
                        </CardContent>
                    </Card>
                )}
            </div>
        </ScrollArea>
    );
}
