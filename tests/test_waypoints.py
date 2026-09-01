import datetime
import json
import os
import re

import pytest

import waypoints_core as c


# ---- surfaceable (done + date filtering) ----

def _items():
    return [
        {"id": "a", "title": "A", "surface_on": None, "done": False},
        {"id": "b", "title": "B", "surface_on": None, "done": True},
        {"id": "c", "title": "C", "surface_on": "2026-07-13", "done": False},
        {"id": "d", "title": "D", "surface_on": "2026-07-10", "done": False},
    ]


def test_surfaceable_hides_done():
    out = [i["id"] for i in c.surfaceable(_items(), "2026-07-20")]
    assert "b" not in out


def test_surfaceable_undated_always_shows():
    out = [i["id"] for i in c.surfaceable(_items(), "2000-01-01")]
    assert "a" in out


def test_surfaceable_future_date_hidden_before():
    out = [i["id"] for i in c.surfaceable(_items(), "2026-07-12")]
    assert "c" not in out  # surface_on 07-13 > today 07-12


def test_surfaceable_date_shows_on_and_after():
    on = [i["id"] for i in c.surfaceable(_items(), "2026-07-13")]
    after = [i["id"] for i in c.surfaceable(_items(), "2026-07-14")]
    assert "c" in on and "c" in after  # boundary inclusive


def test_surfaceable_past_date_shows():
    out = [i["id"] for i in c.surfaceable(_items(), "2026-07-12")]
    assert "d" in out


# ---- format_banner ----

def test_format_banner_empty_is_empty_string():
    assert c.format_banner([]) == ""


def test_format_banner_lists_titles_not_ids():
    b = c.format_banner([{"id": "x1", "title": "Do the thing", "surface_on": None, "done": False}])
    assert "waypoint" in b.lower()
    assert "Do the thing" in b
    assert "x1" not in b  # ids are a redundant restatement right next to the title; not printed


# ---- add / done / prune / slug ----

def test_add_item_generates_unique_slug_ids():
    items = []
    i1 = c.add_item(items, "Publish the PR", created="2026-07-12")
    i2 = c.add_item(items, "Publish the PR", created="2026-07-12")
    assert i1["id"] == "publish-the-pr"
    assert i2["id"] != i1["id"]  # de-duplicated
    assert len(items) == 2 and i1["done"] is False


def test_add_item_records_surface_on():
    items = []
    it = c.add_item(items, "Later", surface_on="2026-07-13", created="2026-07-12")
    assert it["surface_on"] == "2026-07-13"


def test_mark_done_sets_flag_and_returns_true():
    items = [{"id": "k", "title": "K", "surface_on": None, "done": False}]
    assert c.mark_done(items, "k") is True
    assert items[0]["done"] is True
    assert c.mark_done(items, "nope") is False


def test_prune_moves_done_to_archive_batch():
    # 0.4.0: prune is a MOVE, not a delete — it returns (kept, archived) and nothing is dropped.
    items = [{"id": "a", "done": False, "title": "A", "surface_on": None},
             {"id": "b", "done": True, "title": "B", "surface_on": None}]
    kept, archived = c.prune(items)
    assert [i["id"] for i in kept] == ["a"]
    assert [i["id"] for i in archived] == ["b"]
    # every input item is accounted for in exactly one output pile — the property that makes
    # prune non-destructive, and the one a future refactor would break first
    assert len(kept) + len(archived) == len(items)


def test_prune_stamps_archived_at_so_the_trail_carries_when():
    items = [{"id": "b", "done": True, "title": "B", "surface_on": None}]
    os.environ["WAYPOINTS_TODAY"] = "2026-08-27"
    try:
        _, archived = c.prune(items)
    finally:
        del os.environ["WAYPOINTS_TODAY"]
    assert archived[0]["archived_at"] == "2026-08-27"


# ---- v0.1.3: slug cap, summary tier, edit/get, summary-aware banner ----

def test_slugify_caps_length_and_trims_partial_word():
    long = ("Run Adobe cutout re-test on corporate wifi with a very long descriptive "
            "title that just keeps going well past any sane id length")
    s = c.slugify(long)
    assert len(s) <= 30
    assert not s.startswith("-") and not s.endswith("-")


def test_add_item_defaults_summary_to_empty_list():
    items = []
    it = c.add_item(items, "Do X", created="2026-07-14")
    assert it["summary"] == []


def test_add_item_stores_summary_list():
    items = []
    it = c.add_item(items, "Do X", summary=["point one", "point two"], created="2026-07-14")
    assert it["summary"] == ["point one", "point two"]


def test_get_item_returns_match_or_none():
    items = [{"id": "k", "title": "K"}]
    assert c.get_item(items, "k")["title"] == "K"
    assert c.get_item(items, "nope") is None


def test_edit_item_changes_only_passed_fields():
    items = []
    c.add_item(items, "Old title", detail="keep me", created="2026-07-14")
    iid = items[0]["id"]
    c.edit_item(items, iid, title="New title")
    assert items[0]["title"] == "New title"
    assert items[0]["detail"] == "keep me"   # untouched


def test_edit_item_id_and_created_are_immutable():
    items = []
    c.add_item(items, "Title", created="2026-07-01")
    iid = items[0]["id"]
    c.edit_item(items, iid, title="Totally different words here")
    assert items[0]["id"] == iid            # id stable despite retitle (the whole point)
    assert items[0]["created"] == "2026-07-01"


def test_edit_item_replaces_summary():
    items = []
    c.add_item(items, "T", summary=["a"], created="2026-07-14")
    iid = items[0]["id"]
    c.edit_item(items, iid, summary=["x", "y"])
    assert items[0]["summary"] == ["x", "y"]


def test_edit_item_surface_on_sentinel_vs_explicit():
    items = []
    c.add_item(items, "T", surface_on="2026-07-20", created="2026-07-14")
    iid = items[0]["id"]
    c.edit_item(items, iid, title="renamed")            # not passing surface_on
    assert items[0]["surface_on"] == "2026-07-20"       # → left intact
    c.edit_item(items, iid, surface_on=None)            # explicit clear
    assert items[0]["surface_on"] is None
    c.edit_item(items, iid, surface_on="2026-08-01")    # explicit set
    assert items[0]["surface_on"] == "2026-08-01"


def test_edit_item_returns_none_for_missing_id():
    assert c.edit_item([], "nope", title="x") is None


def test_format_banner_renders_summary_bullets():
    b = c.format_banner([{"id": "x1", "title": "Headline", "summary": ["first pt", "second pt"],
                          "surface_on": None, "created": "2026-07-14", "done": False}])
    assert "Headline" in b
    assert "first pt" in b and "second pt" in b


def test_format_banner_without_summary_is_title_only():
    b = c.format_banner([{"id": "x1", "title": "Headline", "surface_on": None,
                          "created": "2026-07-14", "done": False}])
    assert [l for l in b.splitlines() if l.strip().startswith("- ")] == []


def test_format_banner_compact_mode_past_threshold_drops_bullets():
    items = [{"id": f"x{n}", "title": f"Item {n}", "summary": ["detail point"],
              "surface_on": None, "done": False} for n in range(c.COMPACT_THRESHOLD + 1)]
    b = c.format_banner(items)
    assert "detail point" not in b
    assert all(f"Item {n}" in b for n in range(c.COMPACT_THRESHOLD + 1))
    assert "waypoints.py show" in b


def test_format_banner_at_threshold_still_shows_bullets():
    items = [{"id": f"x{n}", "title": f"Item {n}", "summary": ["detail point"],
              "surface_on": None, "done": False} for n in range(c.COMPACT_THRESHOLD)]
    b = c.format_banner(items)
    assert "detail point" in b
    assert "waypoints.py show" not in b


