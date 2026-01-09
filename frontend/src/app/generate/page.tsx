"use client";

import { useState, useRef, useCallback, KeyboardEvent } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { generateDocument, GenerateDocumentInput, RentRowInput } from "@/lib/api";
import { FilePlus, Download, Loader2, Plus, Trash2, ArrowDown } from "lucide-react";

// Field configuration for the form - simpler labels with format hints
const FIELD_CONFIG = [
    // Parties Section
    {
        section: "Parties", fields: [
            { name: "tenant_name", label: "Tenant Name", placeholder: "ACME Corporation Ltd." },
            { name: "tenant_address", label: "Tenant Address", placeholder: "123 Main Street, Vancouver, BC V6B 1A1" },
            { name: "indemnifier_name", label: "Indemnifier Name", placeholder: "John Smith" },
            { name: "indemnifier_address", label: "Indemnifier Address", placeholder: "456 Oak Avenue, Vancouver, BC" },
        ]
    },
    // Premises Section
    {
        section: "Premises", fields: [
            { name: "premises_unit", label: "Unit Number", placeholder: "170" },
            { name: "rentable_area", label: "Rentable Area (sq ft)", placeholder: "1761", type: "number" },
        ]
    },
    // Term & Dates Section
    {
        section: "Term & Dates", fields: [
            { name: "lease_date", label: "Lease Date", placeholder: "July 13, 2020" },
            { name: "initial_term", label: "Initial Term (years)", placeholder: "10", type: "number" },
            { name: "renewal_option_count", label: "# of Renewal Options", placeholder: "2", type: "number" },
            { name: "renewal_option_years", label: "Years per Renewal", placeholder: "5", type: "number" },
            { name: "possession_date", label: "Possession Date", placeholder: "February 1, 2026" },
            { name: "fixturing_period", label: "Fixturing Period (days)", placeholder: "90", type: "number" },
            { name: "offer_to_lease_date", label: "Offer to Lease Date", placeholder: "December 1, 2025" },
            { name: "indemnity_date", label: "Indemnity Agreement Date", placeholder: "January 15, 2026" },
        ]
    },
    // Financials Section
    {
        section: "Financials", fields: [
            { name: "deposit", label: "Security Deposit ($)", placeholder: "20000", type: "number" },
            { name: "tenant_improvement_allowance", label: "TI Allowance ($/sq ft)", placeholder: "25", type: "number" },
        ]
    },
    // Use & Restrictions Section
    {
        section: "Use & Restrictions", fields: [
            { name: "permitted_use", label: "Permitted Use", placeholder: "Restaurant and take-out food service" },
            { name: "trade_name", label: "Trade Name", placeholder: "Church's Chicken" },
            { name: "exclusive_use", label: "Exclusive Use - Business Type", placeholder: "selling fried chicken" },
            { name: "radius_restriction", label: "Radius Restriction (if any)", placeholder: "5 km" },
        ]
    },
];

// Get all field names in order for keyboard navigation
const ALL_FIELDS = FIELD_CONFIG.flatMap(section => section.fields.map(f => f.name));

