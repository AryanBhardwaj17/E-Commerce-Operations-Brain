import type { ReactNode } from "react";

type AppShellProps = {
  eyebrow: string;
  title: string;
  description: string;
  accent: "ops" | "portal";
  children: ReactNode;
};

export function AppShell({ eyebrow, title, description, accent, children }: AppShellProps) {
  return (
    <main style={styles.page}>
      <div style={{ ...styles.hero, borderColor: accent === "ops" ? "var(--accent)" : "var(--accent-alt)" }}>
        <p style={styles.eyebrow}>{eyebrow}</p>
        <h1 style={styles.title}>{title}</h1>
        <p style={styles.description}>{description}</p>
      </div>
      <div style={styles.content}>{children}</div>
    </main>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    padding: "32px 20px 56px",
  },
  hero: {
    maxWidth: "1120px",
    margin: "0 auto 24px",
    padding: "24px",
    border: "1px solid var(--border)",
    borderRadius: "28px",
    background: "var(--panel-strong)",
    boxShadow: "var(--shadow)",
  },
  eyebrow: {
    margin: 0,
    fontFamily: "var(--font-mono), monospace",
    fontSize: "0.85rem",
    letterSpacing: "0.16em",
    textTransform: "uppercase" as const,
    color: "var(--muted)",
  },
  title: {
    margin: "0.7rem 0 0",
    fontSize: "clamp(2.5rem, 6vw, 5rem)",
    lineHeight: 0.95,
  },
  description: {
    maxWidth: "60ch",
    margin: "1rem 0 0",
    fontSize: "1.05rem",
    color: "var(--muted)",
    lineHeight: 1.7,
  },
  content: {
    maxWidth: "1120px",
    margin: "0 auto",
  },
};