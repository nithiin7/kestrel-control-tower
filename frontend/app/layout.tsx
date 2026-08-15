import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { FilterBar } from "@/components/FilterBar";
import { Nav } from "@/components/Nav";
import { FilterProvider } from "@/lib/FilterContext";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Kestrel Control Tower",
  description: "Supply chain control tower over Kestrel's operational data",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <FilterProvider>
          <Nav />
          <FilterBar />
          <main className="flex-1 p-4">{children}</main>
        </FilterProvider>
      </body>
    </html>
  );
}
