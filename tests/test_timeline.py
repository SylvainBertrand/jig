"""Tests for jig.core.timeline.TimelineController."""

import pytest

from jig.core.timeline import TimelineController


@pytest.fixture
def tc():
    return TimelineController()


class TestTimeRange:
    def test_default_range(self, tc: TimelineController):
        assert tc.t_min == 0.0
        assert tc.t_max == 0.0
        assert tc.duration == 0.0

    def test_set_range(self, tc: TimelineController):
        tc.set_range(1.0, 10.0)
        assert tc.t_min == 1.0
        assert tc.t_max == 10.0
        assert tc.duration == 9.0

    def test_set_range_clamps_current_time(self, tc: TimelineController):
        tc.set_range(0.0, 10.0)
        tc.set_time(5.0)
        tc.set_range(6.0, 10.0)
        assert tc.current_time == 6.0


class TestSetTime:
    def test_basic(self, tc: TimelineController):
        tc.set_range(0.0, 10.0)
        tc.set_time(5.0)
        assert tc.current_time == 5.0

    def test_clamp_low(self, tc: TimelineController):
        tc.set_range(2.0, 8.0)
        tc.set_time(0.0)
        assert tc.current_time == 2.0

    def test_clamp_high(self, tc: TimelineController):
        tc.set_range(2.0, 8.0)
        tc.set_time(100.0)
        assert tc.current_time == 8.0

    def test_signal_emitted(self, tc: TimelineController):
        tc.set_range(0.0, 10.0)
        received = []
        tc.time_changed.connect(lambda t: received.append(t))
        tc.set_time(3.0)
        assert received == [3.0]

    def test_no_signal_on_same_value(self, tc: TimelineController):
        tc.set_range(0.0, 10.0)
        tc.set_time(5.0)
        received = []
        tc.time_changed.connect(lambda t: received.append(t))
        tc.set_time(5.0)
        assert received == []


class TestPlayback:
    def test_default_not_playing(self, tc: TimelineController):
        assert tc.playing is False

    def test_set_playing(self, tc: TimelineController):
        received = []
        tc.playback_changed.connect(lambda p: received.append(p))
        tc.set_playing(True)
        assert tc.playing is True
        assert received == [True]

    def test_toggle(self, tc: TimelineController):
        tc.toggle_playing()
        assert tc.playing is True
        tc.toggle_playing()
        assert tc.playing is False

    def test_no_signal_on_same_state(self, tc: TimelineController):
        received = []
        tc.playback_changed.connect(lambda p: received.append(p))
        tc.set_playing(False)  # already False
        assert received == []