# ---- line-wrap hanging indent ----

def test_format_banner_wrapped_bullet_hangs_indent_under_text():
    long_title = "A " + ("very long descriptive title word " * 6)
    items = [{"id": "x1", "title": long_title, "surface_on": None, "created": None,
              "done": False}]
    b = c.format_banner(items)
    bullet_block = [l for l in b.splitlines() if l.startswith("  • ") or l.startswith("    ")]
    assert len(bullet_block) > 1  # actually wrapped across multiple lines
    assert bullet_block[0].startswith("  • ")
    for cont in bullet_block[1:]:
        assert cont.startswith("    ") and not cont.startswith("    • ")


def test_format_banner_wrapped_summary_point_hangs_indent_under_text():
    long_point = "a very long summary bullet point word " * 6
    items = [{"id": "x1", "title": "T", "summary": [long_point], "surface_on": None,
              "created": None, "done": False}]
    lines = c.format_banner(items).splitlines()
    idx = next(i for i, l in enumerate(lines) if l.strip().startswith("- "))
    assert lines[idx].startswith("      - ")
    assert lines[idx + 1].startswith("        ")  # continuation hangs under the point's text
    assert not lines[idx + 1].startswith("        - ")


def test_format_banner_date_is_always_its_own_line():
    # v0.1.10: the date never shares a line with the title (regardless of title length) —
    # it always gets its own hanging-indented line, so its indentation is predictable.
    long_title = ("Tackle two JoyIA Chat-drafted plans once budget resets: "
                  "credit-efficient-setup-v2.md")
    items = [{"id": "x1", "title": long_title, "surface_on": None, "created": "2026-07-16",
              "done": False}]
    lines = c.format_banner(items).splitlines()
    since_lines = [l for l in lines if "since" in l or "2026-07-16" in l]
    assert len(since_lines) == 1
    assert since_lines[0] == "    (since 2026-07-16)"
    title_lines = [l for l in lines if "Tackle" in l]
    assert not any("since" in l for l in title_lines)  # date never on the title's own line(s)


# ---- v0.1.9: conservative width prevents double-wrap by Claude Code's renderer ----

def test_banner_width_is_conservative_under_80_cols():
    # The banner is relayed through Claude Code's own message renderer, which re-wraps at the
    # user's live pane width. Keeping our width comfortably under the common 80-col minimum stops
    # that second wrap from mangling our hanging indents.
    assert c.BANNER_WIDTH <= 76


def test_no_emitted_line_exceeds_banner_width():
    # Every wrapped line we emit must fit within BANNER_WIDTH so a real (>=80-col) terminal pane
    # never re-wraps it. Uses long text in every tier: header, title, since-date, summary points.
    items = [
        {"id": "x1",
         "title": "A very long descriptive waypoint title that will certainly need wrapping " * 2,
         "summary": ["a long summary bullet point that also must wrap across several lines " * 2],
         "surface_on": None, "created": "2026-07-16", "done": False},
        {"id": "x2", "title": "second", "surface_on": None, "created": "2026-07-16",
         "done": False},
    ]
    for line in c.format_banner(items).splitlines():
        assert len(line) <= c.BANNER_WIDTH, repr(line)


def test_compact_mode_lines_also_within_width():
    # Compact mode (>3 items) emits its own notice line + title-only bullets; those must fit too.
    items = [{"id": f"i{n}",
              "title": "long compact-mode waypoint title that needs to wrap somewhere " * 2,
              "surface_on": None, "created": "2026-07-16", "done": False} for n in range(5)]
    b = c.format_banner(items)
    assert "compact mode" in b
    for line in b.splitlines():
        assert len(line) <= c.BANNER_WIDTH, repr(line)


def test_since_annotation_stays_atomic_at_new_width():
    # The date line is its own line at the 72-col width regardless of title length.
    long_title = "Tackle a plan once budget resets: some-fairly-long-artifact-name-v2.md here"
    items = [{"id": "x1", "title": long_title, "surface_on": None, "created": "2026-07-16",
              "done": False}]
    lines = c.format_banner(items).splitlines()
    since_lines = [l for l in lines if "since" in l or "2026-07-16" in l]
    assert len(since_lines) == 1
    assert since_lines[0] == "    (since 2026-07-16)"


# ---- reopen / toggle / priority / reorder ----

def test_reopen_item_clears_done():
    items = [{"id": "a", "title": "A", "done": True}]
    assert c.reopen_item(items, "a") is True
    assert items[0]["done"] is False


def test_reopen_item_missing_id_returns_false():
    assert c.reopen_item([], "nope") is False


def test_toggle_done_flips_state_both_ways():
    items = [{"id": "a", "title": "A", "done": False}]
    assert c.toggle_done(items, "a") is True
    assert items[0]["done"] is True
    assert c.toggle_done(items, "a") is False
    assert items[0]["done"] is False


def test_toggle_done_missing_id_returns_none():
    assert c.toggle_done([], "nope") is None


def test_add_item_defaults_priority_to_zero():
    items = []
    it = c.add_item(items, "Do X", created="2026-07-14")
    assert it["priority"] == 0


def test_set_priority_updates_item():
    items = []
    c.add_item(items, "Title", created="2026-07-14")
    iid = items[0]["id"]
    it = c.set_priority(items, iid, 5)
    assert it["priority"] == 5
    assert items[0]["priority"] == 5


def test_set_priority_missing_id_returns_none():
    assert c.set_priority([], "nope", 5) is None


def test_surfaceable_sorts_by_priority_descending():
    items = [
        {"id": "a", "title": "A", "surface_on": None, "done": False, "priority": 0},
        {"id": "b", "title": "B", "surface_on": None, "done": False, "priority": 5},
        {"id": "c", "title": "C", "surface_on": None, "done": False, "priority": 1},
    ]
    out = [i["id"] for i in c.surfaceable(items, "2026-07-14")]
    assert out == ["b", "c", "a"]


def test_surfaceable_stable_order_for_equal_priority():
    items = [
        {"id": "a", "title": "A", "surface_on": None, "done": False, "priority": 0},
        {"id": "b", "title": "B", "surface_on": None, "done": False, "priority": 0},
    ]
    out = [i["id"] for i in c.surfaceable(items, "2026-07-14")]
    assert out == ["a", "b"]


def test_reorder_item_moves_to_position():
    items = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}, {"id": "c", "title": "C"}]
    assert c.reorder_item(items, "c", 0) is True
    assert [i["id"] for i in items] == ["c", "a", "b"]


def test_reorder_item_clamps_out_of_range_position():
    items = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
    assert c.reorder_item(items, "a", 99) is True
    assert [i["id"] for i in items] == ["b", "a"]


def test_reorder_item_missing_id_returns_false():
    assert c.reorder_item([], "nope", 0) is False


# ---- v0.1.12: looks_unresolved heuristic + done --as (resolve-before-close) ----

def test_looks_unresolved_matches_trailing_question_mark():
    assert c.looks_unresolved("Does the new flow work?") is True


def test_looks_unresolved_matches_leading_inquiry_verbs():
    for t in ["Confirm qwen thinking works", "Decide + open the PRs", "Test CC Live behavior",
              "Verify the fix holds", "Research the best model", "Investigate the crash",
              "Evaluate Kimi-VL", "Compare A vs B", "Head-to-head: X vs Y",
              "Whether to ship now", "Should we migrate"]:
        assert c.looks_unresolved(t) is True, t


def test_looks_unresolved_ignores_plain_task_imperatives():
    for t in ["Fix the login bug", "Add a logout button", "Build the artwork",
              "Publish the PR", "Finish the plugin", "Run the backup"]:
        assert c.looks_unresolved(t) is False, t


