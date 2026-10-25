"""A scripted, repeatable demo for presentations: one 7 minute loop of a person on the mat. Frames go through the real
pipeline (MatEngine -> risk, alerts, history, repositioning counters), nothing is faked after the engine.

    0-20 s empty   20-30 sits down   30-90 settles (centred)   90-262 pressure builds under the left side
    (risk climbs, an alert is raised)   262-274 lifts off the mat, then sits back leaning right (relief, alert clears)
    274-340 settled on the right   340-355 stands up   355-420 empty, then the loop starts again.

Times are on the demo clock (a speed factor makes it run faster). Values are raw 0-1000 grids (20 raw = 1 kPa on the
demo calibration)."""

import numpy as np

import config

PERIOD_S = 420.0
ROWS = COLS = 20
RAW_PER_KPA = config.VALUE_MAX_DEFAULT / config.PRESSURE_DISPLAY_MAX_KPA
DEMO_RELIEF_MIN = 2.0   # the demo's "time without relief that counts as full risk" (minutes of demo clock)
YY, XX = np.mgrid[0:ROWS, 0:COLS]


def _blob(row, col, kpa, sigma=1.6):
    return kpa * RAW_PER_KPA * np.exp(-((YY - row) ** 2 + (XX - col) ** 2) / (2 * sigma ** 2))


def _ramp(t, start, end):
    return float(np.clip((t - start) / (end - start), 0.0, 1.0))


def scenario_grid(t, seed=0):
    """The raw grid at scenario time t (any float, wraps every PERIOD_S). Column 0 is the sitter's right."""
    t = (t + seed) % PERIOD_S
    lift = _ramp(t, 262, 264) * (1 - _ramp(t, 272, 274))          # off the mat for ~8 s: every cell is relieved
    presence = _ramp(t, 20, 30) * (1 - _ramp(t, 340, 355)) * (1 - lift)
    grid = _blob(13, 9.5, 5.0, 3.0)                                   # thighs
    if t < 268:                                                   # first position, centred; the left side builds up
        grid += _blob(10, 6, 14.0) + _blob(10, 13, 14 + 30 * _ramp(t, 90, 150))
    else:                                                         # leans right and forward, other cells carry the load
        grid += _blob(12, 4, 20.0) + _blob(12, 9, 12.0)
    noise = np.random.default_rng(int(t * 4) + seed).random((ROWS, COLS)) * 8.0                  # < 0.5 kPa: below contact
    return np.clip(grid * presence + noise, 0, config.VALUE_MAX_DEFAULT)


class ScenarioMat:
    """Feed for the server (take() -> (grid, demo time)); same interface as DemoMat. `offset_s` shifts the phase."""

    def __init__(self, offset_s=0.0, speed=1.0, wall=None):
        import time
        self.wall = wall or time.time
        self.offset_s, self.speed = offset_s, speed
        self.t0 = self.wall()

    def clock(self):
        return self.t0 + (self.wall() - self.t0) * self.speed

    def take(self):
        t = self.clock()
        return scenario_grid(self.offset_s + t - self.t0), t


def frames(seconds=PERIOD_S, fps=4.0, offset_s=0.0):
    """(grids, timestamps) of one loop, for tools/publish_demo_mat.py --scenario"""
    times = [i / fps for i in range(int(seconds * fps))]
    return [scenario_grid(offset_s + t) for t in times], times
