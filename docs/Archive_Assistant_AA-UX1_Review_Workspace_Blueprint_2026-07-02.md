# Archive Assistant AA-UX1 — Review Workspace Blueprint

**Owner:** Bonny Makaniankhondo  
**Project:** NAS System / Archive Assistant  
**Date:** 2026-07-02  
**Phase:** Design only  
**Status:** Draft for review before implementation  
**Scope:** Frontend UX architecture reset for Archive Assistant review flow

---

## 1. Problem Statement

Archive Assistant has outgrown the old frontend shape.

The backend is now behaving more like a real ingestion engine. It can read metadata, classify media, detect source fragments, reconstruct candidate groups, route mixed-media review, persist review actions, and protect against bad identity decisions. The frontend is still shaped like the earlier batch approval tool.

That mismatch is now creating operator friction.

Current symptoms:

- The user must scroll through too many raw candidate groups.
- Safe, review-needed, and blocked items appear too similarly.
- Old media-specific modals and newer universal ingestion panels coexist awkwardly.
- The UI exposes database/debug complexity before showing the operator decision.
- Source fragment folder names can still leak into old review contexts as fake identity.
- Different media types use different layout patterns, making the system harder to maintain.
- The user is forced to inspect technical structure instead of making clear media-library decisions.

The correct fix is not another modal cleanup. The correct fix is one consistent Review Workspace that can handle all media types through a shared shell.

---

## 2. Design Goal

Create one universal Review Workspace for Archive Assistant.

The workspace must support:

- Music albums
- Music discographies
- Singles / EPs / mixtapes
- Audiobooks
- Ebooks
- PDFs
- Comics
- Movies
- TV shows
- Anime specials / OAD / OVA / OAV
- Artwork
- Subtitles
- Sidecars
- Unknown files
- Source fragments such as Google Drive download chunks
- True mixed-media batches

The workspace should make Archive Assistant feel like a command center, not a spreadsheet or debugger.

The guiding principle:

```text
AA does the hard analysis.
The user only makes meaningful decisions.
The UI never shows raw complexity first.
```

---

## 3. Non-Goals

AA-UX1 must not implement backend behavior.

Do not add:

- Llama / AI metadata naming
- Beets
- MusicBrainz
- TMDB
- Open Library
- Jellyfin export
- BM Radio export
- Cleaner deletion
- Embedded tag writeback
- Automatic cleanup
- New final move behavior
- More separate modals

This is a design artifact only. Implementation begins after this blueprint is accepted.

---

## 4. Non-Negotiable Safety Rules

Archive Assistant must preserve the existing NAS safety model.

Rules:

- Archive Assistant does not delete production media.
- Archive Assistant does not overwrite final destinations.
- Archive Assistant does not mutate embedded tags.
- Archive Assistant does not move final media without approval.
- Metadata suggestions are candidates, not authority.
- Source folders are evidence, not final identity.
- Source chunk names such as `drive-download-...` must not become artist, author, title, album, or destination identity without explicit review.
- Photos stay outside Archive Assistant and go to Immich.
- Cleaner is the only future system that may eventually delete anything, and only after evidence, age thresholds, logs, and review.
- BM Radio is read-only and must not organize, delete, mutate, or clean media.

---

## 5. Current Codebase Shape Confirmed from ZIP

The latest uploaded ZIP was inspected for current frontend/backend structure before writing this design.

Current relevant frontend files include:

```text
frontend/src/components/BatchDetail.tsx
frontend/src/components/BatchRow.tsx
frontend/src/components/BatchTable.tsx
frontend/src/components/BulkApproveModal.tsx
frontend/src/components/CandidateMovePreviewPanel.tsx
frontend/src/components/DiscographyEditor.tsx
frontend/src/components/MediaReviewRouter.tsx
frontend/src/components/MetadataQualityPanel.tsx
frontend/src/components/ReviewIssuesPanel.tsx
frontend/src/components/UniversalIngestionPanel.tsx
frontend/src/components/AudiobookMetadataEditor.tsx
frontend/src/components/BookMetadataEditor.tsx
frontend/src/components/MovieMetadataEditor.tsx
frontend/src/components/TvMetadataEditor.tsx
```

