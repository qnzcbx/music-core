"""本机启动器的所有权边界；实际 VBS/服务验证见归档记录。"""
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import launch_local as launcher


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "STATE", tmp_path / "processes.json")
    return launcher.load_state()


def identity(pid=100, parent=1, created="1000"):
    return {"pid": pid, "parent": parent, "created": created,
            "exe": "C:/project/python.exe", "command": "python app.py"}


@pytest.mark.parametrize("field,value", [("created", "2000"), ("exe", "other.exe"),
                                         ("command", "other app"), ("pid", 101)])
def test_changed_identity_never_opens_process(monkeypatch, field, value):
    original = identity()
    current = dict(original, **{field: value})
    kernel = Mock()
    monkeypatch.setattr(launcher, "kernel_api", lambda: kernel)
    assert launcher.verified_handle(original, {100: current}) is None
    kernel.OpenProcess.assert_not_called()


def test_handle_creation_time_is_rechecked(monkeypatch):
    original = identity()
    kernel = Mock()
    kernel.OpenProcess.return_value = 50
    monkeypatch.setattr(launcher, "kernel_api", lambda: kernel)
    monkeypatch.setattr(launcher, "creation_time", lambda handle: "2000")
    assert launcher.verified_handle(original, {100: original}) is None
    kernel.CloseHandle.assert_called_once_with(50)


def test_unrecorded_and_reused_services_are_not_stopped(registry, monkeypatch):
    registry["services"]["web"] = {"owned": False}
    launcher.save_state(registry)
    monkeypatch.setattr(launcher, "snapshot", lambda: {})
    kernel = Mock()
    monkeypatch.setattr(launcher, "kernel_api", lambda: kernel)
    message = launcher.stop_owned()
    assert "保留" in message
    kernel.TerminateProcess.assert_not_called()
    kernel.AttachConsole.assert_not_called()


def test_recycled_parent_pid_does_not_adopt_its_children(registry, monkeypatch):
    root = identity()
    unrelated = identity(200, parent=100, created="3000")
    entry = {"owned": True, "root": root}
    monkeypatch.setattr(launcher, "verified_handle", lambda member, processes: None)
    assert launcher.collect_members(entry, {100: dict(root, created="2000"), 200: unrelated}) == [root]


def test_recorded_child_survives_missing_parent(registry, monkeypatch):
    root, child = identity(), identity(200, parent=100, created="2000")
    registry["services"]["backend"] = {"owned": True, "root": root, "members": [root, child]}
    launcher.save_state(registry)
    monkeypatch.setattr(launcher, "snapshot", lambda: {200: child})
    monkeypatch.setattr(launcher, "verified_handle", lambda member, processes: 20 if member == child else None)
    shutdown = Mock()
    monkeypatch.setattr(launcher, "request_shutdown", shutdown)
    kernel = Mock()
    kernel.WaitForSingleObject.return_value = 0
    monkeypatch.setattr(launcher, "kernel_api", lambda: kernel)
    assert "已停止" in launcher.stop_owned(["backend"])
    shutdown.assert_called_once_with(200, {200})
    assert "无需重复" in launcher.stop_owned(["backend"])
    assert shutdown.call_count == 1


def test_registry_for_another_project_is_rejected(registry):
    registry["project"] = "C:/another-project"
    launcher.save_state(registry)
    with pytest.raises(RuntimeError, match="不属于当前项目"):
        launcher.load_state()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console API")
@pytest.mark.parametrize("unverified_pid", [False, True])
def test_console_broadcast_requires_every_member_verified(monkeypatch, unverified_pid):
    kernel = Mock()
    kernel.AttachConsole.return_value = True
    def console_members(buffer, length):
        buffer[0] = 100
        buffer[1] = 200 if unverified_pid else launcher.os.getpid()
        return 2
    kernel.GetConsoleProcessList.side_effect = console_members
    monkeypatch.setattr(launcher, "kernel_api", lambda: kernel)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    launcher.request_shutdown(100, {100})
    assert kernel.GenerateConsoleCtrlEvent.call_count == (0 if unverified_pid else 1)
    kernel.FreeConsole.assert_called()


def test_reused_manual_service_stays_unowned(registry, monkeypatch):
    monkeypatch.setattr(launcher, "snapshot", Mock(side_effect=AssertionError("should not inspect unowned service")))
    launcher.remember_reused("web")
    assert launcher.load_state()["services"]["web"] == {"owned": False}


def test_previously_owned_service_remains_owned_on_reopen(registry, monkeypatch):
    root = identity()
    registry["services"]["web"] = {"owned": True, "root": root, "members": [root]}
    launcher.save_state(registry)
    monkeypatch.setattr(launcher, "snapshot", lambda: {100: root})
    monkeypatch.setattr(launcher, "verified_handle", lambda member, processes: 10)
    monkeypatch.setattr(launcher, "kernel_api", Mock())
    launcher.remember_reused("web")
    assert launcher.load_state()["services"]["web"]["owned"] is True
