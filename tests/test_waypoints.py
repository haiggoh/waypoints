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


def test_prune_removes_done():
    items = [{"id": "a", "done": False, "title": "A", "surface_on": None},
             {"id": "b", "done": True, "title": "B", "surface_on": None}]
    kept = c.prune(items)
    assert [i["id"] for i in kept] == ["a"]


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
    assert c.validate_verdict("gated", "needs a decision") == ("gated", "needs a decision")


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
