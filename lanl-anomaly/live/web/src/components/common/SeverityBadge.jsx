import { cn } from "../../lib/utils";

export default function SeverityBadge({ level, className }) {
  return (
    <span className={cn("stamp", `stamp-${level}`, className)}>
      {level}
    </span>
  );
}
