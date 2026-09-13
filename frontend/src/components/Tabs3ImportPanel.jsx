import { useState } from 'react'
import {
  uploadTabs3ImportBundle,
  getExternalImportTables,
  reconcileExternalImport,
} from '../api'

/**
 * Operator tool: stage an on-prem Tabs3 export for review before cutover.
 *
 * Lived inside the firm-admin cloud panel, beside "Connect Google". It is a
 * rarely used migration flow, so it is mounted as an operator section under
 * the hub's Advanced disclosure instead.
 */
export default function Tabs3ImportPanel() {
  const [file, setFile] = useState(null)
  const [passphrase, setPassphrase] = useState('')
  const [accountingMode, setAccountingMode] = useState('tabs3_reference')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [run, setRun] = useState(null)
  const [tables, setTables] = useState([])
  const [reconcile, setReconcile] = useState(null)

  const handleUpload = async (event) => {
    event.preventDefault()
    if (!file) {
      setError('Choose a Tabs3 export bundle first.')
      return
    }
    setUploading(true)
    setError(null)
    setRun(null)
    setTables([])
    setReconcile(null)
    try {
      const uploaded = await uploadTabs3ImportBundle({ file, passphrase, accountingMode })
      setRun(uploaded)
      const [tableData, reconcileData] = await Promise.all([
        getExternalImportTables(uploaded.id),
        reconcileExternalImport(uploaded.id),
      ])
      setTables(tableData.tables || [])
      setReconcile(reconcileData)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Tabs3 import upload failed.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="bg-brand-surface border border-brand-line rounded-xl p-6">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
        <div>
          <h3 className="text-brand-ink font-sans text-base font-bold">Tabs3 Import</h3>
          <p className="text-brand-ink-2 font-sans text-xs mt-1">
            Stage an on-prem Tabs3 export bundle for review before cutover.
          </p>
        </div>
        {run && (
          <span className="px-2.5 py-1 rounded-lg bg-green-100 text-green-700 border border-green-200 text-xs font-bold">
            {run.status}
          </span>
        )}
      </div>

      <form onSubmit={handleUpload} className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr_1fr_auto] gap-3 items-end">
        <label className="block">
          <span className="block text-xs font-bold text-brand-ink mb-1">Export bundle</span>
          <input
            type="file"
            accept=".zip,.tabs3bundle,application/zip,application/octet-stream"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            className="block w-full text-sm text-brand-ink file:mr-3 file:px-3 file:py-2 file:rounded-lg file:border file:border-brand-line file:bg-brand-bg file:text-brand-ink file:text-xs file:font-bold"
          />
        </label>
        <label className="block">
          <span className="block text-xs font-bold text-brand-ink mb-1">Passphrase</span>
          <input
            type="password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
            placeholder="Encrypted bundles"
            className="w-full px-3 py-2 bg-brand-bg border border-brand-line rounded-lg text-brand-ink font-sans text-sm focus:outline-none focus:ring-2 focus:ring-brand-ink/20"
          />
        </label>
        <label className="block">
          <span className="block text-xs font-bold text-brand-ink mb-1">Accounting mode</span>
          <select
            value={accountingMode}
            onChange={(event) => setAccountingMode(event.target.value)}
            className="w-full px-3 py-2 bg-brand-bg border border-brand-line rounded-lg text-brand-ink font-sans text-sm focus:outline-none focus:ring-2 focus:ring-brand-ink/20"
          >
            <option value="tabs3_reference">Tabs3 reference</option>
            <option value="clarity_native">LawHand native</option>
            <option value="qbo">QuickBooks Online</option>
          </select>
        </label>
        <button
          type="submit"
          disabled={uploading}
          className="px-4 py-2 bg-brand-ink text-white rounded-lg font-sans text-sm font-bold hover:bg-brand-ink/90 disabled:opacity-50"
        >
          {uploading ? 'Uploading...' : 'Upload'}
        </button>
      </form>

      {error && (
        <div className="mt-4 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs font-medium">
          {error}
        </div>
      )}

      {reconcile && (
        <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-brand-bg border border-brand-line rounded-lg p-3">
            <div className="text-[11px] uppercase font-bold text-brand-ink-2">Run</div>
            <div className="text-sm font-bold text-brand-ink truncate">{reconcile.export_id || run?.id}</div>
          </div>
          <div className="bg-brand-bg border border-brand-line rounded-lg p-3">
            <div className="text-[11px] uppercase font-bold text-brand-ink-2">Tables</div>
            <div className="text-sm font-bold text-brand-ink">{reconcile.table_count}</div>
          </div>
          <div className="bg-brand-bg border border-brand-line rounded-lg p-3">
            <div className="text-[11px] uppercase font-bold text-brand-ink-2">Rows</div>
            <div className="text-sm font-bold text-brand-ink">{reconcile.total_rows}</div>
          </div>
          <div className="bg-brand-bg border border-brand-line rounded-lg p-3">
            <div className="text-[11px] uppercase font-bold text-brand-ink-2">Warnings</div>
            <div className="text-sm font-bold text-brand-ink">{reconcile.warnings?.length || 0}</div>
          </div>
        </div>
      )}

      {tables.length > 0 && (
        <div className="mt-5 overflow-x-auto border border-brand-line rounded-lg">
          <table className="min-w-full text-sm">
            <thead className="bg-brand-bg-soft text-brand-ink-2 text-xs uppercase">
              <tr>
                <th className="text-left px-3 py-2 font-bold">Table</th>
                <th className="text-right px-3 py-2 font-bold">Rows</th>
                <th className="text-left px-3 py-2 font-bold">Checksum</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-line">
              {tables.map((table) => (
                <tr key={table.source_table}>
                  <td className="px-3 py-2 font-mono text-xs text-brand-ink">{table.source_table}</td>
                  <td className="px-3 py-2 text-right text-brand-ink">{table.row_count}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-brand-ink-2 truncate max-w-sm">{table.checksum || 'metadata-only'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
