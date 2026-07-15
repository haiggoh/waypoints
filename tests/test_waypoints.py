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


def test_format_banner_lists_titles_and_ids():
    b = c.format_banner([{"id": "x1", "title": "Do the thing", "surface_on": None, "done": False}])
    assert "waypoint" in b.lower()
    assert "Do the thing" in b
    assert "x1" in b


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
    assert len(s) <= 50
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
