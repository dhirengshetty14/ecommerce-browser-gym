"""Shared pytest fixtures. Pure-logic tests — no browser needed."""

from __future__ import annotations

import copy
import pytest

from server.state import GymState
from server.tasks import TASKS, make_task


@pytest.fixture
def task_id_list() -> list[str]:
    return list(TASKS.keys())


@pytest.fixture
def fresh_state():
    def _make(task_id: str, seed: int = 0) -> GymState:
        return make_task(task_id, seed)
    return _make


@pytest.fixture
def initial_and_state(fresh_state):
    def _make(task_id: str, seed: int = 0):
        s = fresh_state(task_id, seed)
        initial = copy.deepcopy(s)
        return initial, s
    return _make
