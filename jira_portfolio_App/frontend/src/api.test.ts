import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

describe('configuration API client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('encodes field searches and sends the authenticated session header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({items: [], next_cursor: null, total_count: 0, sync_version: 1}),
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', {getItem: () => 'test-session', setItem: vi.fn(), removeItem: vi.fn()})

    await api.fields('risk & confidence')

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('search=risk%20%26%20confidence'),
      expect.objectContaining({headers: expect.objectContaining({Authorization: 'Bearer test-session'})}),
    )
  })
})