def test_looks_unresolved_empty_or_none_is_false():
    assert c.looks_unresolved("") is False
    assert c.looks_unresolved(None) is False


def test_looks_unresolved_leader_is_word_boundary_not_prefix():
    # "Testing" / "Addendum" start with a leader substring but aren't the inquiry verb.
    assert c.looks_unresolved("Testing infrastructure rollout") is False
    assert c.looks_unresolved("Confirmation email template") is False


def test_mark_done_with_resolved_title_rewrites_and_closes():
    items = [{"id": "k", "title": "Confirm X works", "created": "2026-08-01", "done": False}]
    assert c.mark_done(items, "k", resolved_title="Confirmed: X works in prod") is True
    assert items[0]["title"] == "Confirmed: X works in prod"
    assert items[0]["done"] is True
    assert items[0]["id"] == "k" and items[0]["created"] == "2026-08-01"  # immutable


def test_mark_done_without_resolved_title_leaves_title_untouched():
    items = [{"id": "k", "title": "Confirm X works", "done": False}]
    assert c.mark_done(items, "k") is True
    assert items[0]["title"] == "Confirm X works"
    assert items[0]["done"] is True


# ---- optional triage verdict (tier + gate reason) ----

def _legacy():
    """An item as written before verdicts existed: no `tier` key at all."""
    return {"id": "old", "title": "Old", "summary": [], "detail": "",
            "surface_on": None, "created": "2026-01-01", "done": False, "priority": 0}


def test_add_item_writes_no_verdict_keys_by_default():
    items = []
    it = c.add_item(items, "Plain")
    # ABSENT, not None: a store written before verdicts existed must stay byte-comparable.
    assert "tier" not in it and "gate_reason" not in it


def test_add_item_with_verdict_stores_both():
    items = []
    it = c.add_item(items, "Blocked", tier="gated", gate_reason="needs the user present")
    assert it["tier"] == "gated" and it["gate_reason"] == "needs the user present"


def test_legacy_item_is_untriaged_not_actionable():
    it = _legacy()
    assert c.is_untriaged(it)
    assert not c.is_actionable(it) and not c.is_gated(it)


def test_validate_verdict_rejects_unknown_tier():
    with pytest.raises(c.VerdictError):
        c.validate_verdict("urgent")


def test_validate_verdict_rejects_gate_reason_on_non_gated():
    # A reason on a non-gated item is a record that disagrees with itself.
    with pytest.raises(c.VerdictError):
        c.validate_verdict("do-now", "waiting on nothing")


def test_validate_verdict_allows_gate_reason_when_gated():
    # validate_verdict returns the three verdict fields now: (tier, gate_reason, waiting_on).
    assert c.validate_verdict("gated", "needs a decision") == ("gated", "needs a decision", None)


def test_set_verdict_clearing_removes_keys_entirely():
    items = [c.add_item([], "X", tier="gated", gate_reason="blocked on CI")]
    c.set_verdict(items, items[0]["id"], tier=None)
    assert "tier" not in items[0] and "gate_reason" not in items[0]


def test_set_verdict_retiering_away_from_gated_drops_the_inherited_reason():
    # Unblocking an item is one call: the reason is orphaned by definition, so it goes.
    items = []
    it = c.add_item(items, "X", tier="gated", gate_reason="blocked on CI")
    c.set_verdict(items, it["id"], tier="do-now")
    assert it["tier"] == "do-now" and "gate_reason" not in it


def test_set_verdict_refuses_an_explicit_reason_on_a_non_gated_tier():
    # Inheriting a stale reason is a no-op worth silently fixing; ASKING for a reason on a
    # do-now item is a contradiction of intent and is refused.
    items = []
    it = c.add_item(items, "X", tier="gated", gate_reason="blocked on CI")
    with pytest.raises(c.VerdictError):
        c.set_verdict(items, it["id"], tier="do-now", gate_reason="still blocked")


def test_set_verdict_unknown_id_returns_none():
    assert c.set_verdict([], "nope", tier="do-now") is None


def test_partition_groups_are_exhaustive_and_disjoint():
    items = [_legacy()]
    c.add_item(items, "A", tier="do-now")
    c.add_item(items, "B", tier="heavy")
    c.add_item(items, "C", tier="gated", gate_reason="r")
    g = c.partition(items)
    assert len(g["actionable"]) == 2 and len(g["gated"]) == 1 and len(g["untriaged"]) == 1
    # The property a reader relies on to know nothing was dropped:
    assert sum(len(v) for v in g.values()) == len(items)


# ---- list_payload: the documented machine-readable contract ----

def test_list_payload_declares_its_own_contract_version():
    p = c.list_payload([])
    assert p["contract"] == c.LIST_CONTRACT
    # Contract version is independent of the store version -- that's the decoupling.
    assert c.LIST_CONTRACT is not None and "version" not in p


def test_list_payload_counts_add_up():
    items = [_legacy()]
    c.add_item(items, "A", tier="do-now")
    c.add_item(items, "G", tier="gated", gate_reason="r")
    d = c.add_item(items, "Done", tier="heavy")
    d["done"] = True
    p = c.list_payload(items, "2026-07-20")
    cts = p["counts"]
    assert cts["total"] == 4 and cts["open"] == 3 and cts["done"] == 1
    assert cts["gated"] + cts["actionable"] + cts["untriaged"] == cts["open"]


def test_list_payload_normalizes_absent_verdict_to_null():
    items = [_legacy()]
    p = c.list_payload(items, "2026-07-20")
    row = p["items"][0]
    # Absent in the STORE, explicitly null in the VIEW: a consumer shouldn't have to tell a
    # missing key from a null one.
    assert row["tier"] is None and row["gate_reason"] is None
    assert "tier" not in items[0]


def test_list_payload_computes_surfaceability():
    items = []
    c.add_item(items, "Now")
    c.add_item(items, "Later", surface_on="2099-01-01")
    p = c.list_payload(items, "2026-07-20")
    by_title = {i["title"]: i for i in p["items"]}
    assert by_title["Now"]["surfaceable"] is True
    assert by_title["Later"]["surfaceable"] is False


# ---- banner: gated marking and length-driven collapse ----

def _gated(n, prefix="G"):
    items = []
    for k in range(n):
        c.add_item(items, f"{prefix}{k}", tier="gated", gate_reason=f"reason {k}")
    return items


def test_banner_marks_a_few_gated_items_inline():
    items = _gated(2)
    out = c.format_banner(items)
    assert out.count("⛔") == 2
    assert "G0" in out and "G1" in out


def test_banner_collapses_gated_group_past_the_threshold():
    n = c.GATED_COLLAPSE_THRESHOLD + 1
    items = _gated(n)
    out = c.format_banner(items)
    assert f"⛔ {n} gated" in out            # the count is always stated
    assert "G0" not in out                   # individual titles collapsed away
    assert "waypoints-gated" in out          # and the way to expand is named


def test_banner_header_count_stays_total_even_when_gated_collapse():
    items = _gated(c.GATED_COLLAPSE_THRESHOLD + 1)
    c.add_item(items, "Actionable one", tier="do-now")
    out = c.format_banner(items)
    assert f"{len(items)} open waypoint(s)" in out   # nothing hidden from the total


def test_banner_does_not_reorder_gated_items():
    # Anti-preference guarantee: a gated item keeps its position rather than being sorted last.
    # Sorting it last would encode an assumption that something else consumes the other pile.
    items = []
    c.add_item(items, "Gated first", tier="gated", gate_reason="r")
    c.add_item(items, "Actionable second", tier="do-now")
    out = c.format_banner(items)
    assert out.index("Gated first") < out.index("Actionable second")


