import { defineConfig } from '@hey-api/openapi-ts'

// The I4 typed client: generated from the pinned schema snapshot (openapi.json — exported by
// `python -m backend.tools.export_openapi`), committed, and diff-gated in CI (I7) so the FE↔BE
// contract cannot drift silently. Regenerate with `npm run gen:api` after any backend change.
export default defineConfig({
  input: 'openapi.json',
  output: 'src/api/generated',
})
