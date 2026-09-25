import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MatterDocumentsTab, { canReviseWithAssistant, isAssistantRevisionDocument } from './MatterDocumentsTab'
import { ConfirmProvider } from './dialog/ConfirmProvider'
import { ToastProvider } from './toast/ToastProvider'

// Opened a minute ago, so the 12-hour editing marker is live whenever the suite runs.
const RECENT = new Date(Date.now() - 60_000).toISOString()

function LocationProbe() {
  const location = useLocation()
  return <span data-testid="location-search">{location.search}</span>
}

const apiMocks = vi.hoisted(() => ({
  default: { post: vi.fn() },
  getMatterPortalUploadLink: vi.fn().mockResolvedValue({ url: null }),
  setMatterPortalUploadLink: vi.fn(),
  createDocumentTag: vi.fn(),
  createMatterDocumentFolder: vi.fn(),
  deleteMatterDocument: vi.fn(),
  deleteMatterDocumentFolder: vi.fn(),
  getDocumentTags: vi.fn(),
  getMatterCloudFiles: vi.fn(),
  getMatterCloudFolder: vi.fn(),
  getMatterDocumentDownloadUrl: vi.fn(),
  getMatterDocumentFolders: vi.fn(),
  getMatterDocuments: vi.fn(),
  getMatterDocumentPrefill: vi.fn().mockResolvedValue(null),
  getMatterDocumentSigningSource: vi.fn().mockResolvedValue(null),
  getMatterDocumentFormSources: vi.fn().mockResolvedValue({ sources: [] }),
  readMatterDocumentAgainstForm: vi.fn(),
  getMatterFillSessions: vi.fn().mockResolvedValue({ items: [] }),
  searchMatterDocumentText: vi.fn().mockResolvedValue({ query: '', results: [], indexed_documents: 0 }),
  abandonFillSession: vi.fn(),
  moveMatterDocuments: vi.fn(),
  provisionMatterCloudFolder: vi.fn(),
  setMatterDocumentTags: vi.fn(),
  syncMatterCloudFolder: vi.fn(),
  updateMatterDocument: vi.fn(),
  updateMatterDocumentFolder: vi.fn(),
  uploadMatterDocument: vi.fn(),
  getMatterDocumentOpenUrl: vi.fn((matterId, documentId) => `/api/matters/${matterId}/documents/${documentId}/open`),
  startMatterDocumentCloudEdit: vi.fn(),
  reconcileMatterDocument: vi.fn(),
  uploadRevisedMatterDocument: vi.fn(),
}))

vi.mock('../api', () => apiMocks)

const documents = [
  {
    id: 'docx-1',
    filename: 'Contract.docx',
    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    document_category: 'contract',
    file_size: 2048,
    description: 'Client engagement terms',
    portal_visible: false,
    storage_backend: 'local',
    created_at: '2026-08-04T12:00:00Z',
  },
  {
    id: 'pdf-1',
    filename: 'Filed pleading.pdf',
    content_type: 'application/pdf',
    generation_summary: { template_id: 't-1', template_title: 'Pleading form', template_version_no: 2, total: 19, filled: 17, verified: 12, verified_fields: [] },
    document_category: 'pleading',
    file_size: 4096,
    portal_visible: false,
    storage_backend: 'local',
    created_at: '2026-08-03T12:00:00Z',
  },
  {
    id: 'assistant-1',
    filename: 'Contract-revision-v1.docx',
    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    document_category: 'assistant_revision',
    file_size: 2200,
    portal_visible: false,
    storage_backend: 'local',
    created_at: '2026-08-04T13:00:00Z',
  },
]

