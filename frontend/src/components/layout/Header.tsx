"use client";

import { usePathname } from "next/navigation";

/**
 * Maps routes to page titles.
 */
const pageTitles: Record<string, string> = {
    "/analytics": "Dashboard",
    "/qa": "Q&A",
    "/documents": "Documents",
    "/": "Home",
};

export function Header() {
    const pathname = usePathname();

    // Determine title: strict match -> startsWith match -> Default
    let title = pageTitles[pathname];

    if (!title) {
        // Try finding a parent route match (e.g. /documents/123 -> Documents)
        const match = Object.keys(pageTitles).find(route =>
            route !== "/" && pathname.startsWith(route)
        );
        title = match ? pageTitles[match] : "";
    }

    return (
        <header className="h-14 border-b bg-background flex items-center px-6 sticky top-0 z-10">
            <h2 className="text-lg font-semibold">{title}</h2>

            {/* Right side actions can go here later (e.g. Quick Create button) */}
            <div className="ml-auto flex items-center gap-4">
                {/* Placeholder for future actions */}
            </div>
        </header>
    );
}
