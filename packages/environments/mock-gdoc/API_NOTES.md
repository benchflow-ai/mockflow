# Mock Google Docs API Notes

## Ground Truth

- **Official REST API spec (Docs)**: https://developers.google.com/document/api/reference/rest
- **Official REST API spec (Drive)**: https://developers.google.com/drive/api/reference/rest/v3
- **batchUpdate Request types**: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request
- **Discovery Documents** (machine-readable schemas):
  - Docs: https://docs.googleapis.com/$discovery/rest?version=v1
  - Drive: https://www.googleapis.com/discovery/v1/apis/drive/v3/rest
- **Per-resource specs**:
  - Documents: https://developers.google.com/document/api/reference/rest/v1/documents
  - Drive Files: https://developers.google.com/drive/api/reference/rest/v3/files
- **Fixture source**: captured from a private Google Docs/Drive test account.
- **Auth script**: `scripts/auth.py` (OAuth, saves `scripts/token.json`)
- **Fixture capture**: `scripts/capture_fixtures.py` → `tests/fixtures/real_gdocs/`
- **Endpoint spec**: `tests/fixtures/gdocs_api_spec.json`
- **Coverage map**: `tests/fixtures/mock_coverage.json`

---

## batchUpdate Coverage

Our mock implements **37 of the 40** request types from the real Google Docs API
`batchUpdate` endpoint, plus 3 mock-only helpers for seed data. The 3 real request
types not yet implemented are `insertDate`, `insertRichLink`, and
`updateNamedStyle` (absent from the `_HANDLERS` dispatch table in
`mock_gdoc/api/documents.py`).

### Text editing
`insertText`, `deleteContentRange`, `replaceAllText`

### Character formatting
`updateTextStyle` — bold, italic, underline, strikethrough, smallCaps, fontSize, foregroundColor, backgroundColor, link, baselineOffset, weightedFontFamily

### Paragraph formatting
`updateParagraphStyle`, `createParagraphBullets`, `deleteParagraphBullets`

### Tables
`insertTable`, `insertTableRow`, `insertTableColumn`, `deleteTableRow`, `deleteTableColumn`, `mergeTableCells`, `unmergeTableCells`, `updateTableCellStyle`, `updateTableRowStyle`, `updateTableColumnProperties`, `pinTableHeaderRows`

### Images and media
`insertInlineImage`, `replaceImage`, `deletePositionedObject`, `insertPerson`

### Document structure/layout
`insertPageBreak`, `insertSectionBreak`, `updateSectionStyle`, `updateDocumentStyle`, `createHeader`, `createFooter`, `deleteHeader`, `deleteFooter`, `createFootnote`

### Named ranges
`createNamedRange`, `deleteNamedRange`, `replaceNamedRangeContent`

### Tabs
`addDocumentTab`, `deleteTab`, `updateDocumentTabProperties`

### Seed-only helpers (not exposed via API)
`insertEquation`, `insertTableOfContents`, `insertPositionedObject` — these are read-only in the real API (created via UI). The underlying `body_ops` functions exist for seeding rich test documents, but they are not registered in the `_HANDLERS` dispatch table and cannot be called via batchUpdate.

---

## Architecture

### Body manipulation engine (`body_ops.py`)

All document mutations are handled by a pure-function engine that operates directly on the body JSON tree. Key design:

- **Index-aware**: Operations work with the Google Docs 1-based index model, navigating the structural element tree to find the right paragraph/table/cell.
- **No flatten-rebuild**: Unlike the original implementation that flattened body to plain text and rebuilt, the engine preserves all rich content (styles, tables, images, etc.) across mutations.
- **Reindexing**: After every mutation, `reindex_body()` walks the tree and recomputes all `startIndex`/`endIndex` values for consistency.
- **Text run splitting**: Style operations split text runs at boundaries, apply styles to the affected range, then coalesce adjacent runs with identical styles.

### Document model

The `Document` SQLAlchemy model stores the body and all top-level maps as JSON columns:

