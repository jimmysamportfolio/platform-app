/**
 * API Client Utilities
 * 
 * Handles all communication with the FastAPI backend.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Generic fetch wrapper with error handling.
 */
async function apiFetch<T>(
    endpoint: string,
    options: RequestInit = {}
): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;

    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json",
            ...options.headers,
        },
        ...options,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(error.detail || `API Error: ${response.status}`);
    }

    return response.json();
}

// --- Chat API ---

export interface ChatResponse {
    answer: string;
    route: string;
    sources: string[];
}

export async function sendChatMessage(message: string): Promise<ChatResponse> {
    return apiFetch<ChatResponse>("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message }),
    });
}

// --- Analytics API ---

export interface PortfolioSummary {
    total_leases: number;
    total_sqft: number;
    total_deposits: number;
    average_rent_psf: number;
    average_term_years: number;
    leases_expiring_soon: Array<{
        tenant_name: string;
        trade_name: string | null;
        expiration_date: string;
        days_until_expiration: number;
    }>;
    rent_by_property: Array<{
        property_address: string;
        lease_count: number;
        total_sqft: number;
        avg_rent_psf: number;
    }>;
    lease_breakdown: Array<{
        id: number;
        document_name: string;
        tenant: string;
        trade_name: string | null;
        property: string;
        sqft: number | null;
        start_date: string | null;
        end_date: string | null;
        term_years: number | null;
        deposit: number | null;
        base_rent: number | null;
        rate_psf: number | null;
    }>;
}

export async function getPortfolioSummary(): Promise<PortfolioSummary> {
    return apiFetch<PortfolioSummary>("/api/analytics/portfolio");
}

// --- Documents API ---

export interface LeaseDocument {
    id: number;
    document_name: string;
    tenant_name: string;
    trade_name: string | null;
    property_address: string;
    expiration_date: string;
    term_years: number;
    rentable_area_sqft: number;
    deposit_amount: number;
}

export interface DocumentsResponse {
    documents: LeaseDocument[];
}

export async function getDocuments(): Promise<DocumentsResponse> {
    return apiFetch<DocumentsResponse>("/api/documents");
}

export interface DocumentContent {
    filename: string;
    content: string;
}

export async function getDocumentContent(documentName: string): Promise<DocumentContent> {
    const encodedName = encodeURIComponent(documentName);
    return apiFetch<DocumentContent>(`/api/documents/${encodedName}/content`);
}

export interface DeleteResponse {
    status: string;
    message: string;
}

export async function deleteDocument(documentName: string): Promise<DeleteResponse> {
    const encodedName = encodeURIComponent(documentName);
    return apiFetch<DeleteResponse>(`/api/documents/${encodedName}`, {
        method: "DELETE",
    });
}
