import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getMatterCloudFolder, provisionMatterCloudFolder, syncMatterCloudFolder } from '../api'
import { CloudFolderCard } from './MatterDocumentsTab'

vi.mock('../api', async (importOriginal) => ({
  ...await importOriginal(),
  getMatterCloudFolder: vi.fn(),
  provisionMatterCloudFolder: vi.fn(),
  syncMatterCloudFolder: vi.fn(),
}))

beforeEach(() => vi.resetAllMocks())
afterEach(cleanup)

describe('CloudFolderCard setup recovery', () => {
  it('shows a retryable status failure without starting folder setup', async () => {
    getMatterCloudFolder.mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ status: 'not_provisioned', providers: {} })
    render(<CloudFolderCard matterId="matter-status" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Document folder status could not be loaded')
    fireEvent.click(screen.getByRole('button', { name: 'Retry folder status' }))
    expect(await screen.findByRole('button', { name: 'Set up folders' })).toBeEnabled()
    expect(getMatterCloudFolder).toHaveBeenCalledTimes(2)
    expect(provisionMatterCloudFolder).not.toHaveBeenCalled()
  })

  it('offers one setup action, preserves a failed setup, and retries explicitly', async () => {
    getMatterCloudFolder.mockResolvedValue({ status: 'not_provisioned', providers: {} })
    provisionMatterCloudFolder
      .mockRejectedValueOnce({ response: { data: { detail: 'Folder access was denied.' } } })
      .mockResolvedValueOnce({ status: 'provisioned', providers: { onedrive: { matter_folder_id: 'folder' } } })
    const onFolderChange = vi.fn()
    render(<CloudFolderCard matterId="matter-a" onFolderChange={onFolderChange} />)
    const setup = await screen.findByRole('button', { name: 'Set up folders' })
    expect(screen.queryByRole('button', { name: /Provision|Sync folder/ })).toBeNull()
    fireEvent.click(setup)
    expect(await screen.findByText('Folder access was denied.')).toBeInTheDocument()
    expect(provisionMatterCloudFolder).toHaveBeenCalledTimes(1)
    expect(onFolderChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Set up folders' }))
    expect(await screen.findByText('Cloud folder set up successfully.')).toBeInTheDocument()
    expect(provisionMatterCloudFolder).toHaveBeenCalledTimes(2)
    expect(provisionMatterCloudFolder).toHaveBeenLastCalledWith('matter-a')
    expect(syncMatterCloudFolder).not.toHaveBeenCalled()
    expect(onFolderChange).toHaveBeenCalledWith({ onedrive: { matter_folder_id: 'folder' } })
  })

  it('keeps setup available when a different provider already has a folder', async () => {
    getMatterCloudFolder.mockResolvedValue({ status: 'provisioned', providers: { google_drive: { matter_folder_id: 'existing-google-folder' } } })
    let finishSetup
    provisionMatterCloudFolder.mockImplementation(() => new Promise(resolve => { finishSetup = resolve }))
    render(<CloudFolderCard matterId="matter-b" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Set up folders' }))
    expect(screen.getByRole('button', { name: 'Setting up…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Sync folder' })).toBeDisabled()
    expect(provisionMatterCloudFolder).toHaveBeenCalledTimes(1)
    finishSetup({ status: 'provisioned', providers: { google_drive: { matter_folder_id: 'existing-google-folder' }, onedrive: { matter_folder_id: 'new-onedrive-folder' } } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Set up folders' })).toBeEnabled())
    expect(syncMatterCloudFolder).not.toHaveBeenCalled()
  })
})
