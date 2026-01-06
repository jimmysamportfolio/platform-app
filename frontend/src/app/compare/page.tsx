"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
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
    getLeasesGrouped,
    compareClauses,
    PropertyGroup,
    LeaseOption,
    ClauseData,
} from "@/lib/api";
import { Search, ChevronDown, X, Building2, FileText, Loader2 } from "lucide-react";

// Human-readable clause type labels (matches STANDARD_CLAUSE_TYPES in extractor.py)
const CLAUSE_LABELS: Record<string, string> = {
    rent_payment: "Rent & Payment",
    security_deposit: "Security Deposit",
    term_renewal: "Term & Renewal",
    use_restrictions: "Use Restrictions",
    maintenance_repairs: "Maintenance & Repairs",
    insurance: "Insurance",
    termination: "Termination",
    assignment_subletting: "Assignment & Subletting",
    default_remedies: "Default & Remedies",
};

// Order for displaying clause types
const CLAUSE_ORDER = [
    "rent_payment",
    "security_deposit",
    "term_renewal",
    "use_restrictions",
    "maintenance_repairs",
    "insurance",
    "termination",
    "assignment_subletting",
    "default_remedies",
];

// Helper to format clause type for display
const formatClauseType = (type: string): string => {
    if (CLAUSE_LABELS[type]) return CLAUSE_LABELS[type];
    // Fallback: convert snake_case to Title Case
    return type.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
};

// Helper to render markdown bold (**text**) as styled spans
const renderBoldText = (text: string): React.ReactNode => {
    // Split by **bold** markdown pattern
    const parts = text.split(/\*\*([^*]+)\*\*/g);

    return parts.map((part, i) => {
        // Odd indices are the bold content (captured group)
        if (i % 2 === 1) {
            return (
                <span key={i} className="font-semibold text-foreground">
                    {part}
                </span>
            );
        }
        return part;
    });
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

    // Auto-compare when selection changes (2+ leases)
    const doCompare = useCallback(async (leases: LeaseOption[]) => {
        if (leases.length < 2) {
            setComparisons({});
            return;
        }

        setIsComparing(true);
        try {
            const result = await compareClauses(leases.map((l) => l.id));
            setComparisons(result.comparisons);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Comparison failed");
        } finally {
            setIsComparing(false);
        }
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

    // Toggle lease selection - auto-compare on change
    const toggleLease = (lease: LeaseOption) => {
        let newSelection: LeaseOption[];
        if (isSelected(lease.id)) {
            newSelection = selectedLeases.filter((l) => l.id !== lease.id);
        } else {
            newSelection = [...selectedLeases, lease];
        }
        setSelectedLeases(newSelection);
        doCompare(newSelection);
    };

    // Remove a selected lease
    const removeLease = (leaseId: number) => {
        const newSelection = selectedLeases.filter((l) => l.id !== leaseId);
        setSelectedLeases(newSelection);
        doCompare(newSelection);
    };

    // Get clause types that have data, sorted by CLAUSE_ORDER
    const clauseTypes = useMemo(() => {
        return Object.keys(comparisons).sort((a, b) => {
            const aIndex = CLAUSE_ORDER.indexOf(a);
            const bIndex = CLAUSE_ORDER.indexOf(b);
            // Put unknown types at the end
            if (aIndex === -1 && bIndex === -1) return a.localeCompare(b);
            if (aIndex === -1) return 1;
            if (bIndex === -1) return -1;
            return aIndex - bIndex;
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

                            {/* Loading indicator */}
                            {isComparing && (
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Loading...
                                </div>
                            )}
                        </div>

                        {selectedLeases.length === 1 && (
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
                        <CardContent className="p-0">
                            {/* Horizontal scroll wrapper */}
                            <div className="overflow-x-auto">
                                <table className="w-full border-collapse min-w-max">
                                    <thead>
                                        <tr className="bg-muted/50 border-b">
                                            <th className="w-36 min-w-36 max-w-36 px-4 py-3 text-left text-sm font-semibold sticky left-0 bg-muted/50 z-10">
                                                Clause
                                            </th>
                                            {selectedLeases.map((lease) => (
                                                <th
                                                    key={lease.id}
                                                    className="w-64 min-w-64 max-w-64 px-4 py-3 text-left text-sm font-semibold border-l"
                                                >
                                                    {lease.trade_name || lease.tenant_name}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {clauseTypes.map((clauseType) => (
                                            <tr key={clauseType} className="border-b hover:bg-muted/20">
                                                <td className="w-36 min-w-36 max-w-36 px-4 py-4 text-sm font-medium bg-muted/30 sticky left-0 z-10 align-top">
                                                    {formatClauseType(clauseType)}
                                                </td>
                                                {selectedLeases.map((lease) => {
                                                    const clauseData = comparisons[clauseType]?.find(
                                                        (c) => c.lease_id === lease.id
                                                    );

                                                    return (
                                                        <td
                                                            key={lease.id}
                                                            className="w-64 min-w-64 max-w-64 px-4 py-4 align-top border-l"
                                                        >
                                                            {clauseData ? (
                                                                <div className="space-y-2">
                                                                    {clauseData.article_reference && (
                                                                        <div className="text-xs text-muted-foreground font-medium">
                                                                            {clauseData.article_reference}
                                                                        </div>
                                                                    )}
                                                                    <div className="text-sm leading-relaxed text-muted-foreground">
                                                                        {renderBoldText(clauseData.summary)}
                                                                    </div>
                                                                    {clauseData.key_terms && (
                                                                        <div className="flex flex-wrap gap-1 pt-1">
                                                                            {clauseData.key_terms
                                                                                .split(",")
                                                                                .slice(0, 5)
                                                                                .map((term, i) => (
                                                                                    <span
                                                                                        key={i}
                                                                                        className="inline-block px-2 py-0.5 bg-primary/10 text-primary text-xs rounded font-medium"
                                                                                    >
                                                                                        {term.trim()}
                                                                                    </span>
                                                                                ))}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            ) : (
                                                                <span className="text-muted-foreground text-sm italic">
                                                                    —
                                                                </span>
                                                            )}
                                                        </td>
                                                    );
                                                })}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Empty State - No clause data after comparison */}
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