| Column | Maps to API field |
|--------|-------------------|
| `body_json` | `body` |
| `document_style_json` | `documentStyle` |
| `named_styles_json` | `namedStyles` |
| `lists_json` | `lists` |
| `inline_objects_json` | `inlineObjects` |
| `headers_json` | `headers` |
| `footers_json` | `footers` |
| `footnotes_json` | `footnotes` |
| `named_ranges_json` | `namedRanges` |
| `positioned_objects_json` | `positionedObjects` |
| `tabs_json` | `tabs` |

Empty maps (`{}`) are omitted from API responses, matching real Google API behavior.

### Default styles

New documents are created with realistic `documentStyle` and `namedStyles` matching the real Google Docs API (captured from golden fixtures). This includes:
- Page size (612x792 PT = US Letter), 72 PT margins
- Named styles: NORMAL_TEXT (Arial 11pt), HEADING_1-6, TITLE, SUBTITLE with correct font sizes, colors, and spacing

---

## API Quirks (append-only, dated)

- **2026-03-19: Google Docs API has no list method.** There is no `documents.list`. Listing documents is done via Google Drive API v3 `files.list` with `mimeType = 'application/vnd.google-apps.document'`. This is why our mock includes both `/v1/documents` (Docs) and `/drive/v3/files` (Drive) endpoints.

- **2026-03-19: `documents.create` returns the full Document resource.** Unlike Gmail mutations which return minimal responses, Docs `create` returns the complete document including `body`, `documentStyle`, `namedStyles`, etc.

- **2026-03-19: `batchUpdate` returns `{documentId, replies[], writeControl}`.**  Each reply corresponds to one request. Most replies are empty `{}`. `replaceAllText` returns `{replaceAllText: {occurrencesChanged: N}}`. `writeControl` contains `requiredRevisionId`.

- **2026-03-19: Document body uses 1-based indexing.** The first character is at index 1, not 0. Every document body has an implicit `\n` at index 1 even when empty. `insertText` at `location.index: 1` inserts at the very beginning.

- **2026-03-19: Document body starts with a `sectionBreak`.** The first element in `body.content` is always a `sectionBreak` (with `sectionStyle`), not a paragraph. Our mock correctly reproduces this.

- **2026-03-19: Drive `files.list` returns `{}` for empty results.** When no files match the query, the real API returns `{"kind": "drive#fileList", "incompleteSearch": false, "files": []}` — unlike Gmail which omits the array key entirely.

- **2026-03-19: Drive query syntax is its own DSL.** Supports `name contains 'X'`, `name = 'X'`, `mimeType = 'X'`, joined by `and`. Does NOT support `or`, parentheses, or `not` at the query level.

- **2026-03-19: `suggestionsViewMode` defaults to `DEFAULT_FOR_CURRENT_ACCESS`.** Other valid values: `SUGGESTIONS_INLINE`, `PREVIEW_SUGGESTIONS_ACCEPTED`, `PREVIEW_WITHOUT_SUGGESTIONS`.

- **2026-03-19: `documents.create` returns `tabs` field.** Google added tab support to Docs. Our mock supports tab operations (`addDocumentTab`, `deleteTab`, `updateDocumentTabProperties`) but does not return `tabs` in the default document response (tabs are stored separately).

- **2026-03-19: Drive `owners[]` has rich user objects.** Real: `{kind, displayName, me, permissionId, photoLink, emailAddress}`. Our mock returns a simplified version.

- **2026-03-24: Real Comments API lives in Drive, not Docs.** Google comments are served by Drive API v2 (`/drive/v2/files/{fileId}/comments`). Our mock serves them under the Docs namespace at `/v1/documents/{documentId}/comments` to keep agents on a single service.

- **2026-03-24: Real API resolves comments via PATCH, not a dedicated endpoint.** Real Drive API sets `resolved: true/false` by patching the comment resource. Our mock uses dedicated `POST .../resolve` and `POST .../reopen` endpoints for clarity.

- **2026-03-24: Real Permissions API lives in Drive, not Docs.** Google permissions are served by Drive API v3 (`/drive/v3/files/{fileId}/permissions`). Our mock serves them at `/v1/documents/{documentId}/permissions`.

