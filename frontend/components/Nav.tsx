import Link from "next/link";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/service", label: "Service" },
  { href: "/coldchain", label: "Cold Chain" },
  { href: "/money", label: "Money" },
  { href: "/price-position", label: "Price Position" },
  { href: "/ask", label: "Ask" },
] as const;

export function Nav() {
  return (
    <nav className="flex items-center gap-4 border-b border-gray-200 bg-white px-4 py-3">
      <span className="font-semibold">Kestrel Control Tower</span>
      <div className="flex gap-3 text-sm text-gray-600">
        {LINKS.map((link) => (
          <Link key={link.href} href={link.href} className="hover:text-black hover:underline">
            {link.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
