# AlphaDesk Frontend Style Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate DESIGN branding from Claude/Anthropic to AlphaDesk and implement A+A1 landing-page flow so signed-in users reach Dashboard faster.

**Architecture:** Keep existing Next.js page composition and visual language, but update copy taxonomy, CTA logic, and section sequencing. Implement auth-aware CTA components in the landing page and align zh/en i18n keys with a direct-entry homepage narrative.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript, next-intl, Clerk, Tailwind CSS v4

---

## File Structure and Responsibilities

- `DESIGN.md`
  - Single source of design-token semantics and style rules; remove legacy Claude/Anthropic branding and remap examples to AlphaDesk investment context.
- `apps/web/messages/zh.json`
  - Chinese landing-page copy and CTA keys for A1 direct-entry behavior.
- `apps/web/messages/en.json`
  - English equivalents of new/updated landing-page keys.
- `apps/web/src/app/[locale]/page.tsx`
  - Landing page composition, signed-in/out CTA branching, section order, and reduced animation density.
- `apps/web/src/app/globals.css` (optional)
  - Only adjust token aliases if renamed semantics are needed by UI implementation.

---

### Task 1: DESIGN.md Brand and Semantics Migration

**Files:**
- Modify: `DESIGN.md`
- Test: `DESIGN.md` term-scan checks

- [ ] **Step 1: Run failing legacy-term scan**

Run:
```bash
rg -n "Claude|Anthropic|Opus|Sonnet|Haiku" DESIGN.md
```
Expected: FAIL condition (matches found), proving migration is still pending.

- [ ] **Step 2: Replace legacy brand terms and examples with AlphaDesk equivalents**

Apply edits to `DESIGN.md` following this mapping:
```md
# Design System Inspired by AlphaDesk

- Anthropic Near Black -> AlphaDesk Ink
- Anthropic Serif/Sans/Mono -> AlphaDesk Serif/Sans/Mono
- Claude wordmark -> AlphaDesk wordmark
- Claude chat interface screenshot -> AlphaDesk dashboard/recommendation interface screenshot
- Opus/Sonnet/Haiku cards -> Recommendation Evidence Cards
```

- [ ] **Step 3: Reframe narrative from generic AI companion to investment decision copilot**

Update descriptive paragraphs to preserve warm editorial aesthetic while changing product context:
```md
AlphaDesk's interface is a calm investment workspace...
...emphasizing explainable recommendations, reviewable rationale, and human final decision ownership.
```

- [ ] **Step 4: Run migration verification**

Run:
```bash
rg -n "Claude|Anthropic|Opus|Sonnet|Haiku" DESIGN.md
```
Expected: no output (pass).

- [ ] **Step 5: Commit**

```bash
git add DESIGN.md
git commit -m "docs: migrate design system branding to AlphaDesk"
```

---

### Task 2: i18n Copy Update for A1 Direct-Entry CTA Flow

**Files:**
- Modify: `apps/web/messages/zh.json`
- Modify: `apps/web/messages/en.json`
- Test: JSON parse validation + key presence grep

- [ ] **Step 1: Confirm new A1 keys are missing (failing check)**

Run:
```bash
rg -n "ctaDashboard|ctaSignInDashboard|ctaLearnMethod|heroSummary" apps/web/messages/zh.json apps/web/messages/en.json
```
Expected: no matches (failing precondition before adding keys).

- [ ] **Step 2: Add/update Chinese keys for signed-in/out CTA split**

Insert or update under `hero` and related sections:
```json
{
  "hero": {
    "ctaSignInDashboard": "登录并查看今日推荐",
    "ctaDashboard": "进入 Dashboard",
    "ctaLearnMethod": "了解推荐方法",
    "ctaViewToday": "查看今日推荐",
    "heroSummary": {
      "recommendations": "今日推荐",
      "pending": "待审阅",
      "risk": "风险状态"
    }
  }
}
```

- [ ] **Step 3: Add/update matching English keys**

```json
{
  "hero": {
    "ctaSignInDashboard": "Sign in to see today's picks",
    "ctaDashboard": "Go to Dashboard",
    "ctaLearnMethod": "How recommendations work",
    "ctaViewToday": "View today's picks",
    "heroSummary": {
      "recommendations": "Today's Picks",
      "pending": "Pending Review",
      "risk": "Risk Status"
    }
  }
}
```

- [ ] **Step 4: Validate JSON and key existence**

Run:
```bash
node -e "const fs=require('fs'); JSON.parse(fs.readFileSync('apps/web/messages/zh.json','utf8')); JSON.parse(fs.readFileSync('apps/web/messages/en.json','utf8')); console.log('ok')"
rg -n "ctaDashboard|ctaSignInDashboard|ctaLearnMethod|heroSummary" apps/web/messages/zh.json apps/web/messages/en.json
```
Expected: `ok` printed and grep shows all added keys.

- [ ] **Step 5: Commit**

```bash
git add apps/web/messages/zh.json apps/web/messages/en.json
git commit -m "feat(web): add A1 direct-entry landing copy keys"
```

---

### Task 3: Navigation and Hero CTA Refactor (Auth-Aware Direct Entry)

**Files:**
- Modify: `apps/web/src/app/[locale]/page.tsx`
- Test: lint/build checks

- [ ] **Step 1: Add missing navigation/link imports and split CTA rendering logic**

Update imports and CTA dependencies:
```tsx
import { Link } from "@/navigation";
import { Show, UserButton, SignInButton } from "@clerk/nextjs";
```

