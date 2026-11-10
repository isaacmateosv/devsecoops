import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevSecOops — Financial Legacy Intelligence",
  description: "Source-blind business-rule recovery, a reproduced Oops, and a verified rebuild — with real evidence.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-mono antialiased">{children}</body>
    </html>
  );
}
