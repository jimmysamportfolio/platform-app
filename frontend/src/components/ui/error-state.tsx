import { cn } from "@/lib/utils";

interface ErrorStateProps {
    message: string;
    className?: string;
}

/**
 * Consistent error state component used across pages.
 */
export function ErrorState({
    message,
    className
}: ErrorStateProps) {
    return (
        <div className={cn("flex items-center justify-center h-full", className)}>
            <div className="text-sm text-muted-foreground">{message}</div>
        </div>
    );
}
