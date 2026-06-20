import type { Metadata } from 'next';
import './globals.css';
import { ThemeProvider } from '@/components/ThemeProvider';

const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export const metadata: Metadata = {
  title: 'PUG Legal Case Control System',
  description: 'Paris United Group Holding — Legal Case Control System',
  icons: {
    icon: `${apiBase}/api/v1/settings/public/favicon`,
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
