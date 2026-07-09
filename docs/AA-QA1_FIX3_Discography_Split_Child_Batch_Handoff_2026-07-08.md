# AA-QA1 / FIX3 Discography Split and Child Batch Handoff

Date: 2026-07-08
Project: NAS / Archive Assistant
Area: Parent review containers, discography split, child batch review

## Purpose

This note records what we changed, what we tested, what we were trying to solve, and what still needs follow-up around discography parent batches and created child batches.

The main product problem was:

```text
A parent discography/reconstructed batch should not behave like one normal album.
After the user edits and splits the discography, the created child batches must be visible and reviewable as normal media batches.
The parent should remain a container/history object, not the thing that gets moved to the final library.
```

## Original Problems Observed

### Parent looked like a normal media object

After approving or splitting candidates, the dashboard could still show the parent batch as if it were one album or one final media object. This was misleading because the parent represented a source discography folder, not a final album.

Example:

```text
drive-download-20260628T012539Z-3-010
3 release discography
63 tracks
```

The parent was a review container, but the UI could still make it look move-ready.

### Normal Review Workspace was empty for discography parents

Opening Review Workspace on a split-complete discography parent showed:

```text
No candidates match this filter.
Select a candidate to review.
```

That happened because the parent no longer had active universal candidate groups. The useful review targets were the child batches, not the parent.

### Edited discography releases needed real child batches

The user edited releases in the discography modal and expected those releases to become separate child batches.

The needed behavior was:

```text
Edit discography releases
Save and create child batches
See created child albums
Review child albums
Approve child albums
Move approved child albums later
```

The parent itself should not move to the final Music library.

### Some child batches were created but hard to act on

The created child batches appeared in the parent detail panel, but there was not yet a direct Review/Approve action in that panel. The user could see rows like:

```text
#56 Kanye West - Yeezus
pending review
3 tracks
3 files
Music/Library/FLAC/Kanye West/2013 - Yeezus
```

But the next step was not obvious from inside the parent detail view.

## Backend Work Completed

### Discography release split endpoint

Added a parent-level discography split path:

```text
POST /api/batches/{batch_id}/split-discography-releases
```

Implemented through:

```text
backend/app/services/batch_split.py
execute_split_discography_releases(...)
```

The endpoint creates child batches from edited discography release rows.

Important behavior:

```text
Does not move files to final library.
Does not delete files.
Does not mutate embedded tags.
Reassigns scoped files from parent to child batches.
Creates child batches as normal pending_review media batches.
Keeps source parent evidence.
Is intended to be idempotent so repeated calls do not duplicate children.
```

### Child batch listing endpoint

Added:

```text
GET /api/batches/{batch_id}/child-batches
```

This returns child batches where metadata links them back to the parent:

```text
metadata_json.split_from_batch_id
metadata_json.source_parent_batch_id
```

The endpoint returns normal dashboard-style batch summaries so the frontend can display child rows consistently.

### Parent materialization summary fixes

The parent summary logic now distinguishes:

```text
review_in_progress
candidates_approved_waiting_materialization
parent_partially_materialized
split_complete
```

This matters because a parent can have some children created while still retaining leftover files or unresolved releases.

### Split-complete parent truthfulness

For split-complete parents, dashboard display now uses child batch truth instead of candidate truth.

Expected display:

```text
17 child batches created, split complete
17 child batches
```

Not:

```text
17 candidates
one album title
move-ready parent
```

### File count correction for child summaries

Batch summaries can use actual attached `IngestFile` rows so child rows do not depend only on stale metadata counters.

This helps created child batches show real counts like:

```text
3 tracks
3 files
22 tracks
22 files
```

## Frontend Work Completed

### Discography editor action

Added a discography editor action:

```text
Save and create child batches
```

This saves edited discography release corrections, then calls the split-discography endpoint.

The goal was to let the user correct artist, album, year, genre, and release rows before child creation.

### Created child batches panel

Added a panel in the parent batch detail view:

```text
Created child batches
These are the extracted review batches. Approve and move these rows, not the parent container.
```

The panel lists:

```text
child batch id
artist
album
status
track/item count
file count
suggested destination
```

Observed example from batch 20:

```text
#56 Kanye West - Yeezus
pending review
3 tracks
3 files
Music/Library/FLAC/Kanye West/2013 - Yeezus
```