export default function GenerateDocumentPage() {
    // Form state
    const [formData, setFormData] = useState<Record<string, string>>({});
    const [rentSchedule, setRentSchedule] = useState<RentRowInput[]>([
        { lease_year_start: 1, lease_year_end: 3, per_sqft: 0, per_annum: 0, per_month: 0 },
    ]);

    // UI state
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    // Refs for keyboard navigation
    const inputRefs = useRef<Record<string, HTMLInputElement | null>>({});

    // Handle input change
    const handleChange = (name: string, value: string) => {
        setFormData(prev => ({ ...prev, [name]: value }));
        setError(null);
        setSuccess(false);
    };

    // Handle keyboard navigation (down arrow moves to next field)
    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>, currentField: string) => {
        if (e.key === "ArrowDown" || (e.key === "Enter" && !e.shiftKey)) {
            e.preventDefault();
            const currentIndex = ALL_FIELDS.indexOf(currentField);
            if (currentIndex < ALL_FIELDS.length - 1) {
                const nextField = ALL_FIELDS[currentIndex + 1];
                inputRefs.current[nextField]?.focus();
            }
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            const currentIndex = ALL_FIELDS.indexOf(currentField);
            if (currentIndex > 0) {
                const prevField = ALL_FIELDS[currentIndex - 1];
                inputRefs.current[prevField]?.focus();
            }
        }
    };

    // Rent schedule handlers
    const addRentRow = () => {
        const lastRow = rentSchedule[rentSchedule.length - 1];
        const newStart = lastRow ? lastRow.lease_year_end + 1 : 1;
        setRentSchedule([...rentSchedule, {
            lease_year_start: newStart,
            lease_year_end: newStart + 2,
            per_sqft: 0,
            per_annum: 0,
            per_month: 0,
        }]);
    };

    const removeRentRow = (index: number) => {
        if (rentSchedule.length > 1) {
            setRentSchedule(rentSchedule.filter((_, i) => i !== index));
        }
    };

    const updateRentRow = (index: number, field: keyof RentRowInput, value: number) => {
        const updated = [...rentSchedule];
        updated[index] = { ...updated[index], [field]: value };
        setRentSchedule(updated);
    };

    // Generate document
    const handleGenerate = async () => {
        setIsGenerating(true);
        setError(null);
        setSuccess(false);

        try {
            const input: GenerateDocumentInput = {
                tenant_name: formData.tenant_name || "",
                tenant_address: formData.tenant_address || "",
                indemnifier_name: formData.indemnifier_name || "",
                indemnifier_address: formData.indemnifier_address || "",
                premises_unit: formData.premises_unit || "",
                rentable_area: formData.rentable_area || "",
                lease_date: formData.lease_date || "",
                initial_term: formData.initial_term || "",
                renewal_option_count: parseInt(formData.renewal_option_count) || 0,
                renewal_option_years: parseInt(formData.renewal_option_years) || 0,
                possession_date: formData.possession_date || "",
                fixturing_period: formData.fixturing_period || "",
                offer_to_lease_date: formData.offer_to_lease_date || "",
                indemnity_date: formData.indemnity_date || "",
                rent_schedule: rentSchedule,
                deposit: formData.deposit || "",
                tenant_improvement_allowance: formData.tenant_improvement_allowance || "",
                permitted_use: formData.permitted_use || "",
                trade_name: formData.trade_name || "",
                exclusive_use: formData.exclusive_use || "",
                radius_restriction: formData.radius_restriction || "",
            };

            const blob = await generateDocument(input);

            // Trigger download
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `Lease_${input.trade_name || input.tenant_name || "Generated"}.docx`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            setSuccess(true);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to generate document");
        } finally {
            setIsGenerating(false);
        }
    };

    return (
        <ScrollArea className="h-full">
            <div className="p-6 bg-background min-h-full max-w-4xl mx-auto">
                {/* Header */}
                <div className="mb-6">
                    <h1 className="text-2xl font-semibold flex items-center gap-2">
                        <FilePlus className="w-6 h-6" />
                        Generate Lease Document
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        Fill in the fields below to generate a populated lease document.
                        Use <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs">↓</kbd> or
                        <kbd className="px-1.5 py-0.5 bg-muted rounded text-xs ml-1">Enter</kbd> to navigate between fields.
                    </p>
                </div>

                {/* Form Sections */}
                {FIELD_CONFIG.map((section) => (
                    <Card key={section.section} className="mb-4">
                        <CardHeader className="pb-3">
                            <CardTitle className="text-base">{section.section}</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {section.fields.map((field) => (
                                    <div key={field.name} className="space-y-1.5">
                                        <label className="text-sm font-medium text-foreground">
                                            {field.label}
                                        </label>
                                        <Input
                                            ref={(el) => { inputRefs.current[field.name] = el; }}
                                            type={field.type || "text"}
                                            placeholder={field.placeholder}
                                            value={formData[field.name] || ""}
                                            onChange={(e) => handleChange(field.name, e.target.value)}
                                            onKeyDown={(e) => handleKeyDown(e, field.name)}
                                            className="h-9"
                                        />
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                ))}

                {/* Rent Schedule Section */}
                <Card className="mb-6">
                    <CardHeader className="pb-3">
                        <CardTitle className="text-base">Basic Rent Schedule</CardTitle>
                        <CardDescription>Add rent periods with their rates</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b">
                                        <th className="text-left py-2 px-2 font-medium">Lease Year</th>
                                        <th className="text-left py-2 px-2 font-medium">Per Sq. Ft.</th>
                                        <th className="text-left py-2 px-2 font-medium">Per Annum</th>
                                        <th className="text-left py-2 px-2 font-medium">Per Month</th>
                                        <th className="w-10"></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rentSchedule.map((row, index) => (
                                        <tr key={index} className="border-b">
                                            <td className="py-2 px-2">
                                                <div className="flex items-center gap-1">
                                                    <Input
                                                        type="number"
                                                        value={row.lease_year_start}
                                                        onChange={(e) => updateRentRow(index, "lease_year_start", parseInt(e.target.value) || 0)}
                                                        className="h-8 w-16"
                                                    />
                                                    <span>-</span>
                                                    <Input
                                                        type="number"
                                                        value={row.lease_year_end}
                                                        onChange={(e) => updateRentRow(index, "lease_year_end", parseInt(e.target.value) || 0)}
                                                        className="h-8 w-16"
                                                    />
                                                </div>
                                            </td>
                                            <td className="py-2 px-2">
                                                <Input
                                                    type="number"
                                                    step="0.01"
                                                    value={row.per_sqft || ""}
                                                    onChange={(e) => updateRentRow(index, "per_sqft", parseFloat(e.target.value) || 0)}
                                                    className="h-8 w-24"
                                                    placeholder="$0.00"
                                                />
                                            </td>
                                            <td className="py-2 px-2">
                                                <Input
                                                    type="number"
                                                    step="0.01"
                                                    value={row.per_annum || ""}
                                                    onChange={(e) => updateRentRow(index, "per_annum", parseFloat(e.target.value) || 0)}
                                                    className="h-8 w-28"
                                                    placeholder="$0.00"
                                                />
                                            </td>
                                            <td className="py-2 px-2">
                                                <Input
                                                    type="number"
                                                    step="0.01"
                                                    value={row.per_month || ""}
                                                    onChange={(e) => updateRentRow(index, "per_month", parseFloat(e.target.value) || 0)}
                                                    className="h-8 w-28"
                                                    placeholder="$0.00"
                                                />
                                            </td>
                                            <td className="py-2 px-2">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => removeRentRow(index)}
                                                    disabled={rentSchedule.length === 1}
                                                    className="h-8 w-8 p-0"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </Button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={addRentRow}
                            className="mt-3"
                        >
                            <Plus className="w-4 h-4 mr-1" />
                            Add Rent Period
                        </Button>
                    </CardContent>
                </Card>

                {/* Error/Success Messages */}
                {error && (
                    <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-md text-destructive text-sm">
                        {error}
                    </div>
                )}
                {success && (
                    <div className="mb-4 p-3 bg-green-500/10 border border-green-500/20 rounded-md text-green-600 text-sm">
                        ✓ Document generated successfully! Check your downloads.
                    </div>
                )}

                {/* Generate Button */}
                <div className="flex justify-end">
                    <Button
                        onClick={handleGenerate}
                        disabled={isGenerating}
                        className="gap-2"
                        size="lg"
                    >
                        {isGenerating ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Generating...
                            </>
                        ) : (
                            <>
                                <Download className="w-4 h-4" />
                                Generate Document
                            </>
                        )}
                    </Button>
                </div>
            </div>
        </ScrollArea>
    );
}