const folders = [
  {
    id: 'folder-discovery',
    matter_id: 'matter-1',
    parent_id: null,
    name: 'Discovery',
    path: 'Discovery',
    depth: 0,
    kind: 'user',
    system_key: null,
    document_count: 1,
    created_at: '2026-08-01T12:00:00Z',
    updated_at: '2026-08-01T12:00:00Z',
  },
  {
    id: 'folder-depos',
    matter_id: 'matter-1',
    parent_id: 'folder-discovery',
    name: 'Depositions',
    path: 'Discovery/Depositions',
    depth: 1,
    kind: 'user',
    system_key: null,
    document_count: 0,
    created_at: '2026-08-01T12:00:00Z',
    updated_at: '2026-08-01T12:00:00Z',
  },
  {
    id: 'folder-client-uploads',
    matter_id: 'matter-1',
    parent_id: null,
    name: 'Client Uploads',
    path: 'Client Uploads',
    depth: 0,
    kind: 'system',
    system_key: 'client_uploads',
    document_count: 1,
    created_at: '2026-08-01T12:00:00Z',
    updated_at: '2026-08-01T12:00:00Z',
  },
]

const tags = [
  { id: 'tag-signed', name: 'Signed', color: 'green' },
  { id: 'tag-privileged', name: 'Privileged', color: 'rose' },
]

function renderDocuments(onReviseDocument = vi.fn(), { initialEntries = ['/matters/matter-1'] } = {}) {
  return {
    onReviseDocument,
    ...render(
      <MemoryRouter initialEntries={initialEntries}>
        <ToastProvider>
          <ConfirmProvider>
            <MatterDocumentsTab matterId="matter-1" onReviseDocument={onReviseDocument} />
            <LocationProbe />
          </ConfirmProvider>
        </ToastProvider>
      </MemoryRouter>,
    ),
  }
}

describe('MatterDocumentsTab assistant revision entry point', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getMatterDocuments.mockResolvedValue({ items: documents, total: documents.length })
    apiMocks.getMatterCloudFiles.mockResolvedValue({ files: [] })
    apiMocks.getMatterCloudFolder.mockResolvedValue(null)
    apiMocks.getMatterDocumentFolders.mockResolvedValue({ items: folders, total: folders.length, root_document_count: 1 })
    apiMocks.getDocumentTags.mockResolvedValue({ items: tags, total: tags.length })
    apiMocks.getMatterDocumentDownloadUrl.mockImplementation((matterId, documentId) => `/api/matters/${matterId}/documents/${documentId}/download`)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('copies into a chosen folder and retains a failed request ID for retry', async () => {
    apiMocks.default.post.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: {} })
    renderDocuments()
    await screen.findAllByText('Contract.docx')
    fireEvent.click(screen.getByRole('button', { name: 'Folder', exact: true }))
    const card = screen.getByText('Contract.docx').closest('article')
    fireEvent.click(within(card).getByText('Copy to…'))
    fireEvent.change(screen.getByLabelText('Destination folder'), { target: { value: 'folder-discovery' } })
    fireEvent.click(screen.getByText('Copy here'))
    await screen.findByRole('alert')
    const first = apiMocks.default.post.mock.calls[0][1]
    expect(first).toMatchObject({ document_id: 'docx-1', folder_id: 'folder-discovery' })
    fireEvent.click(screen.getByText('Copy here'))
    await waitFor(() => expect(screen.queryByLabelText('File operation')).not.toBeInTheDocument())
    expect(apiMocks.default.post.mock.calls[1][1]).toEqual(first)
    expect(apiMocks.moveMatterDocuments).not.toHaveBeenCalled()
    expect(localStorage.getItem('document-view:matter-1')).toBe('folder')
  })

  it('recognizes DOCX by extension or MIME type but not PDF', () => {
    expect(canReviseWithAssistant({ filename: 'draft.DOCX' })).toBe(true)
    expect(canReviseWithAssistant({ filename: 'draft', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })).toBe(true)
    expect(canReviseWithAssistant({ filename: 'file.pdf', content_type: 'application/pdf' })).toBe(false)
    expect(isAssistantRevisionDocument(documents[2])).toBe(true)
  })

  it('opens the assistant for DOCX and disables other formats with a clear reason', async () => {
    const user = userEvent.setup()
    const { onReviseDocument } = renderDocuments()

    const docxButtons = await screen.findAllByRole('button', { name: 'Revise Contract.docx with assistant' })
    await user.click(docxButtons[0])
    expect(onReviseDocument).toHaveBeenCalledWith(expect.objectContaining({ id: 'docx-1' }))

    const pdfButtons = screen.getAllByRole('button', { name: 'Revise Filed pleading.pdf with assistant' })
    expect(pdfButtons.length).toBeGreaterThan(0)
    pdfButtons.forEach((button) => expect(button).toBeDisabled())
    expect(screen.getByText('Assistant revisions currently support DOCX files only.')).toBeInTheDocument()
  })

  it('has no detectable accessibility violations in the mobile and desktop document layouts', async () => {
    const { container } = renderDocuments()
    await screen.findAllByText('Contract.docx')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('keeps assistant derivatives out of the legacy client-release control', async () => {
    renderDocuments()

    const releaseControls = await screen.findAllByRole('button', {
      name: 'Contract-revision-v1.docx requires a separate release workflow',
    })
    releaseControls.forEach((control) => expect(control).toBeDisabled())
    expect(screen.getAllByText('Release locked').length).toBeGreaterThan(0)
    expect(apiMocks.updateMatterDocument).not.toHaveBeenCalled()
  })
})


