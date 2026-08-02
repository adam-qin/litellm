import type { Metadata } from "next";
import "./globals.css";

import AntdGlobalProvider from "@/contexts/AntdGlobalProvider";
import ChineseLocaleProvider from "@/contexts/ChineseLocaleProvider";
import { AuthProvider } from "@/contexts/AuthContext";
import ReactQueryProvider from "@/contexts/ReactQueryProvider";

export const metadata: Metadata = {
  title: "XHub 管理控制台",
  description: "XHub 模型网关管理界面",
  icons: { icon: "/get_favicon" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="font-sans">
        <ReactQueryProvider>
          <AntdGlobalProvider>
            <ChineseLocaleProvider>
              <AuthProvider>{children}</AuthProvider>
            </ChineseLocaleProvider>
          </AntdGlobalProvider>
        </ReactQueryProvider>
      </body>
    </html>
  );
}