def test_banner_shows_the_gate_reason_when_not_compact():
    items = _gated(1)
    out = c.format_banner(items)
    assert "gated: reason 0" in out


def test_banner_unaffected_for_stores_with_no_verdicts():
    # The whole feature is invisible to a user who never triages anything.
    items = [_legacy()]
    out = c.format_banner(items)
    assert "⛔" not in out and "gated" not in out


def test_wrap_never_splits_hyphenated_tokens():
    # Regression: default textwrap broke `/waypoints-gated` across lines, leaving the user a
    # command they cannot copy. Kebab-case ids hit the same bug, so this guards both.
    long_id = "resume-interrupted-a-budget-caused-kill-on-a-later-utc-day"
    # The padding matters: the token must STRADDLE the wrap boundary, or default textwrap has no
    # occasion to split it and the test passes for the wrong reason. Verified that without
    # break_on_hyphens=False this exact input yields "...-utc-\n    day".
    out = c._wrap(f"xxxx pick up {long_id} now", "  • ")
    assert "\n" in out, "input must actually wrap for this to test anything"
    assert long_id in out, "hyphenated id was split across lines"
    for line in out.splitlines():
        assert not line.rstrip().endswith("-"), f"token split at a hyphen: {line!r}"


def test_wrap_keeps_slash_commands_intact_at_a_boundary():
    out = c._wrap("x" * 60 + " run /waypoints-gated to expand the group", "  ")
    assert "/waypoints-gated" in out


def test_banner_keeps_long_ids_intact():
    items = []
    c.add_item(items, "DISTILLER 0.7.0 — rename to claude-code-transcript-distiller everywhere",
               tier="gated", gate_reason="outward-facing repo rename needs sign-off")
    out = c.format_banner(items)
    assert "claude-code-transcript-distiller" in out
    assert "outward-facing" in out


# ---- v0.4.0: archive tiers, the paper trail, and the backup ring ----

def test_archive_payload_contract_shape():
    items = [{"id": "a", "title": "A", "summary": ["p"], "done": True,
              "archived_at": "2026-08-20", "restored_at": "2026-08-25"},
             {"id": "b", "title": "B", "done": True, "archived_at": "2026-08-21"}]
    pay = c.archive_payload(items, "2026-08-27")
    assert pay["contract"] == c.ARCHIVE_CONTRACT
    assert pay["generated"] == "2026-08-27"
    assert pay["counts"] == {"total": 2, "restored": 1}
    # a view never makes a consumer distinguish a missing key from a null one
    for entry in pay["items"]:
        for key in ("id", "title", "summary", "detail", "created", "done", "priority",
                    "tier", "gate_reason", "archived_at", "restored_at"):
            assert key in entry
    assert pay["items"][1]["restored_at"] is None
    # NOT the list contract: surfaceability is meaningless off the live store
    assert "surfaceable" not in pay["items"][0]


def _write_store(path, marker):
    path.write_text(json.dumps({"version": 1, "items": [{"id": marker}]}) + "\n")


def test_backup_is_a_copy_so_the_store_never_vanishes(tmp_path):
    # A move would unlink the store between backup and rewrite; dying there leaves no store at
    # the canonical path at all. Assert the source SURVIVES its own backup.
    store = tmp_path / "waypoints.json"
    _write_store(store, "one")
    dst = c._backup_before_write(str(store))
    assert dst is not None
    assert store.exists(), "the store must still exist after being backed up"
    assert json.loads(store.read_text())["items"][0]["id"] == "one"
    assert json.loads(open(dst).read())["items"][0]["id"] == "one"


def test_backups_in_the_same_second_do_not_clobber_each_other(tmp_path):
    # The 0.4.0-draft bug: second-granularity names collided and the earlier snapshot was
    # silently overwritten. Freeze the clock to the same second and demand distinct files.
    store = tmp_path / "waypoints.json"
    fixed = datetime.datetime(2026, 8, 27, 12, 43, 58)

    class _Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    real = c.datetime.datetime
    c.datetime.datetime = _Clock
    try:
        made = []
        for marker in ("one", "two", "three"):
            _write_store(store, marker)
            made.append(c._backup_before_write(str(store)))
    finally:
        c.datetime.datetime = real
    assert all(made), "every changed write must produce a snapshot"
    assert len(set(made)) == 3, "same-second snapshots collided: %r" % (made,)
    # and each one holds its OWN state, not the last writer's
    got = sorted(json.loads(open(m).read())["items"][0]["id"] for m in made)
    assert got == ["one", "three", "two"]


def test_backup_skipped_when_content_is_identical(tmp_path):
    # A no-op write must not consume a ring slot — slots are what protect the older states.
    store = tmp_path / "waypoints.json"
    _write_store(store, "one")
    assert c._backup_before_write(str(store)) is not None
    assert c._backup_before_write(str(store)) is None, "identical content should be skipped"
    _write_store(store, "two")
    assert c._backup_before_write(str(store)) is not None


def test_retention_never_touches_files_it_did_not_create(tmp_path):
    # The real ~/.claude holds hand-made neighbours (waypoints.json.bak-reconcile-20260731-...).
    # A loose glob would delete them. Assert foreign files survive a sweep that deletes ours.
    store = tmp_path / "waypoints.json"
    bdir = tmp_path / "waypoints-backups"
    bdir.mkdir()
    foreign = [bdir / "waypoints.json.bak-reconcile-20260731-025549",
               bdir / "hand-made.json",
               bdir / "waypoints-20260101.json"]  # near-miss: no micros field
    for f in foreign:
        f.write_text("{}")
    for n in range(c.BACKUP_KEEP_RECENT + c.BACKUP_KEEP_DAILY + 12):
        (bdir / ("waypoints.20260401-000000-%06d.json" % n)).write_text("{}")
    removed = c._prune_backups(str(bdir), "waypoints")
    assert removed, "the sweep must actually delete our surplus snapshots"
    for f in foreign:
        assert f.exists(), "retention deleted a file it did not create: %s" % f.name


def test_retention_keeps_the_ring_bounded_but_spares_day_baselines(tmp_path):
    bdir = tmp_path / "waypoints-backups"
    bdir.mkdir()
    # a burst of same-day writes, big enough to evict everything older on its own
    for n in range(c.BACKUP_KEEP_RECENT + 15):
        (bdir / ("waypoints.20260827-120000-%06d.json" % n)).write_text("{}")
    # plus one baseline per earlier day, which the burst must NOT be able to evict
    older = ["waypoints.202608%02d-090000-000000.json" % d for d in range(1, 11)]
    for name in older:
        (bdir / name).write_text("{}")
    c._prune_backups(str(bdir), "waypoints")
    left = {p.name for p in bdir.iterdir()}
    for name in older:
        assert name in left, "a burst evicted the day-baseline %s" % name
    assert len(left) <= c.BACKUP_KEEP_RECENT + c.BACKUP_KEEP_DAILY


def test_backups_of_store_and_archive_stay_distinguishable(tmp_path):
    # Both share one backup dir; without the source stem in the name their histories would be
    # indistinguishable after the fact, and dedupe could compare a store to an archive snapshot.
    store = tmp_path / "waypoints.json"
    arch = tmp_path / "waypoints-archive.json"
    _write_store(store, "live")
    _write_store(arch, "closed")
    a = c._backup_before_write(str(store))
    b = c._backup_before_write(str(arch), str(store))
    assert os.path.dirname(a) == os.path.dirname(b), "both rings share one directory"
    assert os.path.basename(a).startswith("waypoints.")
    assert os.path.basename(b).startswith("waypoints-archive.")
    assert c._existing_backups(os.path.dirname(a), "waypoints")[-1][2] == a
    assert c._existing_backups(os.path.dirname(b), "waypoints-archive")[-1][2] == b


