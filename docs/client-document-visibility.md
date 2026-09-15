# What the client can see — one definition across three surfaces

Staff answer "what can the client see?" from the matter documents tab; clients
answer it from the portal. Those two, and the portal overview, used to give
three different answers
([#489](https://github.com/mattpainter701/lawhand/issues/489)).

## What was wrong

| Surface | Counted / labelled |
| --- | --- |
| Portal overview | `portal_visible` only — which includes the client's own uploads, because the portal upload path marks them visible. |
| Portal documents tab, downloads | `portal_visible` **or** the recipient's intake-packet grants. |
| Staff documents tab | `portal_visible`; everything else read "Private", including paperwork the signing recipient could open. |

A per-recipient signing grant cannot be represented by the single
`portal_visible` bit, so the counts could not be reconciled by picking one of
them.

## The definition

`app/services/portal_document_access.py` names the access routes instead of
collapsing them. Every count and label derives from these:

| Source | Meaning |
| --- | --- |
| `firm_shared` | The firm shared it with the matter's client (`portal_visible`). |
| `signing_packet` | The recipient's own intake packet entitles them to it — the fee agreement behind the packet's signature request, and the documents named by its requirements. Narrower than a share: only the holder of that packet can read it. A revoked invite grants nothing. |
| `client_upload` | The client sent it to the firm and can read their own file back. |

## What each surface now says

- **Portal overview** counts everything this login can open — exactly the rows
  the documents tab lists — under "Documents available to you", with the
  breakdown beneath it ("1 shared by your firm · 2 for signing · 1 sent by
  you"). `PortalMatterView` carries `firm_shared_document_count`,
  `signing_document_count` and `client_upload_count`, and the three sum to
  `document_count`; a test pins that parity.
- **Portal documents tab** groups by the same three sources. Signing paperwork
  appears under "Available to you for signing", noted as not shared with the
  matter's other contacts.
- **Staff documents tab** shows "Available to signing client" (with a distinct
  badge) where `signing_access` is true, instead of "Private". The share toggle
  still works: sharing is what makes a document visible to the client portal
  generally, and the tooltip says so.

## Verified: a signing grant does widen visibility

The issue asked for this to be verified either way. It does widen it, by
design: a document with `portal_visible = false` that the packet grants is
listed and served to that recipient — `test_signing_grants_do_widen_visibility_beyond_the_shared_set`
proves the download reaches storage for a grant-only document and is refused
before storage for a private one. What was wrong was never the access; it was
that the staff tab described that document as "Private".

No unauthorized access was found. The boundary holds: a document that is
neither shared nor granted is not listed, not counted, and not downloadable.
