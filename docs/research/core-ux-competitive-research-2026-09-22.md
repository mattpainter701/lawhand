# Competitive UX research brief

Prepared 22 September 2026 for LawHand's core-workspace refinement epic.

See also the [feature-parity audit](./core-ux-feature-parity-2026-09-22.md) and the [market and review evidence](./core-ux-market-and-review-evidence-2026-09-22.md).

## What users appear to value

The recurring theme is easy access to related information, predictable places for everyday actions, reduced re-entry, and help when a user gets stuck. Customization is valuable when it accommodates the firm's work; extensive configuration can undermine that value. These are directional findings from selected public reviews and documented workflows, not a representative survey or hands-on testing of competitor accounts.

| Product | Documented pattern | Reported user value and friction | LawHand implication |
| --- | --- | --- | --- |
| Clio Manage / Grow | A matter is the case's home, with related documents, contacts, tasks, calendar and activities. Matter sections can be customized. Grow provides a separate intake pipeline. | April 2026 reviewers praise centralized information, quick task/note updates and search. Other reviewers describe difficulty moving between Grow and Manage, learning workflows, or arranging matter information. | Keep one matter context across actions and make the next step explicit. Extend LawHand's existing controls instead of introducing another workspace users must learn. |
| PracticePanther | Creating a task from a matter fills its matter/contact context. Tasks need a subject and assigned user; optional reminders and reusable task workflows are available. | Reviews praise predictable layout and fast staff learning. Other reviews raise support delays or difficulty with less common functions. | Use one recognizable task form everywhere, with context already filled in and advanced fields optional. Contextual help should be beside the action it explains. |
| Case Master Pro / CMPOnline | Main case file is the organizing screen; user-defined case types and per-user review lists support repeatable work. | Small review pool praises customization, intuitive operation and support. Its collections orientation makes generalization to other practices uncertain. | Borrow the personal work queue and flexible case presentation, not the collections-specific field density. |
| PracticeMaster (Tabs3) | Matter Manager brings case information together; personal/firm calendar views, Outlook integration and workflows connect daily work. | Review evidence values configurable workflows and integrated tools but also warns that customization can lead to collecting too much data. Historical complaints about navigation should not be treated as current UI defects. | Keep familiar Outlook-like scheduling choices; reduce mandatory data entry. Make the initial arrangement useful without a configuration project. |
| Gavel Workflows | Guided intake with relevant questions, contextual explanation, saved progress and reusable information. | A small, historical independent sample praises client questionnaires, clean portal presentation and authoring flexibility; builder setup and pricing concerns differ from end-user usability. | Borrow purposeful forms and clear next steps for intake; keep daily task capture short. Do not add a new automation builder. |
| MyCase (adjacent check) | Shared calendar views and task-management surfaces connect scheduling with case work. | This brief does not draw a broad sentiment conclusion from the small anecdotal sample reviewed. | Reinforces a combined agenda with clear event kinds. Does not justify adding another dashboard or copying its full feature set. |

## Evidence with dates and caveats

### Clio