def test_backup_failure_never_wedges_the_write(tmp_path, monkeypatch):
    # The backup is insurance; a full disk must not stop the store from being saved.
    store = tmp_path / "waypoints.json"
    _write_store(store, "one")
    monkeypatch.setattr(c.shutil, "copy2",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    assert c._backup_before_write(str(store)) is None
    c.save_store({"version": 1, "items": [{"id": "two"}]}, str(store))
    assert json.loads(store.read_text())["items"][0]["id"] == "two"


# ---- v0.4.0: banner is context the user pays for in EVERY session ----

def _flat(text):
    """Banner text with wrapping collapsed. The banner hard-wraps at BANNER_WIDTH, so a phrase
    like `waypoints.py list` legitimately spans two lines; assert on meaning, not on line breaks."""
    return " ".join(text.split())


def _many(n, prefix="Item"):
    return [{"id": "i%d" % k, "title": "%s %d" % (prefix, k), "surface_on": None,
             "done": False, "created": "2026-08-27"} for k in range(n)]


def test_banner_lists_at_most_banner_max_items():
    items = c.surfaceable(_many(40), "2026-08-27")
    out = c.format_banner(items)
    listed = [l for l in out.splitlines() if l.startswith("  • ")]
    assert len(listed) == c.BANNER_MAX_ITEMS


def test_banner_counts_the_unlisted_remainder_rather_than_dropping_it():
    # Nothing may be silently omitted: the header states the total, the tail states the residue.
    items = c.surfaceable(_many(40), "2026-08-27")
    out = c.format_banner(items)
    assert "40 open waypoint(s)" in out
    assert "%d more open" % (40 - c.BANNER_MAX_ITEMS) in _flat(out)
    assert "waypoints.py list" in _flat(out)  # and names how to see them


def test_banner_keeps_the_highest_priority_items_when_capped():
    items = _many(30)
    items[25]["priority"] = 99
    items[26]["priority"] = 50
    out = c.format_banner(c.surfaceable(items, "2026-08-27"))
    assert "Item 25" in out and "Item 26" in out
    assert "Item 0" in out          # priority 0, but early in insertion order (stable sort)
    assert "Item 29" not in out     # the low-priority tail is summarised, not listed


def test_banner_does_not_cap_a_short_list():
    items = c.surfaceable(_many(c.BANNER_MAX_ITEMS), "2026-08-27")
    out = c.format_banner(items)
    assert "more open" not in out
    for k in range(c.BANNER_MAX_ITEMS):
        assert "Item %d" % k in out


def test_banner_trims_long_titles_but_marks_them_as_trimmed():
    long_title = ("★ NEXT UP: ship the upgrade lifecycle with release discovery and side-by-side "
                  "venvs plus a seven day rollback window, prefix-cache goal already met")
    items = _many(6)
    items[0]["title"] = long_title
    out = c.format_banner(c.surfaceable(items, "2026-08-27"))
    assert "…" in out, "an over-long title must read as truncated"
    assert long_title not in _flat(out)
    assert "★ NEXT UP: ship the upgrade lifecycle" in _flat(out)  # the head survives
    assert "titles are trimmed" in _flat(out)                     # and the trim is disclosed


def test_banner_keeps_full_titles_when_not_compact():
    # Below COMPACT_THRESHOLD the banner is already small; trimming there would cost meaning
    # for no context saving.
    long_title = "A very long title " * 8
    items = [{"id": "a", "title": long_title.strip(), "surface_on": None, "done": False}]
    out = c.format_banner(c.surfaceable(items, "2026-08-27"))
    assert "…" not in out


def test_short_title_trims_on_a_word_boundary():
    assert c._short_title("alpha beta gamma delta", maxlen=14) == "alpha beta…"
    assert c._short_title("short", maxlen=14) == "short"
    assert c._short_title("alpha beta —", maxlen=11) == "alpha beta…"  # trailing dashes stripped


def _with_gated(n_open=2, n_gated=None):
    items = _many(n_open)
    for k in range((c.GATED_COLLAPSE_THRESHOLD + 1) if n_gated is None else n_gated):
        items.append({"id": "g%d" % k, "title": "Gated %d" % k, "surface_on": None,
                      "done": False, "tier": "gated", "gate_reason": "needs sign-off"})
    return c.surfaceable(items, "2026-08-27")


def test_gated_summary_points_at_ungate_queue_and_drops_the_duplicate_invocation():
    out = c.format_banner(_with_gated(), ungate_hint=True)
    assert "/waypoints-gated" in _flat(out)
    assert "/ungate-queue" in _flat(out)
    assert "list --gated" not in _flat(out), "the duplicate invocation should be gone"


def test_capped_banner_still_accounts_for_every_open_item():
    # The property that makes capping safe: listed + unlisted + gated == the header's total.
    items = _many(30)
    for k in range(c.GATED_COLLAPSE_THRESHOLD + 5):
        items.append({"id": "g%d" % k, "title": "Gated %d" % k, "surface_on": None,
                      "done": False, "tier": "gated", "gate_reason": "blocked"})
    surf = c.surfaceable(items, "2026-08-27")
    out = c.format_banner(surf)
    listed = len([l for l in out.splitlines() if l.startswith("  • ")])
    flat = _flat(out)
    unlisted = int(re.search(r"and (\d+) more open", flat).group(1))
    gated = int(re.search(r"⛔ (\d+) gated", flat).group(1))
    total = int(re.search(r"(\d+) open waypoint", flat).group(1))
    assert listed + unlisted + gated == total == len(surf)


def test_backup_stamp_carries_sub_second_precision():
    """Pinned separately from the collision test, which O_EXCL satisfies on its own.

    A stamp truncated to whole seconds still yields unique FILES (O_EXCL appends -NNN), so the
    collision test cannot see the difference — this is the assertion that actually holds the
    microsecond field in place.
    """
    when = datetime.datetime(2026, 8, 27, 12, 43, 58, 123456)
    assert c._backup_stamp(when) == "20260827-124358-123456"
    # and a stamp one microsecond apart must differ, i.e. precision is not decorative
    later = datetime.datetime(2026, 8, 27, 12, 43, 58, 123457)
    assert c._backup_stamp(when) != c._backup_stamp(later)


def test_collision_suffixes_sort_chronologically(tmp_path):
    # "-10" sorts before "-2" unpadded, which would make _existing_backups pick the wrong
    # "newest" snapshot and so compare the dedupe check against a stale file.
    bdir = tmp_path / "waypoints-backups"
    bdir.mkdir()
    names = []
    for n in range(12):
        path, fd = c._unique_backup_path(str(bdir), "waypoints", "20260827-124358-123456")
        os.close(fd)
        names.append(os.path.basename(path))
    ordered = [n for n, _, _ in c._existing_backups(str(bdir), "waypoints")]
    assert ordered == names, "creation order and sort order diverged: %r" % (ordered,)


# ---- v0.4.0: /ungate-queue is a SOFT dependency on another plugin ----

def test_gated_line_omits_ungate_queue_when_the_plugin_is_absent():
    out = c.format_banner(_with_gated(), ungate_hint=False)
    assert "/waypoints-gated" in _flat(out)      # our own command always shows
    assert "/ungate-queue" not in _flat(out)     # the sibling's does not
    # and the sentence still reads correctly, not as a truncated fragment
    assert "to see them and why." in _flat(out)


def test_gated_line_offers_ungate_queue_when_the_plugin_is_present():
    out = c.format_banner(_with_gated(), ungate_hint=True)
    assert "/ungate-queue" in _flat(out)
    assert "to see them and why, or `/ungate-queue`" in _flat(out)


def _fake_claude_dir(tmp_path, registry, settings=None, local=None):
    (tmp_path / "plugins").mkdir(exist_ok=True)
    (tmp_path / "plugins" / "installed_plugins.json").write_text(json.dumps(registry))
    if settings is not None:
        (tmp_path / "settings.json").write_text(json.dumps(settings))
    if local is not None:
        (tmp_path / "settings.local.json").write_text(json.dumps(local))
    return str(tmp_path)


def test_plugin_available_true_when_installed_and_enabled(tmp_path):
    root = _fake_claude_dir(
        tmp_path,
        {"version": 2, "plugins": {"run-to-completion@haiggoh": [{"scope": "user"}]}},
        {"enabledPlugins": {"run-to-completion@haiggoh": True}})
    assert c.plugin_available("run-to-completion", root) is True


def test_plugin_available_false_when_not_installed(tmp_path):
    root = _fake_claude_dir(tmp_path, {"version": 2, "plugins": {"something-else@haiggoh": []}})
    assert c.plugin_available("run-to-completion", root) is False


def test_plugin_available_false_when_installed_but_disabled(tmp_path):
    # installed != enabled: a user can switch a plugin off without uninstalling it, and its
    # commands go away with it.
    root = _fake_claude_dir(
        tmp_path,
        {"version": 2, "plugins": {"run-to-completion@haiggoh": [{"scope": "user"}]}},
        {"enabledPlugins": {"run-to-completion@haiggoh": False}})
    assert c.plugin_available("run-to-completion", root) is False


def test_local_settings_override_global_for_plugin_state(tmp_path):
    root = _fake_claude_dir(
        tmp_path,
        {"version": 2, "plugins": {"run-to-completion@haiggoh": [{"scope": "user"}]}},
        {"enabledPlugins": {"run-to-completion@haiggoh": True}},
        {"enabledPlugins": {"run-to-completion@haiggoh": False}})
    assert c.plugin_available("run-to-completion", root) is False


def test_plugin_available_fails_closed_on_a_missing_or_corrupt_registry(tmp_path):
    # Never advertise a command we cannot confirm exists.
    assert c.plugin_available("run-to-completion", str(tmp_path / "nope")) is False
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "installed_plugins.json").write_text("{ not json")
    assert c.plugin_available("run-to-completion", str(tmp_path)) is False


