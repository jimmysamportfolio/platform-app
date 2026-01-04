"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageCircle, BarChart3, FileText } from "lucide-react";

const navItems = [
    { name: "Q&A", href: "/qa", icon: MessageCircle },
    { name: "Dashboard", href: "/analytics", icon: BarChart3 },
];

export function Sidebar() {
    const pathname = usePathname();

    return (
        <aside className="w-56 h-screen flex flex-col bg-[var(--sidebar)] border-r border-[var(--sidebar-border)]">
            {/* Logo/Brand */}
            <div className="px-4 py-5 border-b border-[var(--sidebar-border)]">
                <h1 className="text-base font-semibold text-[var(--sidebar-foreground)]">
                    Platform Properties
                </h1>
            </div>

            {/* Navigation */}
            <nav className="flex-1 p-3">
                <ul className="space-y-1">
                    {navItems.map((item) => {
                        const isActive = pathname === item.href ||
                            (item.href !== "/" && pathname.startsWith(item.href));
                        const Icon = item.icon;

                        return (
                            <li key={item.name}>
                                <Link
                                    href={item.href}
                                    className={`
                    flex items-center gap-3 px-3 py-2 rounded-md text-sm
                    transition-colors duration-150
                    ${isActive
                                            ? "bg-[var(--sidebar-accent)] text-[var(--sidebar-foreground)] font-medium"
                                            : "text-[var(--sidebar-muted)] hover:text-[var(--sidebar-foreground)] hover:bg-[var(--sidebar-accent)]"
                                        }
                  `}
                                >
                                    <Icon className="w-4 h-4" />
                                    {item.name}
                                </Link>
                            </li>
                        );
                    })}
                </ul>
            </nav>
        </aside>
    );
}
