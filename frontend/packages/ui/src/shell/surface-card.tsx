import type { ReactNode } from "react";

type SurfaceCardProps = {
  title: string;
  tone: "warm" | "cool";
  children: ReactNode;
};

export function SurfaceCard({ title, tone, children }: SurfaceCardProps) {
  return (
    <article
      style={{
        padding: "22px",
        borderRadius: "24px",
        border: "1px solid var(--border)",
        background: tone === "warm"
          ? "linear-gradient(180deg, var(--panel-strong), rgba(255, 238, 226, 0.75))"
          : "linear-gradient(180deg, var(--panel-strong), rgba(226, 245, 241, 0.78))",
        boxShadow: "var(--shadow)",
      }}
    >
      <h2 style={{ marginTop: 0, marginBottom: "0.75rem", fontSize: "1.2rem" }}>{title}</h2>
      <div style={{ color: "var(--muted)", lineHeight: 1.7 }}>{children}</div>
    </article>
  );
}