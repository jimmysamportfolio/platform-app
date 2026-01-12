import { cn } from "@/lib/utils";

interface LoadingStateProps {
    message?: string;
    className?: string;
}

/**
 * Consistent loading state component used across pages.
 */
export function LoadingState({
    message = "Loading...",
    className
}: LoadingStateProps) {
    return (
        <div className={cn("flex items-center justify-center h-full", className)}>
            <div className="text-muted-foreground text-sm">{message}</div>
        </div>
    );
}
