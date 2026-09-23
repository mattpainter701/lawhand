# Matter document storage recovery

This guide covers a failed matter-document write when the tenant uses
customer-owned cloud storage. The failure can happen even when the provider
connection and tenant storage root are available: each matter also needs a
provider folder binding.

## What the failure means

When cloud storage is authoritative and the matter has no binding for the
selected provider, the write fails closed. LawHand does not retry the write to
another provider or store the file on the application host. The upload or save
returns an actionable setup error, and no file was stored. A caller that
requires cloud storage receives the same cause as a structured result.

The missing-binding case is distinct from a revoked or expired provider
connection, denied provider access, a failed provisioning attempt, and a
temporary provider error. Follow the recovery message for the actual cause;
do not treat a general integration health indicator as proof that this
matter's folder exists or is writable.

## Recover a matter with no provider folder

1. In the affected matter, open **Documents** and expand **Document tools**.
2. If the message says the matter folder is not set up, choose **Set up
   folders**. This explicit matter-level action uses the existing configured
   root and provisioning/sharing workflow. Wait for the folder card to report
   success before retrying the upload or save. **Sync folder** is for a folder
   that is already provisioned.
3. Retry the original document action. Confirm that the document appears in
   the matter's document list and that its storage result identifies the
   expected provider.
4. If setup fails or the folder remains unavailable, check the firm-wide
   provider connection in **Administration → Integrations → Cloud**, then return to the
   matter's **Document tools** and retry setup. If the connection is healthy
   but this matter still has no binding, have an administrator or support
   operator inspect the matter's provider binding and the tenant's configured
   provider root through the approved storage-management workflow.

A missing-binding save failure does not provision a folder automatically,
change a provider root, or modify sharing permissions. The explicit **Set up
folders** action is the deliberate recovery step; it uses the firm's existing
provisioning and matter-sharing rules, which may create or update folder shares
for assigned users. This change does not alter those rules or automatically
invoke them after a failed save.
Do not ask a user to paste access tokens, client secrets, or other credentials
into a support request.

## Read the admin storage status correctly

The admin **Document storage** summary reports whether the configured or
automatic provider connection is available. The **Primary provider for matter
documents** control saves a tenant preference for new writes. A “Preference
saved” confirmation means that setting was saved; it does not validate a
particular matter folder, confirm a write to that folder, or move existing
folders. Changing the preference repoints new writes. Use the separate
storage-migration workflow under **Advanced** to rebind existing matters.

Directory and user synchronization is a separate provider capability. Its
availability may depend on the provider account tier and does not determine
whether document storage can write to an already provisioned matter folder.
Likewise, directory-sync success does not prove that a matter folder is ready.

## Incident evidence and privacy

A read-only incident review confirmed the failure occurred before the cloud
file upload because the matter's OneDrive binding was missing, even though a
tenant OneDrive root existed. A later successful upload followed a separate
update that populated the matter binding. The storage code now preserves this
cause so the user can be directed to matter-folder setup instead of receiving
a generic reconnect message.

This note intentionally omits tenant and matter identifiers, document names
and contents, timestamps tied to an account, and credentials. Collect only the
minimum redacted diagnostics needed to distinguish connection, binding,
permission, and transient-provider failures.