[Get Started With Matters](https://help.clio.com/hc/en-us/articles/9285920226075-Get-Started-With-Matters), updated 8 September 2026, documents matter subtabs, permission/subscription-dependent availability and customizable dashboard sections. This is good evidence of available organization controls; it does not prove novice users can discover them easily.

[G2 individual reviews, page 4](https://www.g2.com/products/clio-clio-manage/reviews?page=4) includes a paralegal review dated 16 April 2026 praising quick task/note updates and keyword lookup. An attorney review from that date criticizes switching between Grow and Manage and asks for more control over a matter dashboard. Other April reviews value a central place for client information. Several are labeled seller-invited; one is incentivized. Treat these as examples of needs, not percentages of users. Current September documentation may describe capabilities added after those April complaints.

[Grow tasks and checklists](https://help.clio.com/hc/en-us/articles/9207009137051-Clio-Grow-Tasks-and-Checklists) documents a distinction between Grow tasks and Manage tasks. This supports avoiding fragmented task models in LawHand. [Grow pipeline](https://help.clio.com/hc/en-us/articles/9286134468507-Clio-Grow-Pipeline) documents status-based lead organization. LawHand already has an intake pipeline, so the opportunity is clearer navigation and continuity rather than a replacement pipeline.

### PracticePanther

[Tasks Tutorial](https://support.practicepanther.com/en/articles/480005-tasks-tutorial), dated 22 December 2022 and still published, documents subject/assignee requirements, matter/contact auto-fill, reminders and reusable workflows. [Calendar Tutorial](https://support.practicepanther.com/en/articles/480006-calendar-tutorial) describes scheduling and agenda workflows. Older support dates limit what we can infer about today's visual layout.

[Capterra individual reviews](https://www.capterra.com/p/140231/PracticePanther-Legal-Software/reviews/), page updated 16 September 2026: a non-incentivized small-firm owner review from 31 December 2024 attributes ease of learning to logical placement of controls. A non-incentivized partner review from 3 January 2025 praises usability/support but notes a limitation in saved email threads. The page also contains support complaints, so “everyone loves support” would be inaccurate. A 20 May 2026 review excerpt praises quick onboarding and matter opening. These are concrete usability signals rather than evidence that a particular color scheme causes satisfaction.

### Case Master Pro / CMPOnline

For this research, “casemaster” is interpreted as **Case Master Pro / CMPOnline from Case Master, Inc.** If the user meant a different vendor, replace this comparison; the name alone does not uniquely identify a product.

[Software Features](https://casemasterpro.com/software-features/) describes the case-file starting screen, configurable case types, related parties and individual review work lists. [Vendor background](https://casemasterpro.com/legal-case-management-software/) identifies the debt-collection/legal focus. The features page was available through search indexing; a direct fetch timed out during verification.

[Capterra Case Master Pro reviews](https://www.capterra.com/p/79319/Case-Master-Pro/reviews/), page updated 3 June 2026, showed only 19 reviews in the retrieved snapshot. Its positive customization/usability signal has limited breadth and may reflect collections users and vendor-referred review selection. Do not turn its perfect aggregate score into proof of superior general-purpose UX.

### PracticeMaster

[Tabs3 PracticeMaster product documentation](https://www.tabs3.com/tabs3-cloud/practice-master/) describes Matter Manager, personal/firm calendars, day/week/month views, staff/activity color coding, Outlook integration, workflows and access controls. These are documented capabilities; testimonials on the same vendor page are marketing evidence.

[Capterra Tabs3 reviews](https://www.capterra.com/p/2589/Tabs3-Billing/reviews/), page updated 17 September 2026, includes a non-incentivized PracticeMaster-related review from 1 August 2019 praising workflow customization while warning that users can get carried away collecting data. An incentivized April 2020 review criticizes complexity across multiple programs, followed by a vendor response describing improvements. These old reviews illustrate a design tradeoff; they do not establish that 2026 PracticeMaster still has the same defects. Reviews cover the Tabs3 suite, not always PracticeMaster alone.

An older PracticeMaster manual and a hosting-consultant review were also located. They were not used as the main basis for current feature/UI claims because of version age and commercial bias.

### Gavel Workflows

This addition examines Gavel's guided intake/document-automation product, not Gavel Exec's AI contract drafting. No Gavel trial or authenticated workflow was tested. Available documentation and selected public reviews inform concepts; they do not establish current novice-user success rates.

[Legal Client Intake Software](https://www.gavel.io/legal-intake-software), accessed 22 September 2026, describes conditional questions, response validation, short explainer icons, visible progress, pause/return, editable previous answers and reusing information in later work. Those are documented vendor capabilities. Claims on the page that outputs are always accurate are marketing and are not adopted here.

[Building Beautiful Guided Interviews](https://www.gavel.io/resources/building-guided-legal-interviews), published 10 November 2021 and updated 2 May 2025, emphasizes a specific user and purpose, manageable scope, purposeful questions and testing/refinement. It also acknowledges complex decision trees behind the apparently simple client experience. This supports separating the trained workflow author's setup from the everyday user's task.

[G2 Gavel pros/cons and individual reviews](https://www.g2.com/products/gavel/reviews?qs=pros-and-cons) showed a small sample of 11 reviews, many from 2021. A validated organic immigration-lawyer review dated 26 December 2023 praises conditional questionnaires, a clean client portal and a shareable link, while raising pricing and integration concerns. The integration complaint is historical, not evidence that the same gap exists today. This is directional evidence that a well-built client flow can feel simple even when its setup is sophisticated.

Some official help pages were available in search results but their redirects could not be fetched. No claim here depends on assuming those unseen pages or a current product trial. A final review/edit summary is a LawHand design proposal, not a claim that every Gavel interview includes one.

**Transfer into LawHand (proposed, to validate with the relevant owner):**

- New Task: retain one brief form; prefill visible matter/client context, disclose optional fields, and keep input after a failed save.
- Intake/conversion: use named steps only for a longer flow, show applicable questions and existing contact matches, then review the selected outcome before committing.
- Existing longer document intake: the document-automation owner owns pause/return and saving/saved/submitted behavior. Core UX consumes that contract at entry/return points; promise durable resume only where the actual persistence supports it.
- Matter overview: present next work and concise context; open substantial setup when requested. A question or button should explain its effect where the user acts.
- Calendar: type/source filters and clear dates help more than turning scheduling into an interview.

Core UX owns everyday form/context clarity and the CRM handoff. The separately owned document-automation work owns questionnaires, document preparation and persisted document drafts. These are constrained refinements to existing LawHand flows. They do not expand this epic into a workflow builder, document engine, universal wizard or a promise to automate legal judgment.
### MyCase

[Calendar overview](https://supportcenter.mycase.com/en/articles/9370065-calendar-overview) and [Tasks overview](https://supportcenter.mycase.com/en/articles/9370074-tasks-overview), February 2026 documentation, provide an adjacent check on scheduling/task organization. No MyCase trial account was used, and isolated Reddit complaints were not promoted into general conclusions.

## Extended vendor coverage (added in the parity pass)

Added 22 September 2026 to support the [feature-parity audit](./core-ux-feature-parity-2026-09-22.md). These vendors were not in the original brief. **Review-platform caveat:** G2, Capterra, TrustRadius and SoftwareAdvice returned HTTP 403 to automated fetching during this pass, so review sentiment below comes from Lawyerist (editorial plus self-selected community comments that Lawyerist states are not seller-invited) and search snippets. Samples are small and mostly 2018–2023. Treat as directional only. `[DOC]` marks documented vendor capability; `[REV]` marks user-review sentiment.

| Product | Documented pattern | Reported value and friction | LawHand implication |
| --- | --- | --- | --- |
| Smokeball | `[DOC]` Creating a task from a matter tags the matter by default; there is a global task view, priorities, sub-tasks, and workflows that auto-assign tasks by action/critical date. Per-user dashboard widgets include a **Daily Digest** of events, tasks and phone messages ([Tasks](https://support.smokeball.com/hc/en-us/articles/5859270337815-Tasks), updated 6 Apr 2026; [Dashboard](https://support.smokeball.com/hc/en-us/articles/5911375550743), updated 3 Apr 2024). | `[REV]` Lawyerist composite 4.1/5 (community 3.8, 6 ratings). Praise for document automation and a claimed time-savings on timekeeping; friction is complex setup, migration/refund disputes, no macOS/Google. G2 ~4.7 across ~387 reviews per snippet (no date). | The sticky wins are document automation and a single "today" digest. Make matter-created tasks prefill context, and protect onboarding/migration trust rather than adding configuration. |
| Filevine | `[DOC]` **Taskflow** builds sequences of dependent auto-tasks triggered by a project phase change or an action button, with role-based assignment, **replacement codes** that inject project/client data into task text, relative due dates and repeating tasks ([Taskflow](https://support.filevine.com/hc/en-us/articles/360005080892-Taskflow), updated 11 Aug 2026). | `[REV]` Lawyerist composite 4.2/5 (community 4.0, 12 ratings). Praise for customizability, feed-driven case movement, texting and document generation; the most consistent complaint is **complexity and setup burden** ("expect you to program their version of Salesforce"). | Phase-triggered tasks and replacement codes are the transferable ideas, but ship **opinionated out-of-box templates**, not a blank canvas. |
| Rocket Matter | `[DOC — not substantiated]` Help centre is login/JS-gated and returned no article content; only marketing pages were retrievable. | `[REV]` Lawyerist composite 4.3/5 (community 4.0, **1** rating). Praise for client portal and project management (Kanban added); the sole community review (Feb 2018) cites **tedious time entry, no bulk "add all to invoice", slow UI**. | Add **bulk actions** and a **Kanban** matter/task board; the documented friction was per-row latency, so speed is a differentiator for small firms. |
| Actionstep | `[DOC — not substantiated]` Help-centre articles are JS-gated; only marketing pages retrieved. | `[REV]` Lawyerist composite 4.1/5 (community 4.2, 5 ratings). Praise for true all-in-one and workflows that auto-assign tasks on matter creation and as steps complete, with a one-stop matter dashboard. Friction is setup complexity and vendor/implementer accountability. | Auto-generate and auto-assign a **task set on matter creation by matter type**, advancing on step completion; give each matter a single dashboard. |
| Centerbase | `[DOC]` Separate **form layouts per Activity subtype** — different fields for an Appointment vs a Task, with configurable subtype defaults and templates ([form layouts](https://support.centerbase.com/hc/en-us/articles/360051788391), updated 3 Jan 2023). | `[REV]` Lawyerist composite 3.9/5 (community **3.0**, 1 rating). Praise for accounting and documents; friction is support/consultant dependence (configuration changes quoted at $200/hr) and primitive documentation. | Per-subtype field layouts are configurable value, but deep config needs **in-house onboarding**; the complaint was support dependence, not the config itself. |
| Lawmatics | `[DOC]` Intake pipeline with prebuilt stages, **drag-and-drop reorder**, automations on stage entry/exit, and per-stage **Total/Expected Value** from historical conversion. Tasks and Calendar are top-level navigation with a global search bar ([Intake Pipeline](https://help.lawmatics.com/en/articles/10699827-intake-pipeline); [Navigation](https://help.lawmatics.com/en/articles/10699800-lawmatics-navigation-experience); no visible dates). | `[REV]` Lawyerist composite 4.6/5 (community 4.7, 3 ratings). Praise for automations, signatures and lead management; friction is "too many steps to manually adjust certain things… could be more user-friendly". | Make the pipeline the CRM backbone with stage automations and per-stage value; surface Tasks and Calendar as top-level destinations; cut manual edit steps. |

**Cross-vendor patterns (extended set):** context inheritance on create; workflow/taskflow automation keyed to matter phase or stage; calendar and tasks as first-class navigation with a consolidated "today" view; deep configurability as the top complaint driver; CRM-to-matter continuity without re-entry; and unmet demand for bulk actions. Official product documentation for Rocket Matter and Actionstep could not be substantiated; G2/Capterra/TrustRadius/SoftwareAdvice were entirely blocked to fetching.

## Transferable principles

1. **Give every case a recognizable home.** Matter identity and context persist into tasks, calendar items and communication.
2. **Show the work before the machinery.** Dates, owner, current state and next action should appear before setup forms, empty metrics and advanced configuration.
3. **Offer a good arrangement, then a few controls.** Presets, show/hide, move up/down and reset are enough for this epic. Free-form dashboard design would burden the people asking for simplicity.
4. **Remember where the user was.** Opening a record and returning should retain scope, filters and position.
5. **Explain system state in ordinary words.** Saved locally, waiting for client, needs review and calendar reconnect required are distinct outcomes.
6. **Help with the next action.** Short inline guidance and clear empty states are more useful here than a long compulsory product tour.
7. **Make a control's promise match its effects.** The Working on this example shows why clear copy and a coherent behavior contract belong together. A personal view choice should not secretly alter permissions or reviewer responsibility.
8. **Carry context from the record into every action.** Tasks, dates and documents created inside a matter inherit its client/matter context; competitors that do this well (PracticePanther, Smokeball, Filevine, Actionstep) are praised for reducing re-entry.
9. **Prefer opinionated defaults over blank canvases.** The strongest recurring friction across the extended set is configuration burden and consultant dependence (Filevine, Actionstep, Centerbase, Smokeball). Useful defaults plus a few controls beat a builder.

These principles are inferences from the evidence. The epic's usability sessions will test them against LawHand staff tasks.

## LawHand-specific conclusion

The live walkthrough found good underlying capability with an uneven presentation hierarchy: extensive default matter columns; setup and signature creation above current work; inconsistent task forms; a calendar label that does not match its list range; and CRM/Intake labels that make related work appear separate. The initial core phases should reorder and clarify those existing capabilities. The follow-up audit also found that Working on this is a persistent manual flag with unexpected research-access and reviewer-ranking dependencies; UX-01A explicitly resolves that contract before new focus-list wording ships. The detailed [epic plan](../core-ux-future-state-epic-2026-09-22.md) maps each proposal to acceptance criteria and current source.
