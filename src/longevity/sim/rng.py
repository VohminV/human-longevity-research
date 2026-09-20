from __future__ import annotations

import random

from typing import Any


class Rng:
    """Injectable, serializable source of randomness.

    The engine never touches global random: everything flows through an
    instance constructed with a `seed` (part of the experiment config) or
    handed in from elsewhere. `getstate/setstate` support checkpoint/restore.
    """

    def __init__(self, seed: int = 0, generator: random.Random | None = None):
        self.seed = seed
        self._generator = generator if generator is not None else random.Random(seed)

    def random(self) -> float:
        return self._generator.random()

    def gauss(self, mu: float, sigma: float) -> float:
        return self._generator.gauss(mu, sigma)

    def uniform(self, a: float, b: float) -> float:
        return self._generator.uniform(a, b)

    def getstate(self) -> tuple[Any, ...]:
        return (self.seed, self._generator.getstate())

    def setstate(self, state: tuple[Any, ...]) -> None:
        self.seed, generator_state = state
        self._generator.setstate(generator_state)


def state_to_json(state: tuple[Any, ...]) -> list[Any]:
    """Convert an RNG generator state into JSON-safe lists."""
    version, internal_state, gauss_next = state
    return [version, list(internal_state), gauss_next]


def state_from_json(data: list[Any]) -> tuple[Any, ...]:
    """Restore an RNG generator state from JSON-safe lists."""
    version, internal_state, gauss_next = data
    return (version, tuple(internal_state), gauss_next)