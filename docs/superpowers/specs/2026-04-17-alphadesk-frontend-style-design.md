# AlphaDesk Frontend Style Optimization Design (A + A1)

## 1. Context

Current project has:
- A design reference document (`DESIGN.md`) that still contains extensive Claude/Anthropic branding terms.
- A landing page implementation in `apps/web/src/app/[locale]/page.tsx` with rich narrative/animation and mixed CTA paths.
- A product priority of improving **usage efficiency for signed-in users**, specifically faster entry into Dashboard.

This design defines the style migration and landing-page restructuring before implementation.

## 2. Goals

1. Replace all legacy Claude-related brand references in `DESIGN.md` with AlphaDesk brand language.
2. Preserve the warm editorial visual system (parchment, warm neutrals, soft radius, ring-shadow depth).
3. Shift homepage information architecture to **A1 direct-entry flow**:
   - Signed-in users should quickly reach Dashboard.
   - Primary above-the-fold action should be Dashboard-oriented.
4. Align homepage narrative with AlphaDesk’s investment-decision product context.

## 3. Non-Goals

1. No deep redesign of dashboard product pages in this phase.
2. No backend API or data-model changes.
3. No redesign into dark trading-terminal style.

## 4. Chosen Direction

## 4.1 Visual Direction: A (Classic Warm Parchment)

Maintain existing warm, human-centered design language:
- Parchment background and warm neutrals as base identity.
- Muted terracotta accent used only for high-signal moments.
- Soft ring shadows instead of heavy drop shadows.
- Editorial rhythm and generous whitespace.

## 4.2 Information Architecture: A1 (Direct Entry)

Homepage order:
1. Hero with immediate action to Dashboard/recommendations.
2. “Why today’s recommendations” explanation block.
3. Compact dashboard preview section.
4. Condensed workflow timeline.
5. Trust/reviewability principles section.

## 5. Content and Brand Migration Rules

## 5.1 Mandatory Global Replacements in `DESIGN.md`

- Replace `Claude` references with `AlphaDesk` where brand subject is intended.
- Replace `Anthropic` token naming with `AlphaDesk` naming:
  - `Anthropic Near Black` -> `AlphaDesk Ink`
  - `Anthropic Serif/Sans/Mono` -> `AlphaDesk Serif/Sans/Mono` (semantic naming in design tokens)
- Replace model examples:
  - `Opus/Sonnet/Haiku` cards -> `Recommendation Evidence Cards` (Quant score / Catalyst score / Risk status)
- Replace logo/image mentions:
  - `Claude wordmark` -> `AlphaDesk wordmark`
  - `Claude chat interface screenshot` -> `AlphaDesk dashboard/recommendation interface screenshot`

## 5.2 Narrative Shift

Shift text from “general AI assistant vibe” to “investment decision copilot”:
- Emphasize recommendation transparency, reviewability, and decision ownership.
- Emphasize “approve/reject recommendations” rather than generic conversational AI interactions.

## 6. Landing Page UX Specification

## 6.1 Hero Section

Signed-out state:
- Primary CTA: `登录并查看今日推荐` / `Sign in to see today’s picks`
- Secondary CTA: `了解推荐方法` / `How recommendations work`

Signed-in state:
- Primary CTA: `进入 Dashboard` / `Go to Dashboard`
- Secondary CTA: `查看今日推荐` / `View today’s picks`

Hero visual support:
- Add a compact summary card (recommendation count, pending review count, risk status) within first viewport.

## 6.2 Navigation Behavior

- Keep minimal top nav: brand, language switcher, auth entry.
- Signed-in users get explicit dashboard shortcut in nav actions.
- Sticky nav remains; scrolling state uses lighter visual shift to avoid abrupt transition.

## 6.3 Section Compression

- Keep existing storytelling modules but reduce copy density and animation frequency.
- Ensure first two screens already contain the primary action path.
- Mobile retains immediate CTA visibility without requiring long scroll.

## 7. Design Token/Style Constraints

1. Preserve warm neutral palette and ring-shadow philosophy.
2. Keep rounded corners and soft elevation language.
3. Avoid introducing cool gray or high-saturation tech colors as dominant tones.
4. Preserve readability-focused typography hierarchy and line-height rhythm.

## 8. Implementation Surface (for next phase)

Expected file targets:
- `DESIGN.md` (brand and design semantics migration)
- `apps/web/src/app/[locale]/page.tsx` (A1 structure and CTA flow)
- `apps/web/messages/zh.json`
- `apps/web/messages/en.json`
- `apps/web/src/app/globals.css` (only if token naming or minor style adaptation is required)

## 9. Data Flow and State Behavior

1. Landing page renders with i18n translation keys via `next-intl`.
2. Auth-aware CTA rendering follows Clerk signed-in/signed-out state.
3. CTA destinations:
   - Signed-in primary: dashboard route.
   - Signed-out primary: sign-in flow.
4. Recommendation summary shown on homepage uses static/mock presentation unless existing data path is already available for safe use.

## 10. Error Handling and Resilience

1. If auth state cannot be determined immediately, render safe neutral CTA fallback (`Sign in`).
2. If summary data source is unavailable, render graceful placeholder values without blocking CTA interaction.
3. Avoid layout shift from async text or auth transitions by reserving CTA container size.

## 11. Testing and Verification Plan

1. Content validation:
   - Search `DESIGN.md` to ensure no legacy terms remain (`Claude`, `Anthropic`, `Opus`, `Sonnet`, `Haiku`) unless explicitly contextualized as historical note (not expected in final).
2. Functional validation:
   - Signed-in homepage shows Dashboard-priority CTA.
   - Signed-out homepage shows sign-in-priority CTA.
3. Visual validation:
   - Desktop + mobile checks for hero CTA visibility and section order.
   - Confirm warm palette and ring-shadow style remain consistent.
4. i18n validation:
   - No missing translation keys in `zh`/`en`.

## 12. Scope Check

This spec is intentionally constrained to one implementation cycle:
- Document migration + homepage style/IA alignment.
- No additional product-surface expansion.

The scope is sufficiently bounded for immediate planning and implementation.