### Dashboard routing guard

Split-complete parent containers should not open the empty normal Review Workspace as if they were normal media batches.

Discography split children are normal review targets. They should be edited and approved as child batches, not through the parent container.

## Validation That Was Run

The following checks were run during the work and passed at the time:

```powershell
cd frontend
npm run build
cd ..
python -m compileall backend/app
python scripts/check_parent_candidate_materialization_state.py
python scripts/check_qa1_all_media_acceptance_gate.py
git diff --check
```

Regression coverage was added or extended around:

```text
split-complete parents staying containers
split-complete parents counting actual child batches
partially materialized parents remaining reviewable
discography editor rows creating child batches without universal candidates
parent containers not becoming move-ready just because child candidates exist
```

## Current State

For the tested parent:

```text
Batch 20
drive-download-20260628T012539Z-3-010
17 child batches created
split complete
parent file count: 0
```

The parent is now acting like a container/history object.

The child batches exist and are listed under the parent detail panel.

Examples:

```text
#56 Kanye West - Yeezus
#55 The Weeknd - Trilogy - Thursday
#54 The Weeknd - Trilogy - Echoes Of Silence
#53 Kanye West - Impossible
#52 Lil Wayne - I Am Not A Human Being II
```

The expected workflow is:

```text
1. Leave the parent alone.
2. Review each created child batch.
3. Approve child batches after metadata looks right.
4. Use Move approved on the child batches.
5. Do not move the parent container.
```

## What Still Needs Fixing

### Child panel needs direct actions

The parent detail panel shows created child batches, but it should provide direct actions.

Needed:

```text
Review child batch
Approve child batch
Maybe open child row/detail directly
```

Without those actions, the user can see pending children but does not have an obvious next click from the parent detail.

### Parent Review Workspace should explain the correct next step

If a split-complete parent is opened in Review Workspace, it should not show an empty candidate layout without guidance.

Better behavior:

```text
This parent has been split into child batches.
Review and approve the created child batches instead.
```

It should also link to or list those child batches.

### Child batches should be easy to find on dashboard

The dashboard should make the extracted child batches findable after split.

Possible options:

```text
Add a child batch filter
Highlight newly created child batches
Add "View child batches" from parent row
Keep child rows visible as normal pending_review rows
```

### Approving parent must stay blocked

The parent should not be approved or moved after child creation.

If the user clicks parent approval, the system should continue to block it with clear wording:

```text
Parent review containers require child batch review before move approval.
Approve and move the child batches, not the parent container.
```

## Suggested Next Small Fix

Implement a UI-only workflow polish:

```text
AA-QA1-FIX3.3.3 - Created Child Batch Review Actions
```

Requirements:

```text
In CreatedChildBatchesPanel, add Review and Approve buttons per child row.
Review opens the existing normal metadata editor for that child batch.
Approve calls the existing approve flow for that child batch.
Do not add new backend move behavior.
Do not move files.
Do not delete files.
Do not mutate embedded tags.
Keep the parent as split_complete.
```

Expected user path after the fix:

```text
Open parent detail
Scroll to Created child batches
Click Review on #56 Kanye West - Yeezus
Confirm metadata
Approve #56
Repeat for each child
Click Move approved when ready
```

## Safety Boundaries Preserved

The work was intended to preserve these boundaries:

```text
No final library move during split/materialization.
No file deletion.
No embedded tag mutation.
No old modal removal.
No AI/Llama behavior.
No Cleaner or Intake Watcher behavior.
Parent evidence remains available.
Child batches hold scoped file ownership.
```

## Key Files Involved

Backend:

```text
backend/app/api/routes.py
backend/app/services/batch_split.py
backend/app/services/batch_display.py
backend/app/services/parent_candidate_materialization.py
backend/app/schemas/archive.py
```

Frontend:

```text
frontend/src/api/client.ts
frontend/src/components/BatchDetail.tsx
frontend/src/components/BatchRow.tsx
frontend/src/components/DiscographyEditor.tsx
frontend/src/components/MediaReviewRouter.tsx
frontend/src/App.tsx
frontend/src/types/archive.ts
frontend/src/style.css
```

Regression:

```text
scripts/check_parent_candidate_materialization_state.py
scripts/check_qa1_all_media_acceptance_gate.py
```

