import { AppShell } from "@eob/ui";

import { StoreOwnerWorkbench } from "./components/store-owner-workbench";

export default function StoreOwnerPage() {
  return (
    <AppShell
      eyebrow="Store Owner Assistant"
      title="Ask the store question. Get the business answer."
      description="Use one simple workspace to investigate issues across sales, marketing, inventory, and support. You ask the question, and the answer comes back in a clean summary with next steps when they matter."
      accent="ops"
    >
      <StoreOwnerWorkbench />
    </AppShell>
  );
}