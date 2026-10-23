import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "OpenConvert — Files, ready for what’s next", description: "Convert supported image files with clear format capabilities." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
