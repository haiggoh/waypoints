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
