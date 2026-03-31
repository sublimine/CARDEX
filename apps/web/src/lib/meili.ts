/**
 * MeiliSearch client — used from Server Components for instant search.
 * The public search key (read-only) is exposed to the browser for
 * client-side instant search via the MeiliSearch JS SDK.
 */
import { MeiliSearch } from 'meilisearch'

// Server-side client (master key — never sent to browser)
export const meiliServer = new MeiliSearch({
  host: process.env.MEILI_URL ?? 'http://localhost:7700',
  apiKey: process.env.MEILI_MASTER_KEY ?? '',
})

// Public config for client-side instant search
export const MEILI_PUBLIC_CONFIG = {
  host: process.env.NEXT_PUBLIC_MEILI_URL ?? 'http://localhost:7700',
  apiKey: process.env.NEXT_PUBLIC_MEILI_SEARCH_KEY ?? '',
  indexName: 'vehicles',
}
