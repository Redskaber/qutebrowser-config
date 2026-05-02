"""
tests/test_incremental.py
=========================
Tests for the incremental diff/snapshot system.
"""

from __future__ import annotations

import sys
import os
from typing import Any, List
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfigSnapshot(unittest.TestCase):

    def setUp(self):
        from core.incremental import ConfigSnapshot
        self.Snapshot = ConfigSnapshot

    def test_deep_copy_on_init(self):
        data = {"a": [1, 2, 3]}
        snap = self.Snapshot(data=data)
        data["a"].append(99)          # mutate original
        self.assertEqual(snap.data["a"], [1, 2, 3])  # snapshot unchanged

    def test_version_tracking(self):
        s = self.Snapshot(data={"x": 1}, version=5)
        self.assertEqual(s.version, 5)

    def test_get(self):
        s = self.Snapshot(data={"key": "val"})
        self.assertEqual(s.get("key"), "val")
        self.assertIsNone(s.get("missing"))
        self.assertEqual(s.get("missing", "default"), "default")


class TestConfigDiffer(unittest.TestCase):

    def setUp(self):
        from core.incremental import ConfigDiffer, ConfigSnapshot, ChangeKind
        self.Differ = ConfigDiffer
        self.Snapshot = ConfigSnapshot
        self.ChangeKind = ChangeKind

    def _snap(self, data: dict[str, Any]):
        return self.Snapshot(data=data)

    def test_no_changes(self):
        old = self._snap({"a": 1, "b": 2})
        new = self._snap({"a": 1, "b": 2})
        changes = self.Differ.diff(old, new)
        self.assertEqual(len(changes), 0)

    def test_added_key(self):
        old = self._snap({"a": 1})
        new = self._snap({"a": 1, "b": 2})
        changes = self.Differ.diff(old, new)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, self.ChangeKind.ADDED)
        self.assertEqual(changes[0].key, "b")

    def test_removed_key(self):
        old = self._snap({"a": 1, "b": 2})
        new = self._snap({"a": 1})
        changes = self.Differ.diff(old, new)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, self.ChangeKind.REMOVED)

    def test_changed_key(self):
        old = self._snap({"a": 1})
        new = self._snap({"a": 99})
        changes = self.Differ.diff(old, new)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, self.ChangeKind.CHANGED)
        self.assertEqual(changes[0].old_value, 1)
        self.assertEqual(changes[0].new_value, 99)

    def test_include_same(self):
        old = self._snap({"a": 1})
        new = self._snap({"a": 1})
        changes = self.Differ.diff(old, new, include_same=True)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, self.ChangeKind.SAME)

    def test_summary_format(self):
        old = self._snap({"a": 1, "b": 2, "c": 3})
        new = self._snap({"a": 1, "b": 99, "d": 4})
        changes = self.Differ.diff(old, new)
        summary = self.Differ.summary(changes)
        self.assertIn("+", summary)
        self.assertIn("-", summary)
        self.assertIn("~", summary)


class TestSnapshotStore(unittest.TestCase):

    def setUp(self):
        from core.incremental import SnapshotStore
        self.Store = SnapshotStore

    def test_empty_store(self):
        store = self.Store()
        self.assertIsNone(store.current())
        self.assertIsNone(store.previous())

    def test_push_and_current(self):
        store = self.Store()
        snap = store.push({"x": 1}, label="init")
        self.assertEqual(store.current(), snap)
        self.assertEqual(store.version, 1)

    def test_push_increments_version(self):
        store = self.Store()
        store.push({"a": 1})
        store.push({"a": 2})
        self.assertEqual(store.version, 2)

    def test_max_history_respected(self):
        store = self.Store(max_history=3)
        for i in range(10):
            store.push({"i": i})
        self.assertEqual(len(store), 3)

    def test_diff_last_two(self):
        from core.incremental import ChangeKind
        store = self.Store()
        store.push({"a": 1, "b": 2})
        store.push({"a": 1, "b": 99})
        changes = store.diff_last_two()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].kind, ChangeKind.CHANGED)

    def test_at_version(self):
        store = self.Store()
        s1 = store.push({"a": 1})
        s2 = store.push({"a": 2})
        self.assertEqual(store.at(1), s1)
        self.assertEqual(store.at(2), s2)
        self.assertIsNone(store.at(99))


