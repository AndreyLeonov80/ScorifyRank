from app.services import telegram_sources_runtime as sources


def test_selector_lookup_maps_are_cached_for_repeated_membership_calls(monkeypatch):
    calls = {"build": 0}

    def build_maps():
        calls["build"] += 1
        return {
            "source": {"added": "@added", "plain_group": "plain_group"},
            "import_sync": {"imported": "@imported"},
            "managed": {
                "added": "@added",
                "plain_group": "plain_group",
                "imported": "@imported",
                "known": "@known",
            },
        }

    monkeypatch.setattr(sources, "_build_selector_lookup_maps", build_maps, raising=False)
    sources._invalidate_selector_lookup_cache.__wrapped__()

    maps = sources._selector_lookup_maps.__wrapped__()
    assert maps["source"] == {"added": "@added", "plain_group": "plain_group"}
    assert maps["import_sync"] == {"imported": "@imported"}
    assert maps["managed"] == {
        "added": "@added",
        "plain_group": "plain_group",
        "imported": "@imported",
        "known": "@known",
    }

    assert calls == {"build": 1}

    assert sources._selector_lookup_maps.__wrapped__()["managed"]["known"] == "@known"
    assert calls == {"build": 1}

    sources._invalidate_selector_lookup_cache.__wrapped__()
    sources._selector_lookup_maps.__wrapped__()

    assert calls == {"build": 2}
