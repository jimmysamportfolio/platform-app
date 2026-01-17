import { NextRequest, NextResponse } from 'next/server';

// Server-side API call - use Docker service name in production, localhost in dev
const API_BASE_URL = process.env.BACKEND_URL || "http://backend:8000";

/**
 * Proxy route for document files to avoid CORS issues.
 * Fetches the document from the backend and returns it to the client.
 */
export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ name: string }> }
) {
    const { name } = await params;

    try {
        const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(name)}/file`);

        if (!response.ok) {
            return NextResponse.json(
                { error: `Failed to fetch document: ${response.status}` },
                { status: response.status }
            );
        }

        const blob = await response.blob();
        const arrayBuffer = await blob.arrayBuffer();

        // Return the file with appropriate headers
        return new NextResponse(arrayBuffer, {
            headers: {
                'Content-Type': blob.type || 'application/pdf',
                'Content-Disposition': `inline; filename="${name}"`,
            },
        });
    } catch (error) {
        console.error('Document proxy error:', error);
        return NextResponse.json(
            { error: 'Failed to fetch document' },
            { status: 500 }
        );
    }
}
