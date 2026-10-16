import json

import pytest

from novel.run_store import ConfigurationError, RunStore, configuration_hash


def test_novel_store_atomic_files_and_unicode(tmp_path):
    store = RunStore(tmp_path, {"experiment": "A"}, dry_run=True)
    store.write_json("nested/step.json", {"正文": "银色发夹"})
    store.write_text("nested/chapter.md", "# 第一章\n正文")
    assert store.read_json("nested/step.json") == {"正文": "银色发夹"}
    assert (tmp_path / "nested/chapter.md").read_text() == "# 第一章\n正文"
    assert not list(tmp_path.rglob(".*.json.*"))


@pytest.mark.parametrize("path", ["../escape.json", "/tmp/escape.json", "nested/../../escape.json"])
def test_novel_store_rejects_path_escape(tmp_path, path):
    store = RunStore(tmp_path, {})
    with pytest.raises(ValueError):
        store.write_json(path, {})


def test_novel_store_rejects_symlink_escape(tmp_path):
    output = tmp_path / "run"
    store = RunStore(output, {})
    (output / "escaped").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        store.write_text("escaped/secret", "forbidden")


def test_novel_store_hash_is_canonical_and_budget_independent():
    assert configuration_hash({"a": 1, "b": 2}) == configuration_hash({"b": 2, "a": 1})
    assert configuration_hash({"a": 1, "max_total_tokens": 100}) == configuration_hash({"a": 1, "max_total_tokens": 500})
    assert configuration_hash({"a": 1}, dry_run=True) != configuration_hash({"a": 1}, dry_run=False)


def test_novel_store_resume_checks_hash_but_allows_budget_change(tmp_path):
    first = RunStore(tmp_path, {"experiment": "B"}, dry_run=True, max_total_tokens=10)
    first.set_status("budget_exhausted", stopped_chapter=3)
    resumed = RunStore(tmp_path, {"experiment": "B"}, dry_run=True, max_total_tokens=100)
    assert resumed.manifest["started_at"] == first.manifest["started_at"]
    assert resumed.manifest["stopped_chapter"] == 3
    with pytest.raises(ConfigurationError, match="配置已变化"):
        RunStore(tmp_path, {"experiment": "C"}, dry_run=True)
    with pytest.raises(ConfigurationError, match="配置已变化"):
        RunStore(tmp_path, {"experiment": "B"}, dry_run=False)


def test_novel_store_usage_survives_resume(tmp_path):
    first = RunStore(tmp_path, {})
    first.append_usage({"input_tokens": 7, "output_tokens": 9, "cached_tokens": 2})
    second = RunStore(tmp_path, {})
    assert second.total_tokens == 16
    assert second.usage == first.usage
    assert len((tmp_path / "usage.jsonl").read_text().splitlines()) == 1


def test_novel_store_status_records_finish_and_restart(tmp_path):
    store = RunStore(tmp_path, {})
    store.set_status("completed", chapter=9)
    assert store.read_json("manifest.json")["finished_at"]
    store.set_status("running")
    assert store.manifest["finished_at"] is None
    assert store.manifest["chapter"] == 9


def test_novel_store_rejects_corrupt_usage(tmp_path):
    RunStore(tmp_path, {})
    (tmp_path / "usage.jsonl").write_text("not json\n")
    with pytest.raises(ConfigurationError, match="用量记录损坏"):
        RunStore(tmp_path, {})


@pytest.mark.parametrize("budget", [-1, True, "100"])
def test_novel_store_rejects_invalid_budget(tmp_path, budget):
    with pytest.raises(ConfigurationError):
        RunStore(tmp_path, {}, max_total_tokens=budget)