Current relevant backend files include:

```text
backend/app/services/metadata_database.py
backend/app/services/metadata_quality_gate.py
backend/app/services/universal_ingestion.py
backend/app/services/universal_ingestion_review.py
backend/app/services/universal_review_routing.py
backend/app/services/candidate_move_plan_preview.py
```

This confirms the current problem: the backend already has universal ingestion/review concepts, while the frontend still has multiple specialized review components and modal-style paths.

AA-UX1 should define the new shell before implementation changes are made.

---

## 6. New Top-Level User Flow

Current old model:

```text
Batch table
  -> batch row expands
  -> old detail panel
  -> maybe music editor
  -> maybe discography editor
  -> maybe universal panel
  -> maybe metadata panel
  -> maybe move preview
```

New target model:

```text
Archive Assistant
  -> Batch List
  -> Universal Review Workspace
       -> Overview
       -> Candidate Groups
       -> Candidate Inspector
       -> Media-Specific Editor Panel
       -> Move Plan Preview
       -> Approve / Review Later / Block
```

The user should not need to know whether the backend used old scan logic, M4 metadata quality, universal ingestion, source fragments, or review routing. The Review Workspace should translate all of that into operator decisions.

---

## 7. Main Desktop Wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Archive Assistant                                                            │
│ Batch: drive-download-20260628T012539Z-3-007                                  │
│ Status: Needs Review  Confidence: 100%  Warnings: 7  Files: 94                │
│ Primary action: Review 3 merge recommendations                                │
├───────────────────┬────────────────────────────────────────┬─────────────────┤
│ Left Rail          │ Main Review Area                       │ Inspector Panel │
│                    │                                        │                 │
│ Overview           │ Batch Summary Cards                    │ Identity        │
│ Safe               │                                        │ Evidence        │
│ Needs Review       │ Safe Groups                            │ Move Plan       │
│ Blocked            │ ┌────────────────────────────────────┐ │ Warnings        │
│                    │ │ 500 Degreez                         │ │ Actions         │
│ Music              │ │ Lil Wayne | Music Album | 2002      │ │                 │
│ Audiobooks         │ │ Safe Group | 1 fragment | 1 member  │ │                 │
│ Books              │ │ Destination: Music/...              │ │                 │
│ Comics             │ └────────────────────────────────────┘ │                 │
│ Movies / TV        │                                        │                 │
│ Unknown            │ Needs Review                           │                 │
│                    │ ┌────────────────────────────────────┐ │                 │
│ Source Fragments   │ │ Unknown Album                       │ │                 │
│ Technical Details  │ │ Source identity risk detected       │ │                 │
│                    │ │ Action required: Review identity    │ │                 │
│                    │ └────────────────────────────────────┘ │                 │
└───────────────────┴────────────────────────────────────────┴─────────────────┘
```

Primary layout rules:

- Header gives the batch decision state.
- Left rail controls scope/filter.
- Center shows candidate cards grouped by decision state.
- Right panel shows deep detail only for the selected candidate.
- Technical data is hidden by default.
- Safe groups collapse by default when there are problems.
- Problem groups appear first when action is required.

---

## 8. Batch List Behavior

The existing batch table can remain, but its role changes.

The batch list should only answer:

- What batches exist?
- Which ones need attention?
- Which ones are approved?
- Which ones are blocked?
- How many files/items are involved?
- What is the worst decision state?

Target batch row fields:

```text
Checkbox
Batch name
Batch kind
Files/items
Media mix
Worst decision
Warnings
Confidence
Primary action
Move status
```

The main click target should open the Review Workspace.

Old inline expansion should become optional and eventually deprecated.

---

## 9. Review Workspace Overview

The first screen of a batch should not show every candidate immediately. It should show a control summary.

Example for a clean music batch:

```text
Clean Music Batch
94 music files
12 safe album groups
0 review required
0 blocked

Primary action:
Approve safe groups

Secondary actions:
View move plan
Show technical details
Review later
```

Example for a music-only fragmented batch:

```text
Music-Only Fragmented Batch
94 music files
6 source fragments
12 safe album groups
3 merge recommendations
0 mixed media
0 blocked conflicts

Primary action:
Review 3 merge recommendations

