# Guide image assets

Screenshots and diagrams used by the in-product guides in `frontend/platform_docs/`.

The `.webp` screenshots are generated from the real UI with synthetic data. Regenerate them rather than editing them by hand:

```bash
cd frontend
npm run docs:screenshots -- --only <shot-name>
```

Each file name matches a shot in `frontend/scripts/guide-screenshots/shots.mjs`. See `frontend/platform_docs/README.md` for how shots are defined, annotated, and referenced from a chapter.

`customer-data-task-lifecycle.svg` is the reusable architecture diagram for authoritative task routing and customer-owned document storage.

Every image must use redacted or synthetic data, carry meaningful alternative text where it is used, and stay under 600 KB.