class TestIncrementalApplier(unittest.TestCase):

    def setUp(self):
        from core.incremental import IncrementalApplier, SnapshotStore
        self.store = SnapshotStore()
        self.applier = IncrementalApplier(self.store)

    def test_apply_only_changed(self):
        applied: dict[str, Any] = {}
        def apply_fn(key: str, value: Any):
            applied[key] = value

        self.applier.record({"a": 1, "b": 2}, "v1")
        self.applier.record({"a": 1, "b": 99, "c": 3}, "v2")
        changes = self.applier.compute_delta()
        self.applier.apply_delta(changes, apply_fn)

        # "a" was unchanged, should NOT be in applied
        self.assertNotIn("a", applied)
        # "b" changed
        self.assertIn("b", applied)
        self.assertEqual(applied["b"], 99)
        # "c" was added
        self.assertIn("c", applied)

    def test_observer_called_on_changes(self):
        def apply_fn(k: Any, v: Any) -> None:
            pass
        observed: List[Any] = []
        self.applier.on_changes(observed.append)
        self.applier.record({"x": 1}, "v1")
        self.applier.record({"x": 2}, "v2")
        changes = self.applier.compute_delta()
        self.applier.apply_delta(changes, apply_fn)
        self.assertEqual(len(observed), 1)

    def test_apply_fn_exception_returns_error(self):
        def bad_apply(key: str, value: Any):
            raise ValueError("boom")

        self.applier.record({"a": 1}, "v1")
        self.applier.record({"a": 2}, "v2")
        changes = self.applier.compute_delta()
        errors = self.applier.apply_delta(changes, bad_apply)
        self.assertTrue(len(errors) > 0)


class TestLifecycleManager(unittest.TestCase):

    def setUp(self):
        from core.lifecycle import LifecycleManager, LifecycleHook
        self.Manager = LifecycleManager
        self.Hook = LifecycleHook

    def test_register_and_run(self):
        mgr = self.Manager()
        called: List[str] = []
        mgr.register(self.Hook.PRE_APPLY, lambda: called.append("a"))
        mgr.register(self.Hook.PRE_APPLY, lambda: called.append("b"))
        mgr.run(self.Hook.PRE_APPLY)
        self.assertEqual(called, ["a", "b"])

    def test_priority_ordering(self):
        mgr = self.Manager()
        called: List[str] = []
        mgr.register(self.Hook.PRE_APPLY, lambda: called.append("low"),  priority=90)
        mgr.register(self.Hook.PRE_APPLY, lambda: called.append("high"), priority=10)
        mgr.run(self.Hook.PRE_APPLY)
        self.assertEqual(called, ["high", "low"])

    def test_error_in_handler_doesnt_stop_others(self):
        mgr = self.Manager()
        called: List[int] = []
        def bad(): raise RuntimeError("oops")
        mgr.register(self.Hook.PRE_APPLY, bad,                      priority=10)
        mgr.register(self.Hook.PRE_APPLY, lambda: called.append(1), priority=20)
        mgr.run(self.Hook.PRE_APPLY)
        self.assertEqual(called, [1])

    def test_decorator(self):
        mgr = self.Manager()
        called: List[bool] = []

        @mgr.decorator(self.Hook.POST_APPLY)
        def my_hook(): # type: ignore
            called.append(True)

        mgr.run(self.Hook.POST_APPLY)
        self.assertTrue(called)


class TestCommandBus(unittest.TestCase):

    def setUp(self):
        from core.protocol import CommandBus, SetOptionCommand
        self.CommandBus = CommandBus
        self.SetOptionCommand = SetOptionCommand

    def test_dispatch_to_handler(self):
        bus = self.CommandBus()
        received: List[Any] = []
        bus.register(self.SetOptionCommand, received.append)
        cmd = self.SetOptionCommand(key="test.key", value=42)
        bus.dispatch(cmd)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].key, "test.key")

    def test_no_handler_raises(self):
        bus = self.CommandBus()
        with self.assertRaises(LookupError):
            bus.dispatch(self.SetOptionCommand())

    def test_duplicate_handler_raises(self):
        bus = self.CommandBus()
        bus.register(self.SetOptionCommand, lambda c: None)
        with self.assertRaises(ValueError):
            bus.register(self.SetOptionCommand, lambda c: None)


if __name__ == "__main__":
    print("=" * 60)
    print("Incremental + Extended Architecture Tests")
    print("=" * 60)
    unittest.main(verbosity=2)


