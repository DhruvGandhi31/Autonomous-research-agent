"use client";

import { ChatProvider } from "@/contexts/ChatContext";
import Sidebar from "@/components/layout/Sidebar";
import ChatArea from "@/components/chat/ChatArea";

export default function Home() {
  return (
    <ChatProvider>
      <div className="flex h-screen overflow-hidden bg-bg-primary">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-hidden">
          <ChatArea />
        </main>
      </div>
    </ChatProvider>
  );
}
