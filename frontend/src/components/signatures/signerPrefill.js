import { newSignerRow } from './signatureRequestRules'

// The signer rows a just-generated document starts with. The matter's client
// is the one signer the platform knows by name and address; every other role
// the document requires gets an empty row carrying that role so staff see
// what is still owed. Nothing is invented for a role the matter cannot name.
export function initialSignersForMatter(matter, signingRoles = []) {
  const roles = [...new Set((signingRoles || []).filter(Boolean))]
  const client = {
    ...newSignerRow(),
    name: String(matter?.client_name || '').trim(),
    email: String(matter?.client_email || '').trim(),
  }
  if (!roles.length) return [client]
  const rows = roles.map((role) => (role === 'client' ? client : { ...newSignerRow(), role }))
  // Keep the client first: they usually sign first, and the order here is the
  // signing order when the firm enforces one.
  return rows.sort((a, b) => (a.role === 'client' ? -1 : b.role === 'client' ? 1 : 0))
}
