# LawHand platform guides

This directory is the source of truth for the authenticated, in-product guides.

- `user-guide/` documents day-to-day workflows for every authenticated user. It opens at `/guide/<slug>`.
- `administrative-guide/` documents firm configuration, access, integrations, billing, and governance. It opens inside Administration at `/admin?tab=guide&chapter=<slug>`.

Each chapter is Markdown with a small front matter block. `slug`, `title`, `description`, `order`, `read_time`, and `icon` are required. `order` must equal the file's number followed by a zero (`04-…` is `40`), and `icon` must be one of the icons `GuideViewer.jsx` knows. The frontend discovers chapters automatically, so adding a valid file places it in the navigation.

Run `node ../scripts/check_platform_docs.mjs` from `frontend/` before committing guide changes (CI runs the same check).

## How a chapter should read

Write for the person at the screen, in the product's own words:

- Start with what the screen is for, then numbered steps that name the exact buttons and fields, in bold.
- Put a screenshot near the top of the main task, with numbered markers the text explains.
- Add a **Troubleshooting** table (`What you notice | Likely cause | What to do`) and **Related chapters** at the end.
- Verify every label, status, and message against the component before writing it. Do not describe planned features.
- Never include credentials, customer data, infrastructure addresses, security procedures, incident runbooks, or links to the private repository.

## Callouts

Start a blockquote with one of GitHub's alert markers to render a callout:

```md
> [!TIP]
> Select **Log Time** on a matter to open Time Tracking with it chosen.
```

Supported markers are `NOTE`, `TIP`, `IMPORTANT`, `WARNING`, and `CAUTION`. Use them sparingly, for the one thing a reader must not miss.

## Section anchors

Every heading gets an anchor: lowercase, with links and formatting removed and each run of other characters replaced by `-` (`## Record time` becomes `#record-time`). Headings must be unique within a chapter and must not contain links. Other chapters, `coverage.json`, and the product link to these anchors, so rename a heading only after updating everything that points at it; the check reports broken ones.

## Linking into LawHand

Use root-relative links to take a reader to a screen or another chapter:

```md
[Open your matters](/matters)
[Record time](/guide/time-billing-and-reports#record-time)
[Manage users](/admin?tab=users)
[Connect Zoom](/admin?tab=integrations&integration=zoom)
[Integrations chapter](/admin?tab=guide&chapter=integrations#choose-where-matter-documents-live)
```

The renderer turns these into in-app links. Link to addresses a reader can open (the entry route, not `/matters/:id`). User-guide chapters must not link to administrative routes, and administrator chapters must be linked through `/admin?tab=guide&chapter=<slug>`, never `/guide/<slug>`. The check enforces all of this.

## From the product back to the guide

`coverage.json` maps every authenticated route (`user_modules`), Administration tab (`admin_tabs`), Integrations section (`admin_integration_sections`), and other administrator screen (`admin_routes`) to the chapter, and optionally the `anchor`, that documents it, with the `label` shown in the product. It drives three things:

- the **Guide** button in the top bar (`AppShell`), which opens the section for the current screen; a page can narrow it to the panel in view with `usePageGuideTopic(audience, chapter, anchor, label)`, as the matter sections do;
- the **Open in LawHand** buttons at the start of each chapter; and
- the Integrations hub's per-section guide links.

For a link inside a panel, use `GuideLink` from `src/components/GuideLink.jsx`:

```jsx
<GuideLink chapter="time-billing-and-reports" anchor="record-matter-expenses">
  How expenses and receipts work
</GuideLink>
```

Administrator chapters open inside Administration, so only show those links when `canOpenAdminGuide(user)` is true.

The check compares `coverage.json` with `App.jsx`, `adminTabs.js`, and the Integrations sections. It fails when a product surface is added or removed without updating the guide, when a label or anchor does not match, or when a chapter does not link to the screen it documents.

## Screenshots

Guide screenshots live in `frontend/public/guide-assets/` and are referenced with an absolute path. The title in quotes becomes the caption:

```md
![The Invoices page with the Generate invoice button and the Ready to bill list](/guide-assets/invoices-list.webp "Invoices, ready-to-bill work, and payment status")
```

Write alternative text that says what the image shows. Prefer WebP for screenshots; every image must be served from `/guide-assets/` and be no larger than 600 KB.

### Capturing screenshots

Screenshots are captured from the real UI with synthetic data, so they can be regenerated after any UI change:

```bash
cd frontend
node scripts/capture-guide-screenshots.mjs                                   # every shot
node scripts/capture-guide-screenshots.mjs --only tasks-list,invoices-list
node scripts/capture-guide-screenshots.mjs --only time-tracking --discover   # list the API calls, write nothing
```

The script starts the Vite dev server, opens each page in Chromium with a frozen clock and a fixed time zone, answers every `/api` request from `scripts/guide-screenshots/fixtures.mjs` (a fictional firm, Maple & Birch Law, with `.example` addresses), and writes 2× WebP images.

Each shot in `scripts/guide-screenshots/shots.mjs` names its `path`, signed-in `user`, `viewport`, a `waitFor` text, an optional `setup` step, a `clip` (usually `regionAround` a few locators), and `annotate` markers: numbered rings the chapter text explains. Use `placement: 'bottom-left'` when a marker would cover text.

When a screen looks empty, run it with `--discover`: requests answered by the generic fallback are listed at the end, and each needs a fixture. Never capture real customer data.
