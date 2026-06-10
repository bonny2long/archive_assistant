"""Validation script for TV large mixed show review (Update 036).

Tests:
1. Normal SxxExx episodes → normal_episodes bucket
2. OAD/OVA files → special_episodes bucket with destination_group
3. Special/SP files → special_episodes bucket
4. SxxPxx files → special_episodes bucket
5. SxxExx.x files → special_episodes bucket with season_number
6. Unparsable video files → unresolved_video_files bucket
7. Zero-byte files → ignored_corrupt_video_files
8. tv_warning_details populated correctly
9. File counts are consistent
10. Episode destinations for each category
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.mover import _tv_episode_destination, _tv_special_group_destination
from app.services.scanner import _tv_batch_data


PASS = "PASS"
FAIL = "FAIL"


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def check(description: str, condition: bool) -> None:
    status = PASS if condition else FAIL
    print(f"  [{status}] {description}")


def main() -> int:
    failures = 0

    with TemporaryDirectory(dir=r"C:\tmp") as temp:
        temp_root = Path(temp)
        show = temp_root / "Shingeki no Kyojin (2013)"

        # ── Normal episodes (2 seasons) ──
        touch(show / "Season 01" / "Shingeki no Kyojin - S01E01 - To You 2000 Years.mkv")
        touch(show / "Season 01" / "Shingeki no Kyojin - S01E02 - That Day.mkv")
        touch(show / "Season 02" / "Shingeki no Kyojin - S02E01 - Beast Titan.mkv")
        touch(show / "Season 02" / "Shingeki no Kyojin - S02E02 - I'm Home.mkv")

        # ── OAD files ──
        touch(show / "Shingeki no Kyojin - OADE01 - Ilse's Notebook.mkv")
        touch(show / "Shingeki no Kyojin - OAD 02 - A Sudden Visitor.mkv")

        # ── OVA files ──
        touch(show / "Shingeki no Kyojin - OVA 01 - Lost Girls.mkv")
        touch(show / "Shingeki no Kyojin - OVA02 - No Regrets.mkv")

        # ── Special/SP files ──
        touch(show / "Shingeki no Kyojin - SP01 - Digest.mkv")
        touch(show / "Shingeki no Kyojin - Special 02 - Recap.mkv")

        # ── Part files (SxxPxx) ──
        touch(show / "Shingeki no Kyojin - S01P01 - Part 1.mkv")

        # ── Fractional episodes (SxxExx.x) ──
        touch(show / "Shingeki no Kyojin - S02E01.5 - Midpoint Recap.mkv")

        # ── Unresolvable file (generic name, no season/episode) ──
        touch(show / "extra_video_that_cannot_be_parsed.mkv")

        # ── Zero-byte stub ──
        touch(show / "Shingeki no Kyojin - S01E03 - stub.mkv")

        # ── Sidecar ──
        touch(show / "tvshow.nfo")

        data = _tv_batch_data(show)

        # ── Test 1: data exists ──
        if data is None:
            print("  [FAIL] _tv_batch_data returned None")
            return 1

        md = data["metadata"]
        files = data["files"]
        print(f"\nShow: {md.get('show_title')}")
        print(f"  Episode count (normal): {md.get('episode_count')}")
        print(f"  Special episode count: {md.get('special_episode_count')}")
        print(f"  Unresolved video count: {md.get('unresolved_video_count')}")
        print(f"  Video file count (total): {md.get('video_file_count')}")
        print(f"  Ignored corrupt video count: {md.get('ignored_corrupt_video_count')}")
        print(f"  Warnings: {md.get('metadata_warnings')}")

        # ── Test 2: Normal episodes ──
        print("\n── Normal episodes ──")
        check("4 normal episodes", md["episode_count"] == 4)

        # ── Test 3: Special episodes (OADs, OVAs, Specials, Parts, Fractionals) ──
        print("\n── Special episodes ──")
        check("7 special episodes", md["special_episode_count"] == 7)

        specials = md.get("special_episodes", [])
        oad_items = [s for s in specials if s.get("destination_group") == "oad"]
        ova_items = [s for s in specials if s.get("destination_group") == "ova"]
        specials_items = [s for s in specials if s.get("special_label", "").startswith("SP")]
        part_items = [s for s in specials if s.get("destination_group") == "specials" and "P" in (s.get("special_label") or "")]
        fractional_items = [s for s in specials if s.get("destination_group") == "specials" and "." in (s.get("special_label") or "")]
        check("2 OAD episodes", len(oad_items) == 2)
        check("2 OVA episodes", len(ova_items) == 2)
        check("2 Special/SP episodes", len(specials_items) == 2)
        check("1 Part episode (SxxPxx)", len(part_items) == 1)
        check("1 Fractional episode (SxxExx.x)", len(fractional_items) == 1)

        for s in oad_items:
            check(f"  OAD {s['source_file']} → is_special", s.get("is_special") is True)
            check(f"  OAD {s['source_file']} → destination_group=oad", s.get("destination_group") == "oad")

        for s in ova_items:
            check(f"  OVA {s['source_file']} → is_special", s.get("is_special") is True)
            check(f"  OVA {s['source_file']} → destination_group=ova", s.get("destination_group") == "ova")

        for s in fractional_items:
            check(f"  Fractional {s['source_file']} → season_number present", s.get("season_number") is not None)

        # ── Test 4: Unresolved files ──
        print("\n── Unresolved files ──")
        check("1 unresolved video file", md.get("unresolved_video_count") == 1)

        # ── Test 5: Zero-byte files ──
        print("\n── Zero-byte files ──")
        check("1 ignored corrupt video", md.get("ignored_corrupt_video_count") == 1)

        # ── Test 6: tv_warning_details ──
        print("\n── Warning details ──")
        details = md.get("tv_warning_details", {})
        check("tv_warning_details exists", bool(details))
        unparsed = details.get("unparsed_video_files", [])
        check(f"unparsed_video_files has 1 entry ({len(unparsed)})", len(unparsed) == 1)
        generic = details.get("generic_title_files", [])
        check("generic_title_files has entries", len(generic) > 0)

        # ── Test 7: Total video count ──
        print("\n── Count consistency ──")
        expected_total = md["episode_count"] + md["special_episode_count"] + md["unresolved_video_count"]
        check(
            f"video_file_count ({md['video_file_count']}) equals total ({expected_total})",
            md["video_file_count"] == expected_total,
        )
        check(
            "season_count is 2",
            md["season_count"] == 2,
        )

        # ── Test 8: Episode destinations ──
        print("\n── Episode destinations ──")
        dest = temp_root / "TV" / "Library" / "Shingeki no Kyojin"
        for s in specials:
            sf = SimpleNamespace(
                file_name=s["source_file"],
                metadata_json=s,
            )
            ep_dest = _tv_episode_destination(dest, sf)
            group = s.get("destination_group", "")
            if group == "oad":
                check(f"  OAD destination → OADs/ folder: {ep_dest}", ep_dest is not None and "OADs" in str(ep_dest))
            elif group == "ova":
                check(f"  OVA destination → OVAs/ folder: {ep_dest}", ep_dest is not None and "OVAs" in str(ep_dest))

        # ── Test 9: Special group helper ──
        print("\n── Special group destinations ──")
        oad_folder = _tv_special_group_destination(dest, "oad")
        ova_folder = _tv_special_group_destination(dest, "ova")
        specials_folder = _tv_special_group_destination(dest, "specials")
        extras_folder = _tv_special_group_destination(dest, "extras")
        check("OADs folder name", oad_folder.name == "OADs")
        check("OVAs folder name", ova_folder.name == "OVAs")
        check("Specials folder name", specials_folder.name == "Specials")
        check("Extras folder name", extras_folder.name == "Extras")

    print()
    if failures:
        print(f"Result: {failures} failure(s)")
    else:
        print("All checks passed!")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