def test_banner_probes_the_machine_when_no_hint_is_given(tmp_path, monkeypatch):
    # The default path must actually consult the registry, not assume either answer.
    root = _fake_claude_dir(
        tmp_path,
        {"version": 2, "plugins": {"run-to-completion@haiggoh": [{"scope": "user"}]}},
        {"enabledPlugins": {"run-to-completion@haiggoh": True}})
    monkeypatch.setenv("WAYPOINTS_CLAUDE_DIR", root)
    assert "/ungate-queue" in _flat(c.format_banner(_with_gated()))
    (tmp_path / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {}}))
    assert "/ungate-queue" not in _flat(c.format_banner(_with_gated()))


# ---- the journal (0.5.0): append-only history ----
#
# The bar these hold: an entry must exist for EVERY mutation (a history with holes reads as
# complete and is worse than none), a bad line must not cost the rest of the file, and a
# journal failure must not fail the mutation it was recording.

def _jstore(tmp_path, monkeypatch, items=None):
    """Point the whole file family (store/archive/journal/backups) at tmp_path."""
    store = tmp_path / "s.json"
    monkeypatch.setenv("WAYPOINTS_FILE", str(store))
    c.save_store({"version": c.VERSION, "items": items or []}, argv=["setup"])
    return store


def test_journal_path_is_derived_from_the_store():
    # One env var must redirect the whole family, or a test writes history into the real journal.
    assert c.journal_path("/tmp/x/w.json") == "/tmp/x/w-journal.jsonl"


def test_diff_reports_an_added_item():
    ch = c.diff_items([], [{"id": "a", "title": "A"}])
    assert ch == [{"id": "a", "before": None, "after": {"id": "a", "title": "A"}}]


def test_diff_reports_a_removed_item():
    ch = c.diff_items([{"id": "a", "title": "A"}], [])
    assert len(ch) == 1 and ch[0]["after"] is None and ch[0]["before"]["id"] == "a"


def test_diff_reports_a_field_change_with_both_sides():
    ch = c.diff_items([{"id": "a", "done": False}], [{"id": "a", "done": True}])
    assert ch[0]["before"]["done"] is False and ch[0]["after"]["done"] is True


def test_diff_is_silent_when_nothing_changed():
    same = [{"id": "a", "title": "A"}]
    assert c.diff_items(same, list(same)) == []


def test_diff_catches_a_pure_reorder():
    # `reorder` changes no field, so a field-only differ would leave the command unrecorded.
    a, b = {"id": "a"}, {"id": "b"}
    ch = c.diff_items([a, b], [b, a])
    moved = {x["id"]: x.get("moved") for x in ch}
    assert moved == {"a": [0, 1], "b": [1, 0]}


def test_journal_entry_records_argv_verbatim():
    # Raw argv, not a rendered description: the literal command is the forensic artifact.
    e = c.journal_entry(["done", "some-id", "--as", "fixed it"], [], when="2026-08-27T10:00:00")
    assert e["argv"] == ["done", "some-id", "--as", "fixed it"]
    assert e["contract"] == c.JOURNAL_CONTRACT and e["at"] == "2026-08-27T10:00:00"


def test_journal_stamp_dates_from_today_so_the_clock_is_fakeable(monkeypatch):
    monkeypatch.setenv("WAYPOINTS_TODAY", "2020-01-02")
    assert c._journal_stamp().startswith("2020-01-02T")


def test_append_journal_appends_and_never_truncates(tmp_path):
    j = tmp_path / "j.jsonl"
    for n in range(3):
        c.append_journal(c.journal_entry(["cmd%d" % n], []), path=str(j))
    assert len(c.read_journal(path=str(j))) == 3


def test_journal_file_is_owner_only(tmp_path):
    j = tmp_path / "j.jsonl"
    c.append_journal(c.journal_entry(["x"], []), path=str(j))
    assert oct(os.stat(str(j)).st_mode & 0o777) == "0o600"


def test_read_journal_skips_a_corrupt_line_and_keeps_the_rest(tmp_path):
    # A crash mid-append leaves a partial tail; it must cost one entry, not the history.
    j = tmp_path / "j.jsonl"
    c.append_journal(c.journal_entry(["good-1"], []), path=str(j))
    with open(str(j), "a") as f:
        f.write('{"argv": ["truncated"\n')
        f.write("not json at all\n")
        f.write("\n")
    c.append_journal(c.journal_entry(["good-2"], []), path=str(j))
    got = [e["argv"][0] for e in c.read_journal(path=str(j))]
    assert got == ["good-1", "good-2"]


def test_read_journal_of_a_missing_file_is_empty_not_an_error(tmp_path):
    assert c.read_journal(path=str(tmp_path / "absent.jsonl")) == []


def test_read_journal_filters_by_item_id(tmp_path):
    j = tmp_path / "j.jsonl"
    c.append_journal(c.journal_entry(["a"], [{"id": "one", "before": None, "after": {}}]), path=str(j))
    c.append_journal(c.journal_entry(["b"], [{"id": "two", "before": None, "after": {}}]), path=str(j))
    got = [e["argv"][0] for e in c.read_journal(path=str(j), item_id="two")]
    assert got == ["b"]


def test_read_journal_filters_by_since_date(tmp_path):
    j = tmp_path / "j.jsonl"
    c.append_journal(c.journal_entry(["old"], [], when="2026-08-01T09:00:00"), path=str(j))
    c.append_journal(c.journal_entry(["new"], [], when="2026-08-27T09:00:00"), path=str(j))
    got = [e["argv"][0] for e in c.read_journal(path=str(j), since="2026-08-27")]
    assert got == ["new"]