- **2026-03-24: Owner permission is synthetic in our mock.** Real Drive stores the owner as a persisted permission record. Our mock synthesizes it at list time from `document.user_id`, so it has no `permissionId` and cannot be patched or deleted.

- **2026-03-24: Delete comment/permission returns `{"status": "ok"}`.** Real Google API returns an empty body with 204 No Content.

- **2026-03-24: No pagination on comments or permissions lists.** Real API supports `pageToken`/`nextPageToken`. Our mock returns all results in a single response.

---

## Intentionally Skipped

| Feature | Reason |
|---------|--------|
| ~~Comments API (`/v1/documents/{id}/comments`)~~ | ~~Not needed for current agent tasks (read/write focus)~~ → Implemented in `5dd80a2` |
| Suggested edits / suggestion mode | Complex state machine with shadow elements on every node |
| `includeTabsContent` parameter | Changes response structure significantly; tab content is stored separately |
| `fields` query parameter (partial response) | Not needed for agent testing |
| Real pagination (pageToken) | Mock returns all results; pageSize is respected but no real cursor |
| Drive: file permissions, sharing, trash | Only file listing/metadata needed for doc discovery |
| Drive: upload/download media | Documents are Docs-native, not file blobs |

---

## Key Design Choices

- **Stateful mock, not replay**: Full CRUD with persistent SQLite, enabling multi-step agent workflows
- **Dual API surface**: Docs API v1 (`/v1/documents`) for CRUD + Drive API v3 (`/drive/v3/files`) for listing, matching real Google API architecture
- **Index-aware body engine**: Pure-function `body_ops.py` module preserves rich content (styles, tables, images, equations) across all mutations — no more flatten-to-text
- **37 of 40 batchUpdate types**: Near-complete coverage of the Google Docs API request union (missing `insertDate`, `insertRichLink`, `updateNamedStyle`)
- **Multi-user**: Resolved via `X-Mock-Gdoc-User` header
- **Task-specific seeding**: `seed --scenario task:<name>` loads needle documents from `tasks/<name>/data/needles.py` plus filler docs
- **API parity**: Only real Google Docs API endpoints are exposed. Listing is done via Drive (`/drive/v3/files`), and deletion via Drive `files.delete`, matching the real API surface
- **Comments/permissions under Docs namespace**: Real Google serves these via Drive API, but our mock collocates them under `/v1/documents/` so agents interact with a single service. Trades path fidelity for simplicity.
- **Permission model**: Four roles (owner, writer, commenter, reader). Only the document owner can manage permissions. Owner is synthetic (not a stored permission record).

---

## Open Questions

- ~~**Comments API**: May be needed for future tasks involving document review workflows. Currently no endpoints implemented. Add when a task needs it.~~ → Implemented in `5dd80a2` with full CRUD, resolve/reopen, and threaded replies.
- **Revision history**: `DocumentRevision` model exists but no read API is exposed. Real Docs API supports `documents.get` with specific `revisionId`. Low priority.
- **Suggestions mode**: Would require `suggestedTextStyleChanges`, `suggestedInsertionIds`, `suggestedDeletionIds` on every element. Very complex. Defer unless a specific task requires it.
- **Error response fixtures**: 404 and 400 error fixtures are captured from the real API. Conformance tests validate Google-standard error format. More error cases (quota exceeded, permission denied) could be added.

---

## Test Coverage

| Test file | Count | What it covers |
|-----------|-------|----------------|
| `test_api.py` | 14 | Basic CRUD, admin endpoints, state dump/diff/reset |
| `test_conformance.py` | ~~16~~ 10 | Shape comparison against real API golden fixtures |
| `test_body_ops.py` | 39 | Index arithmetic, text/style/table/list operations in isolation |
| `test_rich_content.py` | 29 | All batchUpdate types through the API (integration) |
| `test_documents_unit.py` | 3 | Document model unit tests |
| `test_seed.py` | 1 | Seed scenario generation |
| `test_tasks.py` | 2 | Task registry and evaluation |
| `test_web_routes.py` | 7 | Web UI route responses |
| **Total** | **105** | |
