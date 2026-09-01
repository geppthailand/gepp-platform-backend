"""`BMAGSheetService.select_baseline` — which month becomes the baseline.

The rule exists because the baseline is the FIRST month a site reports, not a
pre-project survey, and a site's first month is often a partial install. Left
alone, that reads as a large waste *increase*. These cases are the real site
shapes it was derived from, so a future tweak to the threshold has to face them.
"""

import datetime as dt

import pytest

from GEPPPlatform.services.integrations.bma.bma_gsheet_service import (
    BMAGSheetService as S,
)


def m(*pairs):
    """`m((4, 140), (5, 9259))` -> {2026-04-01: 140.0, 2026-05-01: 9259.0}."""
    return {dt.date(2026, mm, 1): float(kg) for mm, kg in pairs}


def pick(by_month):
    """(baseline month as 'MM', skipped count, untested)."""
    months, idx, skipped, untested = S.select_baseline(by_month)
    return months[idx].strftime('%m') if months else None, len(skipped), untested


class TestRampUpSkipping:
    def test_rasa_one_shape_skips_the_install_month(self):
        # 140 kg then ~9,000: 1.5% of the median. The case that motivated this.
        assert pick(m((4, 140), (5, 9259), (6, 10140))) == ('05', 1, False)

    def test_rasa_two_shape(self):
        assert pick(m((4, 347), (5, 22370), (6, 21200))) == ('05', 1, False)

    def test_skips_several_consecutive_part_months(self):
        # อาคาร Unilever: three leading months below the floor.
        got = pick(m((3, 120), (4, 200), (5, 310), (6, 8376), (7, 9000)))
        assert got == ('06', 3, False)

    def test_healthy_first_month_is_kept(self):
        # 39% of median — low, but a plausible month. Must NOT be skipped;
        # a z-score cannot tell this apart from the RASA case above.
        assert pick(m((4, 3900), (5, 10000), (6, 12000))) == ('04', 0, False)

    def test_high_first_month_is_kept(self):
        # One-sided on purpose: 2x the median stays as the baseline.
        assert pick(m((4, 20000), (5, 10000), (6, 9000))) == ('04', 0, False)


class TestGuards:
    def test_two_months_are_untested_and_use_the_first(self):
        # No usable median at n=2, so the first month stands — but flagged, so
        # the sheet is not implying a test that never ran.
        assert pick(m((4, 140), (5, 9259))) == ('04', 0, True)

    def test_never_skips_the_final_month(self):
        # Everything below the floor except the last: something has to be the
        # baseline, and consuming the whole series would leave nothing.
        assert pick(m((4, 1), (5, 1), (6, 100000))) == ('06', 2, False)

    def test_zero_months_are_not_months(self):
        # A logged 0 is "collected nothing", not a data point to baseline on.
        assert pick(m((4, 0), (5, 9000), (6, 9500), (7, 9200))) == ('05', 0, False)

    def test_empty_input(self):
        assert S.select_baseline({}) == ([], 0, [], True)

    def test_skipped_months_are_iso_strings(self):
        _, _, skipped, _ = S.select_baseline(m((4, 140), (5, 9259), (6, 10140)))
        assert skipped == ['2026-04-01']


class TestThreshold:
    @pytest.mark.parametrize('ratio,skips', [
        (0.05, True),    # deep ramp-up
        (0.29, True),    # just under the floor
        (0.31, False),   # just over
        (0.90, False),
    ])
    def test_floor_is_relative_to_the_median(self, ratio, skips):
        # median of the two later months is 10,000, so the floor is 3,000.
        first = 10000 * ratio
        month, n_skipped, _ = pick(m((4, first), (5, 10000), (6, 10000)))
        assert (month == '05') is skips
        assert (n_skipped == 1) is skips

    def test_chosen_threshold_sits_in_an_empty_gap(self):
        # The observed population is bimodal: six sites at 0.015-0.068, next at
        # 0.382. Any floor in this range picks the same six, which is why 0.30
        # is not a fitted number.
        assert 0.10 < S.BASELINE_MIN_RATIO_TO_MEDIAN < 0.37