def test_since_boundary_includes_the_whole_named_day(tmp_path):
    # "--since 2026-08-27" must not silently drop that day's own entries.
    j = tmp_path / "j.jsonl"
    c.append_journal(c.journal_entry(["midnight"], [], when="2026-08-27T00:00:00"), path=str(j))
    assert len(c.read_journal(path=str(j), since="2026-08-27")) == 1


def test_save_store_journals_the_change(tmp_path, monkeypatch):
    store = _jstore(tmp_path, monkeypatch)
    items = [{"id": "a", "title": "A"}]
    c.save_store({"version": c.VERSION, "items": items}, argv=["add", "A"])
    entries = c.read_journal(item_id="a")
    assert len(entries) == 1 and entries[0]["argv"] == ["add", "A"]
    assert entries[0]["source"] == "store"


def test_save_archive_journals_under_its_own_source(tmp_path, monkeypatch):
    # Tagging the source is what lets a MOVE (store-remove + archive-add) be told from a LOSS.
    _jstore(tmp_path, monkeypatch)
    c.save_archive({"version": c.VERSION, "items": [{"id": "a", "title": "A"}]}, argv=["prune"])
    entries = c.read_journal(item_id="a")
    assert [e["source"] for e in entries] == ["archive"]


def test_store_and_archive_share_one_journal(tmp_path, monkeypatch):
    # One file, so a move reads in order instead of being split across two histories.
    _jstore(tmp_path, monkeypatch)
    c.save_store({"version": c.VERSION, "items": [{"id": "a"}]}, argv=["add"])
    c.save_archive({"version": c.VERSION, "items": [{"id": "a"}]}, argv=["prune"])
    assert len(c.read_journal()) == 2


def test_a_no_op_save_earns_no_journal_entry(tmp_path, monkeypatch):
    store = _jstore(tmp_path, monkeypatch, [{"id": "a", "title": "A"}])
    before = len(c.read_journal())
    c.save_store({"version": c.VERSION, "items": [{"id": "a", "title": "A"}]}, argv=["edit"])
    assert len(c.read_journal()) == before


def test_save_store_defaults_argv_to_the_process_argv(tmp_path, monkeypatch):
    # No call site should have to remember to pass argv, or the next one will not.
    _jstore(tmp_path, monkeypatch)
    monkeypatch.setattr(c.sys, "argv", ["waypoints.py", "done", "some-id"])
    c.save_store({"version": c.VERSION, "items": [{"id": "z"}]})
    assert c.read_journal(item_id="z")[0]["argv"] == ["done", "some-id"]