describe('MatterDocumentsTab document explorer', () => {
  beforeEach(() => {
    apiMocks.getMatterDocuments.mockResolvedValue({ items: documents, total: documents.length })
    apiMocks.getMatterCloudFiles.mockResolvedValue({ files: [] })
    apiMocks.getMatterCloudFolder.mockResolvedValue(null)
    apiMocks.getMatterDocumentFolders.mockResolvedValue({ items: folders, total: folders.length, root_document_count: 1 })
    apiMocks.getDocumentTags.mockResolvedValue({ items: tags, total: tags.length })
    apiMocks.getMatterDocumentDownloadUrl.mockImplementation((matterId, documentId) => `/api/matters/${matterId}/documents/${documentId}/download`)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders the folder rail with counts and marks the system folder unmanageable', async () => {
    renderDocuments()

    const rail = await screen.findByRole('navigation', { name: 'Document folders' })
    expect(within(rail).getByRole('button', { name: 'Discovery' })).toBeInTheDocument()
    expect(within(rail).getByRole('button', { name: 'Unfiled' })).toBeInTheDocument()

    // A firm can add a subfolder under the protected folder but cannot rename
    // or delete it, because the client portal files uploads there.
    expect(
      within(rail).getByRole('button', { name: 'New subfolder in Client Uploads' }),
    ).toBeInTheDocument()
    expect(
      within(rail).queryByRole('button', { name: 'Rename Client Uploads' }),
    ).not.toBeInTheDocument()
    expect(
      within(rail).queryByRole('button', { name: 'Delete Client Uploads' }),
    ).not.toBeInTheDocument()
  })

  it('keeps documents and the refresh control available after a transient refresh failure', async () => {
    const user = userEvent.setup()
    renderDocuments()
    const refresh = await screen.findByRole('button', { name: 'Refresh document list' })
    await screen.findAllByText('Contract.docx')
    apiMocks.getMatterDocuments.mockRejectedValueOnce(new Error('offline'))
    await user.click(refresh)
    expect(await screen.findByText('Could not refresh documents')).toBeInTheDocument()
    expect(screen.getAllByText('Contract.docx').length).toBeGreaterThan(0)
    await waitFor(() => expect(refresh).toBeEnabled())
    await user.click(refresh)
    await waitFor(() => expect(apiMocks.getMatterDocuments).toHaveBeenCalledTimes(3))
    expect(screen.getByRole('navigation', { name: 'Document folders' })).toBeInTheDocument()
  })

  it('scopes the listing to the folder the user opens', async () => {
    const user = userEvent.setup()
    renderDocuments()

    const rail = await screen.findByRole('navigation', { name: 'Document folders' })
    await user.click(within(rail).getByRole('button', { name: 'Discovery' }))

    await waitFor(() =>
      expect(apiMocks.getMatterDocuments).toHaveBeenLastCalledWith(
        'matter-1',
        expect.objectContaining({ folder_id: 'folder-discovery', include_subfolders: true }),
      ),
    )
  })

  it('asks the server for unfiled documents rather than filtering in the browser', async () => {
    const user = userEvent.setup()
    renderDocuments()

    const rail = await screen.findByRole('navigation', { name: 'Document folders' })
    await user.click(within(rail).getByRole('button', { name: 'Unfiled' }))

    await waitFor(() =>
      expect(apiMocks.getMatterDocuments).toHaveBeenLastCalledWith(
        'matter-1',
        expect.objectContaining({ folder_id: 'root' }),
      ),
    )
  })

  it('creates a folder and opens it', async () => {
    const user = userEvent.setup()
    apiMocks.createMatterDocumentFolder.mockResolvedValue({
      id: 'folder-new',
      name: 'Trial',
      path: 'Trial',
      parent_id: null,
      depth: 0,
      kind: 'user',
      document_count: 0,
    })
    renderDocuments()

    await screen.findByRole('navigation', { name: 'Document folders' })
    await user.click(screen.getByRole('button', { name: /New Folder/i }))
    await user.type(screen.getByLabelText('New folder name'), 'Trial')
    await user.click(screen.getByRole('button', { name: 'Create folder' }))

    await waitFor(() =>
      expect(apiMocks.createMatterDocumentFolder).toHaveBeenCalledWith('matter-1', {
        name: 'Trial',
        parent_id: null,
      }),
    )
    await waitFor(() =>
      expect(apiMocks.getMatterDocuments).toHaveBeenLastCalledWith(
        'matter-1',
        expect.objectContaining({ folder_id: 'folder-new' }),
      ),
    )
  })

  it('files a document into a folder when it is dragged onto the rail', async () => {
    apiMocks.moveMatterDocuments.mockResolvedValue({ moved: 1, folder_id: 'folder-discovery', items: [] })
    renderDocuments()

    const rail = await screen.findByRole('navigation', { name: 'Document folders' })
    const target = within(rail).getByRole('button', { name: 'Discovery' }).closest('div')
    const payload = JSON.stringify(['docx-1'])
    const dataTransfer = {
      getData: (type) => (type === 'text/plain' || type.startsWith('application/') ? payload : ''),
      dropEffect: '',
    }

    fireEvent.dragOver(target, { dataTransfer })
    fireEvent.drop(target, { dataTransfer })

    await waitFor(() =>
      expect(apiMocks.moveMatterDocuments).toHaveBeenCalledWith(
        'matter-1',
        ['docx-1'],
        'folder-discovery',
      ),
    )
  })

  it('searches and filters by tag on the server', async () => {
    const user = userEvent.setup()
    renderDocuments()

    await screen.findByRole('navigation', { name: 'Document folders' })
    await user.type(screen.getByLabelText('Search documents'), 'compel')
    await waitFor(() =>
      expect(apiMocks.getMatterDocuments).toHaveBeenLastCalledWith(
        'matter-1',
        expect.objectContaining({ q: 'compel' }),
      ),
    )

    await user.click(screen.getByRole('button', { name: 'Signed', pressed: false }))
    await waitFor(() =>
      expect(apiMocks.getMatterDocuments).toHaveBeenLastCalledWith(
        'matter-1',
        expect.objectContaining({ tag_ids: ['tag-signed'] }),
      ),
    )
  })

  it('shows excerpts found inside the documents for a search', async () => {
    apiMocks.searchMatterDocumentText.mockResolvedValue({
      query: 'compel',
      indexed_documents: 2,
      results: [
        { document_id: 'pdf-1', filename: 'Filed pleading.pdf', chunk_index: 0, snippet: 'moves to **compel** discovery responses', score: 0.02, matched_by: ['words'], open_url: '/api/matters/matter-1/documents/pdf-1/open' },
      ],
    })
    const user = userEvent.setup()
    renderDocuments()
    await screen.findByRole('navigation', { name: 'Document folders' })
    await user.type(screen.getByLabelText('Search documents'), 'compel')
    const found = await screen.findByRole('region', { name: 'Found inside documents' }, { timeout: 3000 })
    expect(within(found).getByText('Found inside 1 document')).toBeInTheDocument()
    expect(within(found).getByText('moves to compel discovery responses')).toBeInTheDocument()
    expect(within(found).getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/api/matters/matter-1/documents/pdf-1/open')
    await waitFor(() =>     expect(apiMocks.searchMatterDocumentText).toHaveBeenCalledWith('matter-1', 'compel', 25))
  })

  it('replaces the tags on a document from its row', async () => {
    const user = userEvent.setup()
    apiMocks.setMatterDocumentTags.mockResolvedValue({ items: [tags[0]], total: 1 })
    renderDocuments()

    await screen.findByRole('navigation', { name: 'Document folders' })
    await user.click(screen.getByRole('button', { name: 'Edit tags for Contract.docx' }))

    const dialog = await screen.findByRole('dialog', { name: 'Edit document tags' })
    await user.click(within(dialog).getByRole('checkbox', { name: /Signed/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Save tags' }))

    await waitFor(() =>
      expect(apiMocks.setMatterDocumentTags).toHaveBeenCalledWith('matter-1', 'docx-1', [
        'tag-signed',
      ]),
    )
  })

  it('uploads into the folder that is currently open', async () => {
    const user = userEvent.setup()
    apiMocks.uploadMatterDocument.mockResolvedValue({ ...documents[0], id: 'new-doc' })
    renderDocuments()

    const rail = await screen.findByRole('navigation', { name: 'Document folders' })
    await user.click(within(rail).getByRole('button', { name: 'Discovery' }))
    await user.click(screen.getByRole('button', { name: /Upload Document/i }))

    await waitFor(() =>
      expect(screen.getByLabelText('Folder')).toHaveValue('folder-discovery'),
    )

    const file = new File(['body'], 'rogs.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByLabelText('File *'), file)
    await user.click(screen.getByRole('button', { name: /^Upload$/ }))

    await waitFor(() => expect(apiMocks.uploadMatterDocument).toHaveBeenCalled())
    const formData = apiMocks.uploadMatterDocument.mock.calls[0][1]
    expect(formData.get('folder_id')).toBe('folder-discovery')
  })

  it('deletes a folder without deleting the documents inside it', async () => {
    const user = userEvent.setup()
    apiMocks.deleteMatterDocumentFolder.mockResolvedValue({
      deleted_folder_id: 'folder-discovery',
      documents_moved: 1,
      moved_to_folder_id: null,
    })
    renderDocuments()

    const rail = await screen.findByRole('navigation', { name: 'Document folders' })
    await user.click(within(rail).getByRole('button', { name: 'Delete Discovery' }))
    await user.click(await screen.findByRole('button', { name: 'Delete folder' }))

    await waitFor(() =>
      expect(apiMocks.deleteMatterDocumentFolder).toHaveBeenCalledWith(
        'matter-1',
        'folder-discovery',
        { moveDocumentsToParent: true },
      ),
    )
  })
})

describe('MatterDocumentsTab signing-grant labelling', () => {
  // #489: a document reachable through a client's signing packet is not
  // "Private" to the recipient who is signing it, and staff answer "what can
  // the client see?" from this tab.
  const signingDocuments = [
    {
      id: 'fee-1',
      filename: 'Fee agreement.pdf',
      content_type: 'application/pdf',
      document_category: 'agreement',
      file_size: 1024,
      portal_visible: false,
      signing_access: true,
      storage_backend: 'local',
      created_at: '2026-08-04T12:00:00Z',
    },
    {
      id: 'private-1',
      filename: 'Internal strategy.pdf',
      content_type: 'application/pdf',
      document_category: 'note',
      file_size: 1024,
      portal_visible: false,
      signing_access: false,
      storage_backend: 'local',
      created_at: '2026-08-04T12:00:00Z',
    },
    {
      id: 'shared-1',
      filename: 'Shared brief.pdf',
      content_type: 'application/pdf',
      document_category: 'pleading',
      file_size: 1024,
      portal_visible: true,
      signing_access: false,
      storage_backend: 'local',
      created_at: '2026-08-04T12:00:00Z',
    },
  ]

  beforeEach(() => {
    localStorage.clear()
    apiMocks.getMatterDocuments.mockResolvedValue({
      items: signingDocuments,
      total: signingDocuments.length,
    })
    apiMocks.getMatterCloudFiles.mockResolvedValue({ files: [] })
    apiMocks.getMatterCloudFolder.mockResolvedValue(null)
    apiMocks.getMatterDocumentFolders.mockResolvedValue({ items: [], total: 0, root_document_count: 3 })
    apiMocks.getDocumentTags.mockResolvedValue({ items: [], total: 0 })
    apiMocks.getMatterDocumentDownloadUrl.mockImplementation((matterId, documentId) => `/api/matters/${matterId}/documents/${documentId}/download`)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('marks a grant-readable document instead of calling it private', async () => {
    renderDocuments()
    await screen.findAllByText('Fee agreement.pdf')

    expect(screen.getAllByText('Available to signing client').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Shared with client').length).toBeGreaterThan(0)
    // The genuinely private document keeps the private label.
    expect(screen.getAllByText('Private').length).toBeGreaterThan(0)
  })
})

describe('MatterDocumentsTab prepared documents', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getMatterDocuments.mockResolvedValue({ items: documents, total: documents.length })
    apiMocks.getMatterCloudFiles.mockResolvedValue({ files: [] })
    apiMocks.getMatterCloudFolder.mockResolvedValue(null)
    apiMocks.getMatterDocumentFolders.mockResolvedValue({ items: folders, total: folders.length, root_document_count: 1 })
    apiMocks.getDocumentTags.mockResolvedValue({ items: tags, total: tags.length })
    apiMocks.getMatterDocumentDownloadUrl.mockImplementation((matterId, documentId) => `/api/matters/${matterId}/documents/${documentId}/download`)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    window.history.replaceState(null, '', '/')
  })

  it('opens the document named in the address once, then clears it from the address', async () => {
    renderDocuments(vi.fn(), { initialEntries: ['/matters/matter-1?tab=documents&document=pdf-1'] })
    await screen.findAllByText('Filed pleading.pdf')
    const preview = await screen.findByRole('region', { name: 'Document preview' })
    expect(preview).toHaveTextContent('Filed pleading.pdf')
    expect(preview).toHaveTextContent('17 of 19 fields filled, 12 verified when generated · from Pleading form v2')
    expect(within(preview).queryByRole('button', { name: /^Open Filed pleading.pdf in/ })).not.toBeInTheDocument()
    expect(screen.getByTestId('location-search')).toHaveTextContent('?tab=documents')
  })

  it('routes a prepared document to the Prepare page when the matter page provides the route', async () => {
    apiMocks.getMatterDocumentPrefill.mockResolvedValue({
      event_id: 'e', prepared_at: '2026-09-19T10:00:00Z', stale: false, ready: 1,
      templates: [{ template_id: 't-1', title: 'Fee agreement', status: 'ready', fields: 4, filled: 3, percent: 75, missing_required: 0, review: 0 }],
    })
    const onPrepareTemplate = vi.fn()
    render(
      <MemoryRouter initialEntries={['/matters/matter-1']}>
        <ToastProvider>
          <ConfirmProvider>
            <MatterDocumentsTab matterId="matter-1" onReviseDocument={vi.fn()} onPrepareTemplate={onPrepareTemplate} />
          </ConfirmProvider>
        </ToastProvider>
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Review and save' }))
    expect(onPrepareTemplate).toHaveBeenCalledWith('t-1', null)
    expect(screen.queryByRole('dialog', { name: 'Attach template' })).not.toBeInTheDocument()
  })
})

describe('MatterDocumentsTab Word and Google Docs editing', () => {
  const cloudDoc = {
    ...documents[0],
    id: 'cloud-1',
    filename: 'Engagement.docx',
    storage_backend: 'sharepoint',
    storage_provider: 'microsoft',
    provider_object_id: 'item-1',
    cloud_url: 'https://firm.sharepoint.com/display',
    document_status: 'draft',
  }

  beforeEach(() => {
    localStorage.clear()
    apiMocks.getMatterDocuments.mockResolvedValue({ items: [cloudDoc], total: 1 })
    apiMocks.getMatterCloudFiles.mockResolvedValue({ files: [] })
    apiMocks.getMatterCloudFolder.mockResolvedValue(null)
    apiMocks.getMatterDocumentFolders.mockResolvedValue({ items: [], total: 0, root_document_count: 1 })
    apiMocks.getDocumentTags.mockResolvedValue({ items: [], total: 0 })
    apiMocks.getMatterDocumentDownloadUrl.mockImplementation((matterId, documentId) => `/api/matters/${matterId}/documents/${documentId}/download`)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('labels SharePoint, keeps Download separate from Open, and shows the editor after opening', async () => {
    const popup = { location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(popup)
    apiMocks.startMatterDocumentCloudEdit.mockResolvedValue({
      document: { ...cloudDoc, external_edit_started_at: RECENT, external_edit_app: 'word_web', external_edit_started_by_name: 'Test Attorney' },
      links: { word_web: 'https://firm.sharepoint.com/edit' },
      app: 'word_web',
    })
    renderDocuments()
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Open in SharePoint').closest('a')).toHaveAttribute('href', '/api/matters/matter-1/documents/cloud-1/open')
    expect(within(table).getByRole('link', { name: 'Download Engagement.docx' })).toHaveAttribute('href', '/api/matters/matter-1/documents/cloud-1/download')
    fireEvent.click(within(table).getByRole('button', { name: 'Open Engagement.docx in Word' }))
    await waitFor(() => expect(popup.location.href).toBe('https://firm.sharepoint.com/edit'))
    expect(await within(table).findByText(/Being edited in Word by Test Attorney/)).toBeInTheDocument()
    expect(within(table).getByRole('button', { name: 'Bring back changes to Engagement.docx' })).toBeInTheDocument()
    window.open.mockRestore()
  })

  it('offers Open in Word on the preview a saved document lands on, and follows the edit marker', async () => {
    const popup = { location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(popup)
    apiMocks.startMatterDocumentCloudEdit.mockResolvedValue({
      document: { ...cloudDoc, external_edit_started_at: RECENT, external_edit_app: 'word_web' },
      links: { word_web: 'https://firm.sharepoint.com/edit' },
      app: 'word_web',
    })
    renderDocuments(vi.fn(), { initialEntries: ['/matters/matter-1?tab=documents&document=cloud-1'] })
    const preview = await screen.findByRole('region', { name: 'Document preview' })
    fireEvent.click(within(preview).getByRole('button', { name: 'Open Engagement.docx in Word' }))
    await waitFor(() => expect(popup.location.href).toBe('https://firm.sharepoint.com/edit'))
    expect(apiMocks.startMatterDocumentCloudEdit).toHaveBeenCalledWith('matter-1', 'cloud-1', 'word_web')
    expect(await within(preview).findByText(/Being edited in Word/)).toBeInTheDocument()
    window.open.mockRestore()
  })
})
