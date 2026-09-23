import { AuthProvider } from "../../components/AuthProvider"
import { Navigation } from "../../components/Navigation"
import { OrgProvider } from "../../components/OrgProvider"
import { BrandingRoot } from "../../components/BrandingRoot"
import { CommandPalette } from "../../components/CommandPalette"
import { OnboardingTour } from "../../components/OnboardingTour"

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <OrgProvider>
        <BrandingRoot>
          <Navigation />
          {/* Phase 2 shell redesign: background now reads from the Phase 1
              design token (--bg-surface-secondary) instead of a literal
              Tailwind class -- same resolved color (gray-50 / gray-900),
              so this is a token-alignment refactor with no visible change.
              Padding/max-width are deliberately NOT added here: individual
              pages currently self-manage their own container spacing in
              inconsistent ways (some none, some fully self-padded) --
              normalizing that means editing each page and is out of scope
              for this shell-only pass; see the Phase 2 report for detail. */}
          <main className="ml-0 min-h-screen bg-[var(--bg-surface-secondary)] pt-14 lg:ml-64 lg:pt-0">
            {children}
          </main>
          <CommandPalette />
          <OnboardingTour />
        </BrandingRoot>
      </OrgProvider>
    </AuthProvider>
  )
}