def test_a_failing_journal_does_not_wedge_the_write(tmp_path, monkeypatch):
    # Insurance must not be able to break the thing it insures.
    store = _jstore(tmp_path, monkeypatch)
    monkeypatch.setattr(c, "append_journal", lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    with pytest.raises(OSError):
        c.append_journal({}, path="x")          # the fake really does raise
    c.save_store({"version": c.VERSION, "items": [{"id": "survivor"}]}, argv=["add"])
    assert [i["id"] for i in c.load_store()["items"]] == ["survivor"]


def test_append_journal_swallows_its_own_io_errors(tmp_path):
    # The real function, not a stub: an unwritable path must return None rather than raise.
    assert c.append_journal(c.journal_entry(["x"], []),
                            path=str(tmp_path / "nodir" / "sub" / "\x00bad.jsonl")) is None


def test_journal_is_never_pruned_by_the_backup_retention(tmp_path, monkeypatch):
    # The ring is bounded BECAUSE the journal is not; retention reaching it would undo that.
    store = _jstore(tmp_path, monkeypatch)
    for n in range(c.BACKUP_KEEP_RECENT + 12):
        c.save_store({"version": c.VERSION, "items": [{"id": "a", "n": n}]}, argv=["edit", str(n)])
    kept = len(c.read_journal())
    assert kept >= c.BACKUP_KEEP_RECENT + 12
    assert os.path.exists(c.journal_path())


def test_the_ring_is_ten_now_that_history_lives_in_the_journal():
    assert c.BACKUP_KEEP_RECENT == 10


# ---------------------------------------------------------------------------------------
# 0.6.0 -- the `waiting` tier: blocked on ANOTHER ITEM IN THIS STORE reaching a milestone.
# It earns a tier (rather than staying a prefix inside `gated`) only because the target is an
# id this store holds, so the store can re-check it for free and release the item itself.
# ---------------------------------------------------------------------------------------

def test_waiting_is_a_tier_and_its_own_partition_group():
    assert "waiting" in c.TIERS
    items = []
    c.add_item(items, "target")
    c.add_item(items, "dependent", tier="waiting", waiting_on="target @ phase 2 lands")
    g = c.partition(items)
    assert [i["id"] for i in g["waiting"]] == ["dependent"]
    # Its own group: NOT folded into either neighbour.
    assert g["actionable"] == [] and g["gated"] == []
    # And the sum invariant still lets a reader verify nothing was dropped.
    assert sum(len(v) for v in g.values()) == len(items)


def test_waiting_without_a_target_is_refused():
    # An untargeted "waiting" is exactly the unfalsifiable label this tier exists to replace.
    with pytest.raises(c.VerdictError):
        c.validate_verdict("waiting")


def test_waiting_target_must_name_a_milestone_not_just_an_item():
    # "when that item is done" is often NOT the trigger, so the milestone is required.
    with pytest.raises(c.VerdictError):
        c.validate_verdict("waiting", waiting_on="some-item")
    assert c.parse_waiting_on("some-item @ its API freezes") == [("some-item", "its API freezes")]
    # Surrounding whitespace is tolerated; the two halves are not.
    assert c.parse_waiting_on("  a-b  @   the thing  ") == [("a-b", "the thing")]


def test_a_waiting_target_on_a_non_waiting_item_is_refused():
    # Symmetric with the gate-reason rule: a record that disagrees with itself is refused.
    for tier in ("do-now", "heavy", "gated"):
        with pytest.raises(c.VerdictError):
            c.validate_verdict(tier, waiting_on="x @ y")


def test_gate_reason_and_waiting_on_cannot_both_apply():
    with pytest.raises(c.VerdictError):
        c.validate_verdict("waiting", gate_reason="needs a decision",
                           waiting_on="x @ y")


def test_retiering_away_from_waiting_drops_the_target():
    items = []
    c.add_item(items, "target")
    c.add_item(items, "dep", tier="waiting", waiting_on="target @ ships")
    c.set_verdict(items, "dep", tier="do-now")
    assert "waiting_on" not in items[1] and items[1]["tier"] == "do-now"


def test_clearing_the_verdict_leaves_no_tombstone():
    items = []
    c.add_item(items, "target")
    c.add_item(items, "dep", tier="waiting", waiting_on="target @ ships")
    c.set_verdict(items, "dep", tier=None)
    assert "tier" not in items[1] and "waiting_on" not in items[1]


def test_waiting_status_distinguishes_pending_landed_and_stale():
    items = []
    c.add_item(items, "target")
    c.add_item(items, "dep", tier="waiting", waiting_on="target @ ships")
    assert c.waiting_status(items[1], items)[0] == c.WAITING_PENDING
    items[0]["done"] = True
    assert c.waiting_status(items[1], items)[0] == c.WAITING_LANDED
    c.add_item(items, "orphan", tier="waiting", waiting_on="ghost @ never")
    # A target that does not exist is STALE, never landed: a renamed or mistyped id must not be
    # indistinguishable from the work having happened.
    assert c.waiting_status(items[2], items)[0] == c.WAITING_STALE


def test_an_archived_done_target_still_releases_its_dependent():
    items, archived = [], []
    c.add_item(archived, "target")
    archived[0]["done"] = True
    c.add_item(items, "dep", tier="waiting", waiting_on="target @ ships")
    assert c.waiting_status(items[0], items, archived)[0] == c.WAITING_LANDED


def test_promotion_clears_the_tier_rather_than_guessing_one():
    items = []
    c.add_item(items, "target")
    c.add_item(items, "dep", tier="waiting", waiting_on="target @ ships")
    items[0]["done"] = True
    promoted = c.promote_landed_waiting(items, today_str="2026-08-31")
    assert [i["id"] for i, _t, _m in promoted] == ["dep"]
    # UNTRIAGED, not do-now: the item's own weight was never assessed while it waited, so
    # inventing one would be a verdict nobody made.
    assert items[1].get("tier") is None and "waiting_on" not in items[1]
    # ...and the target it waited on is preserved in the summary, so dropping waiting_on does
    # not erase the only record of why it was parked.
    note = items[1]["summary"][-1]
    assert "RELEASED 2026-08-31" in note and "target @ ships" in note


def test_promotion_leaves_pending_and_stale_items_alone():
    items = []
    c.add_item(items, "target")
    c.add_item(items, "pending", tier="waiting", waiting_on="target @ ships")
    c.add_item(items, "orphan", tier="waiting", waiting_on="ghost @ never")
    assert c.promote_landed_waiting(items) == []
    assert items[1]["tier"] == "waiting" and items[2]["tier"] == "waiting"


def test_stale_waiting_reports_but_never_repairs():
    items = []
    c.add_item(items, "orphan", tier="waiting", waiting_on="ghost @ never")
    stale = c.stale_waiting(items)
    assert [(i["id"], t) for i, t in stale] == [("orphan", "ghost")]
    # Untouched: which side is wrong is not something the store can know.
    assert items[0]["tier"] == "waiting" and items[0]["waiting_on"] == ["ghost @ never"]


def test_done_items_are_not_reported_as_waiting():
    items = []
    c.add_item(items, "orphan", tier="waiting", waiting_on="ghost @ never")
    items[0]["done"] = True
    assert c.stale_waiting(items) == []
    assert c.promote_landed_waiting(items) == []


def test_list_payload_carries_waiting_and_keeps_the_sum_honest():
    items = []
    c.add_item(items, "target", tier="do-now")
    c.add_item(items, "dep", tier="waiting", waiting_on="target @ ships")
    c.add_item(items, "blocked", tier="gated", gate_reason="needs you")
    c.add_item(items, "fresh")
    p = c.list_payload(items)
    assert p["contract"] == 2
    counts = p["counts"]
    assert counts["waiting"] == 1
    assert (counts["gated"] + counts["waiting"] + counts["actionable"]
            + counts["untriaged"]) == counts["open"]
    row = [r for r in p["items"] if r["id"] == "dep"][0]
    # Present-and-null at the boundary, absent in the store: the same asymmetry as tier.
    assert row["waiting_on"] == ["target @ ships"]
    assert [r for r in p["items"] if r["id"] == "fresh"][0]["waiting_on"] is None


def test_banner_resolves_waiting_targets_against_the_whole_store_not_the_display_list():
    # Regression: the banner is handed only the SURFACEABLE items, so a landed (therefore done)
    # target is absent from that list. Resolving against it reported every landed target as
    # missing -- inverting the one signal the reader most needs.
    items = []
    c.add_item(items, "target")
    c.add_item(items, "dep", tier="waiting", waiting_on="target @ ships")
    items[0]["done"] = True
    display = [i for i in items if not i.get("done")]
    assert "can move NOW" not in c.format_banner(display, ungate_hint=False)
    assert "can move NOW" in c.format_banner(display, ungate_hint=False, all_items=items)


# ---------------------------------------------------------------------------------------
# Multiple targets. Not hypothetical: of the first fifteen real items migrated into this tier,
# three waited on two-to-four others at once, so a single-target field would have forced either
# an ungroundable guess about which dependency binds last, or leaving a fifth of the pile behind.
# ---------------------------------------------------------------------------------------

def test_waiting_on_is_stored_as_a_list_even_for_one_target():
    items = []
    c.add_item(items, "t")
    c.add_item(items, "dep", tier="waiting", waiting_on="t @ ships")
    assert items[1]["waiting_on"] == ["t @ ships"], "one shape on disk, always a list"


def test_several_targets_release_only_when_ALL_have_landed():
    items = []
    c.add_item(items, "a")
    c.add_item(items, "b")
    c.add_item(items, "dep", tier="waiting",
               waiting_on=["a @ its API freezes", "b @ the matrix is decided"])
    assert c.waiting_status(items[2], items)[0] == c.WAITING_PENDING
    items[0]["done"] = True
    # One of two is NOT unblocked -- an item blocked on two things is not freed by one of them.
    assert c.waiting_status(items[2], items)[0] == c.WAITING_PENDING
    assert c.promote_landed_waiting(items) == []
    items[1]["done"] = True
    assert c.waiting_status(items[2], items)[0] == c.WAITING_LANDED
    promoted = c.promote_landed_waiting(items, today_str="2026-09-01")
    assert [i["id"] for i, _t, _m in promoted] == ["dep"]
    # The release note names EVERY target, not just the one that happened to be reported.
    note = items[2]["summary"][-1]
    assert "a @ its API freezes" in note and "b @ the matrix is decided" in note


def test_one_missing_target_makes_the_whole_spec_stale():
    items = []
    c.add_item(items, "a")
    items[0]["done"] = True
    c.add_item(items, "dep", tier="waiting", waiting_on=["a @ ships", "ghost @ never"])
    status, target, _m = c.waiting_status(items[1], items)
    # Stale dominates: the store disagrees with itself, so no partial answer is trustworthy --
    # and it must NOT read as landed just because the surviving target happens to be done.
    assert status == c.WAITING_STALE and target == "ghost"
    assert [i["id"] for i, _t in c.stale_waiting(items)] == ["dep"]
    assert c.promote_landed_waiting(items) == []


def test_the_reported_target_explains_the_verdict():
    items = []
    c.add_item(items, "a")
    c.add_item(items, "b")
    items[0]["done"] = True
    c.add_item(items, "dep", tier="waiting", waiting_on=["a @ done already", "b @ still open"])
    status, target, milestone = c.waiting_status(items[2], items)
    # The still-PENDING one is named, not the already-landed one: a caller needs something
    # specific to show, and "a" would be actively misleading here.
    assert (status, target, milestone) == (c.WAITING_PENDING, "b", "still open")


def test_every_target_must_carry_a_milestone():
    with pytest.raises(c.VerdictError):
        c.validate_verdict("waiting", waiting_on=["good-one @ a real milestone", "bare-id"])


def test_an_empty_target_list_is_refused():
    with pytest.raises(c.VerdictError):
        c.validate_verdict("waiting", waiting_on=[])


def test_waiting_targets_reports_each_target_separately():
    items = []
    c.add_item(items, "a")
    c.add_item(items, "b")
    items[0]["done"] = True
    c.add_item(items, "dep", tier="waiting", waiting_on=["a @ x", "b @ y", "ghost @ z"])
    detail = c.waiting_targets(items[2], items)
    assert [(t, st) for t, _m, st in detail] == [
        ("a", c.WAITING_LANDED), ("b", c.WAITING_PENDING), ("ghost", c.WAITING_STALE)]


def test_waiting_on_str_is_one_readable_line():
    items = []
    c.add_item(items, "dep", tier="waiting", waiting_on=["a @ x", "b @ y"])
    assert c.waiting_on_str(items[0]) == "a @ x + b @ y"
