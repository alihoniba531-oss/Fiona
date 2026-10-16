"""Frontend probes skip before launching Node when their dependencies are absent."""
import shutil

import pytest

import test_studio_frontend_components as components
import test_studio_frontend_navigation as navigation
import test_studio_frontend_shell as shell


COMPONENT_DEPENDENCIES = {
    "typescript": "typescript/lib/typescript.js",
    "react": "react/index.js",
    "react/jsx-runtime": "react/jsx-runtime.js",
    "react-dom/server": "react-dom/server.js",
}


def forbid_node(monkeypatch, module, root):
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(shutil, "which", lambda executable: "/offline/node")

    def unexpected_node(*args, **kwargs):
        pytest.fail("Node must not run without the required frontend dependencies")

    monkeypatch.setattr(module.subprocess, "run", unexpected_node)


@pytest.mark.parametrize("module", [shell, navigation, components], ids=["shell", "navigation", "components"])
def test_probe_skips_without_frontend_node_modules(monkeypatch, tmp_path, module):
    forbid_node(monkeypatch, module, tmp_path)

    with pytest.raises(pytest.skip.Exception, match="frontend dependencies unavailable:.*typescript"):
        module.probe("process.stdout.write('true');")


@pytest.mark.parametrize("missing", COMPONENT_DEPENDENCIES)
def test_component_probe_skips_each_missing_dependency(monkeypatch, tmp_path, missing):
    for name, relative_path in COMPONENT_DEPENDENCIES.items():
        entry = tmp_path / "frontend" / "node_modules" / relative_path
        entry.parent.mkdir(parents=True, exist_ok=True)
        if name != missing:
            entry.write_text("", encoding="utf-8")
    forbid_node(monkeypatch, components, tmp_path)

    with pytest.raises(pytest.skip.Exception) as skipped:
        components.probe("process.stdout.write('true');")

    assert str(skipped.value) == f"frontend dependencies unavailable: {missing}"


@pytest.mark.parametrize("module", [shell, navigation], ids=["shell", "navigation"])
def test_probe_skips_when_typescript_directory_has_no_entry(monkeypatch, tmp_path, module):
    (tmp_path / "frontend" / "node_modules" / "typescript").mkdir(parents=True)
    forbid_node(monkeypatch, module, tmp_path)

    with pytest.raises(pytest.skip.Exception, match="frontend dependencies unavailable: typescript"):
        module.probe("process.stdout.write('true');")
