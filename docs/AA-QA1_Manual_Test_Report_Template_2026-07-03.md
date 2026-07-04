# AA-QA1 Manual Test Report

Date:
Tester:
Commit hash:
Environment:
Data root:
Ingest root:

## Summary

Status: PASS / PASS WITH GAPS / FAIL

## Automated validation

- [ ] python -m compileall backend/app
- [ ] python scripts/check_system1_scoped_object_contract.py
- [ ] python scripts/check_qa1_all_media_acceptance_gate.py
- [ ] python scripts/check_core_v1_regression.py
- [ ] cd frontend && npm run build
- [ ] git diff --check

## Media class results

| Media class | Test fixture | Scan | Review | Destination preview | Approval | Move readiness | Result | Notes |
|---|---|---:|---:|---:|---:|---:|---|---|
| music_album |  |  |  |  |  |  |  |  |
| music_discography |  |  |  |  |  |  |  |  |
| split_child_music_album |  |  |  |  |  |  |  |  |
| audiobook |  |  |  |  |  |  |  |  |
| multi_disc_audiobook |  |  |  |  |  |  |  |  |
| audiobook_series_or_collection |  |  |  |  |  |  |  |  |
| ebook |  |  |  |  |  |  |  |  |
| pdf_book |  |  |  |  |  |  |  |  |
| book_collection |  |  |  |  |  |  |  |  |
| comic_or_cbz_cbr |  |  |  |  |  |  |  |  |
| movie |  |  |  |  |  |  |  |  |
| movie_collection |  |  |  |  |  |  |  |  |
| tv_show |  |  |  |  |  |  |  |  |
| tv_episode |  |  |  |  |  |  |  |  |
| tv_special_or_anime_special |  |  |  |  |  |  |  |  |
| artwork |  |  |  |  |  |  |  |  |
| subtitle |  |  |  |  |  |  |  |  |
| sidecar_metadata |  |  |  |  |  |  |  |  |
| unknown |  |  |  |  |  |  |  |  |
| mixed_media_folder |  |  |  |  |  |  |  |  |
| quarantine_review_item |  |  |  |  |  |  |  |  |

## Scoped object checks

- [ ] No child object inherited parent/sibling tracks.
- [ ] No artwork became a track/chapter/episode/book.
- [ ] No sidecar became a primary media object.
- [ ] Subtitles attach only to the correct movie/episode/show.
- [ ] Artwork attaches only to the correct album/book/movie/show unless classified as parent-level artwork.
- [ ] Unknown files require review.
- [ ] Mixed media does not silently move.

## Safety checks

- [ ] No deletion.
- [ ] No overwrite.
- [ ] No embedded tag mutation.
- [ ] No final move without approval.
- [ ] Quarantine remains review-only.
- [ ] Reset/dev tools cannot touch real NAS media.

## Known gaps accepted for now

List each gap and why it is acceptable before UX7.

## Blockers before UX7

List anything that must be fixed before Move Readiness Panel work.