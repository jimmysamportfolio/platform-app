"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { getPortfolioSummary } from "@/lib/api";
import { TrendingUp } from "lucide-react";

interface LeaseBreakdown {
    id: number;
    tenant: string;
    trade_name: string | null;
    property: string;
    sqft: number | null;
    term_years: number | null;
    deposit: number | null;
    end_date: string | null;
}

interface PortfolioData {
    total_leases: number;
    total_sqft: number;
    total_deposits: number;
    average_rent_psf: number;
    lease_breakdown: LeaseBreakdown[];
}

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

export default function AnalyticsPage() {
    const [data, setData] = useState<PortfolioData | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        async function fetchData() {
            try {
                const summary = await getPortfolioSummary();
                setData(summary as PortfolioData);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load data");
            } finally {
                setIsLoading(false);
            }
        }
        fetchData();
    }, []);

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
            <div className="p-6 bg-muted/30 min-h-full">
                {/* Metric Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                    <Card className="bg-card">
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

                    <Card className="bg-card">
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

                    <Card className="bg-card">
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

                    <Card className="bg-card">
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
                <Card className="bg-card">
                    <CardHeader>
                        <CardTitle className="text-base">Lease Breakdown</CardTitle>
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
                                {data.lease_breakdown?.map((lease) => (
                                    <TableRow key={lease.id}>
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
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            </div>
        </ScrollArea>
    );
}