Secondary actions:
Approve safe groups
Open music editor after reconstruction
Show source fragments
Show technical details
```

Example for a true mixed-media batch:

```text
Mixed-Media Batch
40 music files
1 audiobook candidate
2 book/comic files
1 movie candidate
9 artwork/sidecar files

Required action:
Split media groups before final move.

Actions:
Review music group
Review audiobook group
Review book/comic group
Review movie/TV group
Approve split plan
Review sidecars
```

Example for source identity risk:

```text
Source Identity Risk
AA detected a source folder name being used as candidate identity.

Source value:
drive-download-20260628T012539Z-3-007

Required action:
Review identity before approval.
```

---

## 10. Left Rail Design

The left rail should be stable across every batch.

Recommended navigation:

```text
Overview

Decision States
- Safe
- Needs Review
- Blocked
- Review Later

Media Types
- Music
- Audiobooks
- Books
- Comics
- Movies / TV
- Artwork / Sidecars
- Unknown

Evidence
- Source Fragments
- Move Plan
- Technical Details
```

Rail badges should show counts:

```text
Safe 12
Needs Review 3
Blocked 0
Music 94
Audiobooks 1
Unknown 2
```

The rail should not expose database terms like `candidate_members` or `source_fragments` unless the user chooses technical details.

---

## 11. Candidate Group List

Candidate groups should be shown as cards, not raw rows.

Sort order:

1. Blocked conflicts
2. Required review
3. Merge/split recommendations
4. Unknowns
5. Safe groups
6. Excluded/review-later groups

Safe groups should be collapsed by default when any problem exists.

If everything is safe, safe groups can show in a compact approve-ready list.

---

## 12. Candidate Card Design

Default card fields:

```text
Media Type
Decision Status
Title
Primary Creator
Year / season / series if known
Confidence
File count
Source fragment count
Warnings count
Recommended action
Destination preview
```

Example safe music card:

```text
[MUSIC] [SAFE GROUP]
500 Degreez
Lil Wayne | 2002
1 file | 1 source fragment | High confidence
Destination: Music/Discographies/Lil Wayne/Albums/2002 - 500 Degreez
Recommended: Approve
```

Example merge review card:

```text
[MUSIC] [MERGE RECOMMENDED]
Unknown Album
Unknown Artist | Unknown Year
14 files | 3 source fragments | High confidence
Warning: Source fragments may belong to one album group
Recommended: Review merge
```

Example source identity risk card:

```text
[MUSIC] [REVIEW REQUIRED]
drive-download-20260628T012539Z-3-007
Source folder name detected as identity
94 files | 6 source fragments
Recommended: Review identity before approval
```

Candidate card actions:

```text
Approve
Edit
Change Type
Split
Merge
Exclude
Review Later
Block
```

Rules:

- `Approve` is hidden or disabled if source identity risk exists.
- `Approve` is hidden or disabled if required fields are unknown.
- `Block` does not delete files.
- `Exclude` excludes from move plan only; it does not delete files.
- Raw members are not shown by default.
- Evidence opens in the right panel.
- Technical details open in a drawer.

---

## 13. Candidate Inspector Panel

The right panel is the main decision workspace.

Tabs or sections:

```text
Identity
Evidence
Move Plan
Warnings
Actions
```

### 13.1 Identity Section

Shows normalized editable identity.

Default fields:

```text
Media type
Title
Creator / artist / author
Year
Series / album / season if relevant
Confidence
Review state
```

The panel should clearly separate:

```text
Current identity
Suggested identity
Source evidence
User override
```

### 13.2 Evidence Section

Shows why AA believes this candidate is what it is.

Evidence types:

```text
Embedded tags
Filename clues
Folder clues
Source fragment clues
Track/chapter numbering
Duration/hash clues
Sidecar/artwork relationships
Prior user overrides
Metadata quality gate flags
```

Evidence should be summarized first, then expandable.

### 13.3 Move Plan Section

Shows destination before approval.

Fields:

```text
Destination root
Final folder path
File count to move
Sidecars/artwork included
Manifest target
Conflicts
Blocked reason if any
```

Example:

```text
Destination preview:
Music/Discographies/Lil Wayne/Albums/2002 - 500 Degreez/

