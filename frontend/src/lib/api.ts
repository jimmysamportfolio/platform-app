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
    confidence: number;  // 0-100 confidence percentage
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

/**
 * Get the URL to view/download the original document file (PDF/DOCX).
 */
export function getDocumentFileUrl(documentName: string): string {
    const encodedName = encodeURIComponent(documentName);
    return `${API_BASE_URL}/api/documents/${encodedName}/file`;
}

// --- Clause Comparison API ---

export interface LeaseOption {
    id: number;
    tenant_name: string;
    trade_name: string | null;
}

export interface PropertyGroup {
    property_address: string;
    leases: LeaseOption[];
}

export interface LeasesListResponse {
    properties: PropertyGroup[];
}

export async function getLeasesGrouped(): Promise<LeasesListResponse> {
    return apiFetch<LeasesListResponse>("/api/leases/list");
}

export interface ClauseData {
    lease_id: number;
    tenant_name: string;
    trade_name: string | null;
    property_address: string;
    summary: string;
    key_terms: string;
    article_reference: string | null;
}

export interface ClauseComparisonResponse {
    comparisons: Record<string, ClauseData[]>;
    lease_count: number;
}

export async function compareClauses(leaseIds: number[]): Promise<ClauseComparisonResponse> {
    return apiFetch<ClauseComparisonResponse>("/api/clauses/compare", {
        method: "POST",
        body: JSON.stringify({ lease_ids: leaseIds }),
    });
}

// --- Document Generation API ---

export interface RentRowInput {
    lease_year_start: number;
    lease_year_end: number;
    per_sqft: number;
    per_annum: number;
    per_month: number;
}

export interface GenerateDocumentInput {
    tenant_name: string;
    tenant_address: string;
    indemnifier_name: string;
    indemnifier_address: string;
    premises_unit: string;
    rentable_area: string;
    lease_date: string;
    initial_term: string;
    renewal_option_count: number;
    renewal_option_years: number;
    possession_date: string;
    fixturing_period: string;
    offer_to_lease_date: string;
    indemnity_date: string;
    rent_schedule: RentRowInput[];
    deposit: string;
    tenant_improvement_allowance: string;
    permitted_use: string;
    trade_name: string;
    exclusive_use: string;
    radius_restriction: string;
}

export async function generateDocument(input: GenerateDocumentInput): Promise<Blob> {
    const url = `${API_BASE_URL}/api/documents/generate`;

    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(input),
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(error.detail || `API Error: ${response.status}`);
    }

    return response.blob();
}

// --- Key Terms API ---

export interface KeyTermsLease {
    id: number;
    tenant_name: string;
    trade_name: string | null;
    tenant_address: string | null;
    indemnifier_name: string | null;
    indemnifier_address: string | null;
    lease_date: string | null;
    premises: string | null;
    rentable_area_sqft: number | null;
    term_years: number | null;
    renewal_option: string | null;
    deposit_amount: number | null;
    permitted_use: string | null;
    fixturing_period: string | null;
    free_rent_period: string | null;
    possession_date: string | null;
    tenant_improvement_allowance: string | null;
    exclusive_use: string | null;
}

export interface KeyTermsResponse {
    leases: KeyTermsLease[];
    count: number;
}

export async function getKeyTerms(leaseIds: number[]): Promise<KeyTermsResponse> {
    const idsParam = leaseIds.join(",");
    return apiFetch<KeyTermsResponse>(`/api/extraction/key-terms?lease_ids=${idsParam}`);
}

// --- Ingestion API ---

export const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export interface PendingFile {
    file_path: string;
    file_name: string;
    detected_at: string;
}

export interface PendingFilesResponse {
    pending_files: PendingFile[];
    count: number;
}

export async function getPendingFiles(): Promise<PendingFilesResponse> {
    return apiFetch<PendingFilesResponse>("/api/ingestion/pending");
}

export interface ProcessIngestionResult {
    success: boolean;
    file_name: string;
    mode?: string;
    chunks_processed?: number;
    vectors_uploaded?: number;
    processing_time?: number;
    error?: string;
}

export async function processIngestion(
    filePath: string,
    mode: "full" | "clause_only"
): Promise<ProcessIngestionResult> {
    return apiFetch<ProcessIngestionResult>("/api/ingestion/process", {
        method: "POST",
        body: JSON.stringify({ file_path: filePath, mode }),
    });
}

