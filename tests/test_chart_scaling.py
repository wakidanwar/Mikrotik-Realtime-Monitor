"""Chart axes must stay readable, but must never clip sustained traffic."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.config import InterfaceConfig
from app.metrics import format_axis_ago, format_axis_clock, median_filter, robust_peak, smooth_series
from app.ui import TrafficChart


def test_robust_peak_ignores_an_isolated_spike():
    values = [45e6] * 119 + [1.2e9]
    assert robust_peak(values) < 1e8


def test_robust_peak_tracks_the_max_when_there_is_no_outlier():
    assert robust_peak([45e6, 50e6, 40e6]) == 50e6


def test_robust_peak_of_empty_history_is_zero():
    assert robust_peak([]) == 0.0


def test_smooth_series_keeps_endpoints_and_adds_intermediate_points():
    xs, ys = smooth_series([0, 1, 2, 3], [0, 10, 5, 20], subdivisions=4)

    assert len(xs) == 13
    assert xs[0] == 0 and xs[-1] == 3
    assert ys[0] == 0 and ys[-1] == 20
    assert all(v >= 0 for v in ys)


def test_median_filter_removes_a_single_spike_but_keeps_the_trend():
    assert median_filter([1, 10, 1, 2, 3]) == [1, 1, 2, 2, 3]
    assert median_filter([]) == []


def test_clock_axis_label_is_hh_mm():
    import re
    assert re.fullmatch(r"\d{2}:\d{2}", format_axis_clock(1_700_000_000.0))
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", format_axis_clock(1_700_000_000.0, True))


def test_chart_x_axis_uses_wall_clock_when_supplied():
    app = QApplication.instance() or QApplication([])
    chart = TrafficChart(InterfaceConfig(name="ether1"), 120)
    now = 1000.0
    wall = 1_700_000_000.0
    chart._draw([(now - 2, 45e6, 9e6), (now - 1, 46e6, 9e6), (now, 47e6, 9e6)], now, wall)

    assert abs(chart.plot.getAxis("bottom").range[1] - wall) < 1


def test_time_axis_labels_are_relative_and_end_at_now():
    assert format_axis_ago(0) == "NOW"
    assert format_axis_ago(30) == "-30s"
    assert format_axis_ago(60) == "-1m"
    assert format_axis_ago(90) == "-1m30s"
    assert format_axis_ago(120) == "-2m"


def test_sustained_traffic_growth_expands_the_y_axis():
    app = QApplication.instance() or QApplication([])
    chart = TrafficChart(InterfaceConfig(name="ether1"), 120)
    now = 1000.0
    history = [(now - 120 + i, 45e6, 9e6) for i in range(121)]
    chart._draw(history, now)
    assert chart.plot.getAxis("left").range[1] <= 2e8

    for i in range(111, 121):
        history[i] = (history[i][0], 45e6 + (i - 110) * 35e6, 9e6)
    chart._draw(history, now)

    assert chart.plot.getAxis("left").range[1] >= 395e6


def test_one_isolated_spike_does_not_expand_the_y_axis():
    app = QApplication.instance() or QApplication([])
    chart = TrafficChart(InterfaceConfig(name="ether1"), 120)
    now = 1000.0
    history = [(now - 120 + i, 45e6, 9e6) for i in range(121)]
    history[-1] = (history[-1][0], 1.2e9, 9e6)

    chart._draw(history, now)

    assert chart.plot.getAxis("left").range[1] <= 2e8
