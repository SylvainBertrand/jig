"""Tests for jig.core.data_store.DataStore."""

import numpy as np
import pytest

from jig.core.data_store import DataStore
from jig.core.types import TopicInfo


@pytest.fixture
def ds():
    return DataStore()


class TestAddSeries:
    def test_add_and_retrieve(self, ds: DataStore):
        ts = np.array([0.0, 1.0, 2.0])
        vals = np.array([10.0, 20.0, 30.0])
        ds.add_series("/topic/field", ts, vals)

        series = ds.get_series("/topic/field")
        assert series is not None
        assert series.name == "/topic/field"
        assert len(series) == 3
        np.testing.assert_array_equal(series.timestamps, ts)
        np.testing.assert_array_equal(series.values, vals)

    def test_get_missing_returns_none(self, ds: DataStore):
        assert ds.get_series("/nonexistent") is None

    def test_series_names(self, ds: DataStore):
        ds.add_series("/a/x", np.array([0.0]), np.array([1.0]))
        ds.add_series("/b/y", np.array([0.0]), np.array([2.0]))
        assert set(ds.series_names) == {"/a/x", "/b/y"}


class TestGetScalarAt:
    def test_interpolation_nearest_before(self, ds: DataStore):
        ts = np.array([0.0, 1.0, 2.0, 3.0])
        vals = np.array([10.0, 20.0, 30.0, 40.0])
        ds.add_series("/s", ts, vals)

        assert ds.get_scalar_at("/s", 0.0) == 10.0
        assert ds.get_scalar_at("/s", 0.5) == 10.0  # before 1.0 → idx 0
        assert ds.get_scalar_at("/s", 1.0) == 20.0
        assert ds.get_scalar_at("/s", 2.5) == 30.0
        assert ds.get_scalar_at("/s", 3.0) == 40.0
        assert ds.get_scalar_at("/s", 99.0) == 40.0  # clamp to last

    def test_missing_series_returns_zero(self, ds: DataStore):
        assert ds.get_scalar_at("/missing", 1.0) == 0.0

    def test_empty_series(self, ds: DataStore):
        ds.add_series("/empty", np.array([]), np.array([]))
        assert ds.get_scalar_at("/empty", 1.0) == 0.0


class TestMessages:
    def test_add_and_retrieve(self, ds: DataStore):
        ds.add_message("/images", 1.0, {"frame": 1})
        ds.add_message("/images", 2.0, {"frame": 2})
        ds.add_message("/images", 3.0, {"frame": 3})

        result = ds.get_message_at("/images", 2.5)
        assert result is not None
        ts, msg = result
        assert ts == 2.0
        assert msg == {"frame": 2}

    def test_get_message_before_first(self, ds: DataStore):
        ds.add_message("/t", 5.0, "data")
        result = ds.get_message_at("/t", 1.0)
        assert result is not None
        assert result[0] == 5.0  # clamps to first

    def test_missing_topic_returns_none(self, ds: DataStore):
        assert ds.get_message_at("/nope", 1.0) is None

    def test_message_topics(self, ds: DataStore):
        ds.add_message("/a", 0.0, "x")
        ds.add_message("/b", 0.0, "y")
        assert set(ds.message_topics()) == {"/a", "/b"}


class TestTimeRange:
    def test_initial_range(self, ds: DataStore):
        assert ds.time_range == (0.0, 0.0)

    def test_range_from_series(self, ds: DataStore):
        ds.add_series("/s1", np.array([1.0, 5.0]), np.array([0.0, 0.0]))
        assert ds.time_range == (1.0, 5.0)

    def test_range_expands(self, ds: DataStore):
        ds.add_series("/s1", np.array([2.0, 4.0]), np.array([0.0, 0.0]))
        ds.add_message("/m", 1.0, "x")
        ds.add_message("/m", 6.0, "y")
        assert ds.time_range == (1.0, 6.0)


class TestTopics:
    def test_add_topic(self, ds: DataStore):
        info = TopicInfo(name="/test", message_type="Foo", message_count=10, fields=["a", "b"])
        ds.add_topic(info)
        assert "/test" in ds.topics
        assert ds.topics["/test"].message_count == 10