Introduce helper CTA block in Hero:
```tsx
function HeroPrimaryActions() {
  const t = useTranslations("hero");
  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      <Show
        when="signed-in"
        fallback={
          <SignInButton>
            <button className="...">{t("ctaSignInDashboard")}</button>
          </SignInButton>
        }
      >
        <Link href="/dashboard" className="...">
          {t("ctaDashboard")}
        </Link>
      </Show>
      <a href="#product" className="...">{t("ctaLearnMethod")}</a>
    </div>
  );
}
```

- [ ] **Step 2: Update top nav signed-in experience with explicit dashboard shortcut**

In `Navigation()` actions:
```tsx
<Show when="signed-in" fallback={...sign-in button...}>
  <Link href="/dashboard" className="bg-green ...">
    {t("nav.dashboard")}
  </Link>
  <UserButton />
</Show>
```

- [ ] **Step 3: Replace old hero single button with A1 CTA group + summary card**

Insert compact summary card in first viewport:
```tsx
<div className="mt-8 grid grid-cols-3 gap-3 max-w-2xl mx-auto">
  <div className="bg-white/80 border border-divider rounded-xl p-3 text-left">
    <p className="text-xs text-warm-gray">{t("heroSummary.recommendations")}</p>
    <p className="text-lg font-semibold text-charcoal">5</p>
  </div>
  ...
</div>
```

- [ ] **Step 4: Verify compile and lint**

Run:
```bash
cd apps/web && pnpm lint
cd apps/web && pnpm build
```
Expected: both commands pass with no TypeScript/i18n key errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/[locale]/page.tsx
git commit -m "feat(web): implement auth-aware A1 hero and nav CTA flow"
```

---

### Task 4: Section Order and Motion Compression for Faster Action Path

**Files:**
- Modify: `apps/web/src/app/[locale]/page.tsx`
- Test: local dev visual QA + reduced-motion safety

- [ ] **Step 1: Reorder sections to A1 flow in page export**

Ensure page order prioritizes direct action and proof:
```tsx
export default function Home() {
  return (
    <main className="overflow-x-clip">
      <Navigation />
      <HeroSection />
      <ProductSection />
      <FeaturesSection />
      <WorkflowSection />
      <PhilosophySection />
      <CTASection />
    </main>
  );
}
```

- [ ] **Step 2: Reduce high-friction scroll storytelling intensity**

Adjust long sticky sections:
```tsx
// ProblemSection -> either remove from main flow or reduce from h-[300vh] to h-[180vh]
// WorkflowSection -> reduce from h-[400vh] to h-[260vh]
```

- [ ] **Step 3: Keep animations but remove unnecessary heavy effects**

Examples:
```tsx
transition={{ duration: 0.35 }}
// remove or reduce repeated glow/pulse where it distracts from CTA
```

- [ ] **Step 4: Verify behavior in dev**

Run:
```bash
cd apps/web && pnpm dev
```
Manual checks:
- Signed-in: primary action visible in first screen and links to `/dashboard`.
- Signed-out: primary action opens sign-in flow.
- Mobile viewport (375px width): CTA visible without deep scroll.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/[locale]/page.tsx
git commit -m "refactor(web): compress landing narrative and prioritize dashboard path"
```

---

### Task 5: Final Verification and Documentation Sync

**Files:**
- Modify (if needed): `apps/web/src/app/globals.css`
- Verify: `DESIGN.md`, `apps/web/messages/*.json`, `apps/web/src/app/[locale]/page.tsx`

- [ ] **Step 1: Run final regression checks**

```bash
rg -n "Claude|Anthropic|Opus|Sonnet|Haiku" DESIGN.md
cd apps/web && pnpm lint && pnpm build
```
Expected:
- no legacy terms in `DESIGN.md`
- lint/build pass

- [ ] **Step 2: Optional token alias cleanup if UI references migrated names**

If needed, align comments/aliases in `globals.css`:
```css
/* AlphaDesk Ink semantic alias */
--color-ink: #141413;
```

- [ ] **Step 3: Final QA checklist execution**

Checklist:
- zh/en copy both render without missing translation fallbacks.
- Hero shows summary card + direct-entry CTA pair.
- Nav signed-in state includes Dashboard shortcut.
- Overall palette remains warm and editorial (no dark-terminal drift).

- [ ] **Step 4: Commit**

```bash
git add DESIGN.md apps/web/src/app/[locale]/page.tsx apps/web/messages/zh.json apps/web/messages/en.json apps/web/src/app/globals.css
git commit -m "feat(web): ship AlphaDesk A1 landing style and brand migration"
```

---

## Self-Review

### 1) Spec Coverage
- Brand migration in `DESIGN.md`: covered by Task 1 + Task 5 verification.
- A1 direct-entry CTA logic: covered by Task 2 + Task 3.
- Landing IA and pacing optimization: covered by Task 4.
- Verification across desktop/mobile + signed-in/out: covered by Task 4 and Task 5.

### 2) Placeholder Scan
- No `TODO`, `TBD`, or unresolved implementation placeholders included in steps.
- Commands and expected outcomes are explicit per task.

### 3) Type/Name Consistency
- New key set consistently referenced as:
  - `hero.ctaSignInDashboard`
  - `hero.ctaDashboard`
  - `hero.ctaLearnMethod`
  - `hero.ctaViewToday`
  - `hero.heroSummary.*`
- Route target consistently `/dashboard`.
