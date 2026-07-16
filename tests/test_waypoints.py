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
