// Plain <a> tags rather than next/link's typed <Link>: most of these routes
// (service/coldchain/money/price-position/ask) don't exist yet — they land in
// later tasks — and Next's typed-routes feature rejects Link hrefs that don't
// resolve to a real page at build time.
const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/service", label: "Service" },
  { href: "/coldchain", label: "Cold Chain" },
  { href: "/money", label: "Money" },
  { href: "/price-position", label: "Price Position" },
  { href: "/ask", label: "Ask" },
];

export function Nav() {
  return (
    <nav className="flex items-center gap-4 border-b border-gray-200 bg-white px-4 py-3">
      <span className="font-semibold">Kestrel Control Tower</span>
      <div className="flex gap-3 text-sm text-gray-600">
        {LINKS.map((link) => (
          <a key={link.href} href={link.href} className="hover:text-black hover:underline">
            {link.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