Will move:
1 audio file
1 cover image
1 metadata manifest

Will not move:
0 files

Conflicts:
None
```

### 13.4 Warnings Section

Warnings should be human-language, not raw backend labels.

Examples:

```text
Source folder name detected as identity.
Album year missing.
Embedded genre is unmapped.
Multiple source fragments may belong together.
Subtitle file found without matching movie file.
Audiobook chapter numbers are incomplete.
```

### 13.5 Actions Section

Action buttons should be clear and ordered by safety.

Recommended order:

```text
Approve
Save edits
Review later
Change media type
Split
Merge
Exclude from move
Block
Show technical details
```

No delete button.

---

## 14. Media-Specific Editor Panel Rules

The Review Workspace has one shell. Media types only change the fields inside the inspector.

### 14.1 Music Album / Discography Candidate

Fields:

```text
Artist
Album artist
Album title
Year
Release type: album / single / EP / mixtape / compilation / live / remix / demo
Genre
Genre family
Track count
Disc count
Destination preview
```

Rules:

- Artist cannot equal a source fragment pattern unless user confirms override.
- Album cannot equal a source fragment pattern unless user confirms override.
- Discography destination must use artist identity, not source folder identity.
- Unknown genre can be saved but should remain review-recommended.

### 14.2 Audiobook Candidate

Fields:

```text
Author
Title
Series
Series index
Narrator
Year
Part/chapter count
Disc count
Destination preview
```

Rules:

- Audiobook title cannot be inferred only from folder chunk names.
- Chapter-only generic names should not block if folder/book identity is strong.
- Multi-part audiobooks should show ordering evidence.

### 14.3 Book / Ebook Candidate

Fields:

```text
Author
Title
Series
Series index
Format: EPUB / PDF / MOBI / AZW3
Year
ISBN if available
Destination preview
```

Rules:

- Generic PDF garbage titles should require review.
- Folder clues may suggest collection, but not final title by themselves.

### 14.4 Comic Candidate

Fields:

```text
Series
Volume/title
Issue number or range
Publisher optional
Format: CBZ / CBR / PDF
Year optional
Destination preview
```

Rules:

- Comic series and issue identity should be visibly separated.
- Unknown publisher should not block.

### 14.5 Movie Candidate

Fields:

```text
Title
Year
Edition/version
Quality/source optional
Subtitles attached
Artwork attached
Destination preview
```

Rules:

- Title/year should be required before approval.
- Quality/source labels should not become movie title.

### 14.6 TV Candidate

Fields:

```text
Show title
Season
Episode range
Specials/OAD/OVA/OAV handling
Subtitles attached
Artwork attached
Destination preview
```

Rules:

- Specials should show explicit destination preview.
- Anime OAD/OVA/OAV should remain visible as special handling evidence.
- Episode confidence should be shown as summary, not every file by default.

### 14.7 Unknown Candidate

Fields:

```text
Detected file types
Best guess
Reason unclear
Choose media type
Review later
Block
Send to quarantine review
```

Rules:

- Unknown does not mean trash.
- Unknown candidates should not be moved to final library until classified.
- Quarantine is for review, not deletion.

---

## 15. Bulk Action Bar

Bulk actions appear only when meaningful.

Allowed actions:

```text
Approve all safe groups
Approve selected safe groups
Review only warnings
Review only blocked
Collapse safe groups
Expand safe groups
Show move plan
Show technical details
Mark selected review later
```

Never show:

```text
Delete
Clean
Remove source
Permanently discard
```

If any selected candidate has source identity risk, the bulk approve action must skip it and show:

```text
Some groups require identity review before approval.
```

---

## 16. Source Identity Guard

This is a central AA-UX1 rule.

Source-like names include patterns such as:

```text
drive-download-20260628T012539Z-3-007
part-001
chunk-003
googledrive-004
archive-download-001
download-zip-001
```

If any candidate uses this value as title, creator, artist, author, album, show, movie, or destination identity, the UI must show:

```text
Source folder name detected as identity.
Review required before approval.
```

Required UI behavior:

- Candidate state becomes `Review Required`.
- Primary action becomes `Review identity`.
- `Approve` is disabled until corrected or explicitly confirmed.
- Destination preview is marked unsafe.
- Evidence panel shows where the source value came from.
- If embedded tags contain real names, those should be promoted as suggested identity.

Example:

```text
Unsafe candidate identity:
Artist: drive-download-20260628T012539Z-3-007
Album: Discography

