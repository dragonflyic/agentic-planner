import type { Metadata } from "next";
import "./globals.css";
import { ClientProviders } from "@/components/ClientProviders";

export const metadata: Metadata = {
  title: "Signal-to-Attempt Workbench",
  description: "Manage GitHub issues and Claude Code automation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <ClientProviders>
        <div className="flex min-h-screen">
          {/* Sidebar */}
          <aside className="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
            <div className="p-4">
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                Workbench
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Signal-to-Attempt
              </p>
            </div>
            <nav className="mt-4">
              <a
                href="/"
                className="flex items-center px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                Dashboard
              </a>
              <a
                href="/signals"
                className="flex items-center px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                Signals
              </a>
              <a
                href="/working-set"
                className="flex items-center px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                Working Set
              </a>
              <a
                href="/attempts"
                className="flex items-center px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                Attempts
              </a>
              <a
                href="/clarifications"
                className="flex items-center px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                Needs Attention
              </a>
            </nav>
          </aside>

          {/* Main content */}
          <main className="flex-1 p-8">{children}</main>
        </div>
        </ClientProviders>
      </body>
    </html>
  );
}
