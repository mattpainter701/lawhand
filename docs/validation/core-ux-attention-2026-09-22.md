# My Matters attention view repair

PR #590 is a focused S3.04 slice over the matter-list contracts already on main. The attention entry opens the counted loaded records in the list, clears incompatible personal keyword/status filters, and retains sorting and All Matters filters. Clear filter removes the three personal filters atomically. Removing the attention chip keeps other filters; selecting Board clears attention because the lifecycle board does not apply that filter.

## Count and scope contract

Attention covers non-terminal assigned matters that are threatened, have an overdue or due-today deadline label, or are open/active and last updated more than 14 days ago. The heading and filtered list use the same predicate. The included conditions are visible beside the list.

The API still returns only page 1 with page size 200. The assigned summary uses the returned total. If total exceeds loaded rows, the heading says “loaded matters” and nearby text names the loaded/total counts and explains that search and filters apply to the loaded set. A missing total also receives loaded-scope wording. Failed requests or empty rows without a confirmed zero total offer retry instead of claiming there are no assigned matters. Late responses cannot replace a newer personal-list request.

This visible narrowing follows S3.04's permitted fallback. It does not complete S3.01–03, B1/B2 full-corpus paging/search, bounded SQL enrichment, stable backend ordering, the other list consumers, or staff usability validation. No focus/reviewer/access or document-generation contract changes are included.

## Validation

The concurrent count-predicate fix and its interaction test are preserved in this repair.

- Six regressions fail against the original PR: terminal-state attention, board-to-list navigation, combined clear, board switching, partial counts and failed-request feedback.
- Real page tests use MemoryRouter and synthetic API results; they check returned rows and URL state, retained sort/All Matters filters, chip removal, reload, partial scope and retry.
- All 34 focused attention/table/row tests, the three database-free release tests, focused ESLint/Ruff, the release-catalog check and the production frontend build pass locally. Final-head CI and Merge Gate remain required before merge.
- No production data, provider calls or database fixtures are needed for this presentation repair. Fixture persistence and backend completeness remain with their owners.