Detected evidence:
Embedded artist: Lil Wayne
Embedded album: Tha Carter II
Embedded artist: The Weeknd
Embedded album: Starboy

Required action:
Split or confirm real candidate identities before move.
```

---

## 17. Move Plan Preview

Move preview must exist before final approval.

The preview should show:

```text
Candidate identity
Current source fragments
Final destination
Files included
Files excluded
Sidecars/artwork handling
Manifest path
Conflicts
Warnings
```

Move plan display should be grouped by destination, not source folder.

Bad preview:

```text
Music/Discographies/drive-download-20260628T012539Z-3-007
```

Good preview:

```text
Music/Discographies/Lil Wayne/Albums/2005 - Tha Carter II
Music/Discographies/The Weeknd/Albums/2016 - Starboy
Audiobooks/Library/Drew Karpyshyn/Star Wars The Old Republic - Revan
```

If the destination uses source chunk identity, it must be blocked from approval.

---

## 18. Technical Details Drawer

Technical data should still exist, but not be the main interface.

Technical details drawer may include:

```text
Raw API response
Candidate ID
Source fragment ID
Member file list
Raw metadata tags
Quality decision object
Routing decision object
Review action history
Move preview JSON
```

Rules:

- Drawer is closed by default.
- Drawer is accessible from candidate and batch level.
- Drawer copy/export remains available for debugging.
- Drawer must not drive the main workflow.

---

## 19. Responsive / Tablet / Mobile Considerations

Archive Assistant is primarily desktop-first, but the UI should not break on smaller screens.

### Tablet

Tablet layout:

```text
Header
Left rail collapses to tabs
Candidate list full width
Inspector slides in as right drawer
```

### Mobile

Mobile layout:

```text
Header
Batch summary
Segmented filters
Candidate cards
Inspector opens full-screen
Actions sticky at bottom
```

Mobile is for checking and light review, not bulk deep correction.

Do not optimize for tiny phone workflows before desktop review is stable.

---

## 20. Component Map

Target components:

```text
ReviewWorkspace
BatchSummaryHeader
ReviewLeftRail
ReviewOverviewPanel
CandidateGroupList
CandidateCard
CandidateInspectorPanel
MovePlanPreview
EvidencePanel
WarningPanel
BulkActionBar
TechnicalDetailsDrawer
MediaSpecificEditorPanel
```

### 20.1 ReviewWorkspace

Owns the full review page layout.

Responsibilities:

```text
Load batch review summary
Load universal ingestion data
Load metadata quality data
Load review routing data
Track selected candidate
Track active left-rail filter
Coordinate candidate actions
```

### 20.2 BatchSummaryHeader

Shows batch-level status.

Fields:

```text
Batch name
Detected batch kind
File count
Candidate count
Media mix
Worst decision
Warnings count
Confidence
Primary action
```

### 20.3 ReviewLeftRail

Provides navigation and filtering.

Fields:

```text
Overview
Decision filters
Media filters
Evidence filters
Technical details
```

### 20.4 CandidateGroupList

Displays candidate cards by current filter.

Responsibilities:

```text
Sort candidates by decision severity
Collapse safe groups when needed
Group by decision or media type
Handle selection state
```

### 20.5 CandidateCard

Shows decision-level data for one candidate.

Responsibilities:

```text
Display identity summary
Display confidence
Display warning count
Display recommended action
Display destination preview
Expose safe actions
```

### 20.6 CandidateInspectorPanel

Shows selected candidate details and editing tools.

Responsibilities:

```text
Identity editing
Evidence review
Move preview
Warnings
Candidate actions
```

### 20.7 MediaSpecificEditorPanel

Renders fields based on candidate media type.

Responsibilities:

```text
Music fields
Audiobook fields
Book fields
Comic fields
Movie fields
TV fields
Unknown fields
Validation messages
```

### 20.8 MovePlanPreview

Shows destination preview before approval.

Responsibilities:

```text
Display destination path
Flag source identity risk
Show included/excluded files
Show sidecar handling
Show conflicts
```

### 20.9 TechnicalDetailsDrawer

Contains raw data and debug views.

Responsibilities:

```text
Show raw API payloads
Show member files
Show backend decisions
Allow copy/export
Stay closed by default
```

---

## 21. Data Model Expected by Frontend

The frontend should normalize backend responses into a view model.

Suggested UI view model:

```ts
ReviewCandidateViewModel = {
  candidateId: string
  mediaType: 'music' | 'audiobook' | 'book' | 'comic' | 'movie' | 'tv' | 'artwork' | 'sidecar' | 'unknown'
  decisionState: 'safe' | 'review_recommended' | 'review_required' | 'blocked' | 'excluded' | 'review_later'
  recommendedAction: string
  title: string | null
  creator: string | null
  year: string | null
  confidenceLabel: 'high' | 'medium' | 'low'
  fileCount: number
  sourceFragmentCount: number
  warningCount: number
  warnings: string[]
  destinationPreview: string | null
  hasSourceIdentityRisk: boolean
  evidenceSummary: EvidenceSummary
  mediaSpecificFields: Record<string, unknown>
}
```

This can be created in frontend mapping code without requiring a backend rewrite.

---

## 22. Migration Plan from Old UI

Do not remove the old modals immediately. Replace entry points gradually.

### AA-UX2 — Build ReviewWorkspace Shell

Create the empty layout shell.

Includes:

```text
ReviewWorkspace
BatchSummaryHeader
ReviewLeftRail
Three-column layout
Placeholder candidate list
Placeholder inspector
```

No behavior change yet.

### AA-UX3 — Candidate Cards + Inspector

Use current universal ingestion and metadata quality data to populate candidate cards.

Includes:

```text
CandidateGroupList
CandidateCard
CandidateInspectorPanel
EvidencePanel
WarningPanel
```

Old modals still exist.

### AA-UX4 — Move Plan Preview

Move `CandidateMovePreviewPanel` behavior into the inspector.

Includes:

```text
MovePlanPreview
Destination risk flags
Source identity guard display
```

### AA-UX5 — Replace Discography Modal Entry Point

The discography flow should open ReviewWorkspace first.

Includes:

```text
Music-only fragmented batch summary
Safe group approve flow
Merge recommendation review
Discography editor as embedded media-specific panel
```

Old `DiscographyEditor` may remain internally, but should not be the main modal entry point.

### AA-UX6 — Media-Specific Editors

Move existing editors into the shared inspector pattern.

Targets:

```text
MetadataEditor.tsx
DiscographyEditor.tsx
AudiobookMetadataEditor.tsx
BookMetadataEditor.tsx
MovieMetadataEditor.tsx
TvMetadataEditor.tsx
BookCollectionEditor.tsx
MovieCollectionEditor.tsx
```

End state:

```text
One Review Workspace shell.
Media-specific fields inside the inspector.
Old standalone modal paths deprecated.
```

---

## 23. Acceptance Criteria

AA-UX1 is accepted when this design clearly defines:

- One universal Review Workspace shell.
- No new inconsistent modal system.
- Safe groups collapsed by default.
- Problem groups surfaced first.
- Technical details hidden by default.
- Source folders treated as evidence only.
- Source identity risk blocked from normal approval.
- Media-specific fields inside one common inspector layout.
- Clear path for music, audiobooks, books, comics, movies, TV, unknowns, sidecars, and artwork.
- Clear migration path from old discography and metadata modals.
- No destructive actions.
- No AI dependency.
- No backend behavior changes required for the blueprint.

Implementation does not begin until Bonny approves the design direction.

---

## 24. Final Design Decision

The frontend reset should proceed with this architecture:

```text
Batch List
  -> Review Workspace
       -> Overview
       -> Candidate Cards
       -> Inspector Panel
       -> Move Plan Preview
       -> Approval Actions
```

Do not continue expanding the old modal system.

Do not continue AA-M4D.5 until the Review Workspace shell exists.

Archive Assistant is becoming the NAS digital-library ingestion authority. The frontend must now become an operator workspace that turns backend analysis into simple, safe decisions.
