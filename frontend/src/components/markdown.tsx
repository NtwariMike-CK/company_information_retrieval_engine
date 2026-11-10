"use client";
import ReactMarkdown from "react-markdown";

/** Renders markdown from the database (terms, guidelines). react-markdown does not render raw HTML. */
export function Markdown({ children, className = "" }: { children: string; className?: string }) {
  return <div className={`chat-md text-slate-300 ${className}`}><ReactMarkdown>{children}</ReactMarkdown></div>;
}
