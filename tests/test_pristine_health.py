from __future__ import annotations

import unittest

from stock_signal_system.data.pristine_health import (
    StockFundamentals,
    build_annual_eps,
    build_dividend_years,
    compute_debt_ratio_pct,
    compute_roe_pct,
    describe_valuation,
    evaluate_pristine_screen,
)


def _fundamentals(**overrides) -> StockFundamentals:
    defaults = dict(
        symbol="2330",
        quarterly_eps=(2.5, 2.3, 2.1, 2.0),
        annual_eps={2025: 9.5, 2024: 8.8, 2023: 8.0},
        dividend_years=frozenset({2025, 2024, 2023}),
    )
    defaults.update(overrides)
    return StockFundamentals(**defaults)


class EvaluatePristineScreenTest(unittest.TestCase):
    def test_passes_when_all_criteria_met(self):
        result = evaluate_pristine_screen(_fundamentals())
        self.assertTrue(result.passes)
        self.assertEqual(result.reasons, ())

    def test_fails_when_a_recent_quarter_is_negative(self):
        result = evaluate_pristine_screen(_fundamentals(quarterly_eps=(2.5, 2.3, -0.5, 2.0)))
        self.assertFalse(result.passes)
        self.assertIn("最近4季EPS未全數為正", result.reasons)

    def test_fails_when_fewer_than_four_quarters_available(self):
        result = evaluate_pristine_screen(_fundamentals(quarterly_eps=(2.5, 2.3)))
        self.assertFalse(result.passes)
        self.assertIn("最近4季EPS未全數為正", result.reasons)

    def test_fails_when_a_recent_year_eps_is_negative(self):
        result = evaluate_pristine_screen(_fundamentals(annual_eps={2025: -1.0, 2024: 8.8, 2023: 8.0}))
        self.assertFalse(result.passes)
        self.assertIn("最近3年EPS未全數為正", result.reasons)

    def test_fails_when_a_recent_year_has_no_dividend(self):
        result = evaluate_pristine_screen(_fundamentals(dividend_years=frozenset({2025, 2023})))
        self.assertFalse(result.passes)
        self.assertIn("最近3年未皆配息", result.reasons)

    def test_fails_when_fewer_than_three_years_of_eps_available(self):
        result = evaluate_pristine_screen(_fundamentals(annual_eps={2025: 9.5, 2024: 8.8}))
        self.assertFalse(result.passes)
        self.assertIn("最近3年EPS未全數為正", result.reasons)


class ComputeRoeAndDebtRatioTest(unittest.TestCase):
    def test_roe_computed_from_ttm_income_and_equity(self):
        fundamentals = _fundamentals(ttm_net_income=100.0, equity=1000.0)
        self.assertAlmostEqual(compute_roe_pct(fundamentals), 10.0)

    def test_roe_none_when_equity_missing_or_zero(self):
        self.assertIsNone(compute_roe_pct(_fundamentals(ttm_net_income=100.0, equity=None)))
        self.assertIsNone(compute_roe_pct(_fundamentals(ttm_net_income=100.0, equity=0.0)))

    def test_debt_ratio_computed_from_liabilities_and_assets(self):
        fundamentals = _fundamentals(liabilities=300.0, total_assets=1000.0)
        self.assertAlmostEqual(compute_debt_ratio_pct(fundamentals), 30.0)

    def test_debt_ratio_none_when_assets_missing(self):
        self.assertIsNone(compute_debt_ratio_pct(_fundamentals(liabilities=300.0, total_assets=None)))


class DescribeValuationTest(unittest.TestCase):
    def test_sweet_spot_range(self):
        self.assertIn("甜蜜區間", describe_valuation(12.0))

    def test_below_upper_bound_but_above_sweet_spot(self):
        self.assertIn("低於20倍門檻", describe_valuation(18.0))

    def test_above_upper_bound(self):
        self.assertIn("超過建議上限", describe_valuation(25.0))

    def test_missing_pe_is_reported_as_unavailable(self):
        self.assertEqual(describe_valuation(None), "本益比資料暫缺")
        self.assertEqual(describe_valuation(0.0), "本益比資料暫缺")


class BuildAnnualEpsTest(unittest.TestCase):
    def test_sums_quarterly_eps_by_year(self):
        rows = [("2025-03-31", 2.0), ("2025-06-30", 2.5), ("2024-12-31", 2.2)]
        annual = build_annual_eps(rows)
        self.assertAlmostEqual(annual[2025], 4.5)
        self.assertAlmostEqual(annual[2024], 2.2)

    def test_skips_unparseable_dates(self):
        annual = build_annual_eps([("not-a-date", 2.0), ("2025-03-31", 1.0)])
        self.assertEqual(annual, {2025: 1.0})


class BuildDividendYearsTest(unittest.TestCase):
    def test_collects_years_with_cash_or_stock_dividend(self):
        rows = [
            {"date": "2025-07-15", "CashEarningsDistribution": 2.5, "StockEarningsDistribution": 0.0},
            {"date": "2024-07-10", "CashEarningsDistribution": 0.0, "StockEarningsDistribution": 0.3},
            {"date": "2023-07-05", "CashEarningsDistribution": 0.0, "StockEarningsDistribution": 0.0},
        ]
        years = build_dividend_years(rows)
        self.assertEqual(years, frozenset({2025, 2024}))

    def test_empty_rows_returns_empty_set(self):
        self.assertEqual(build_dividend_years([]), frozenset())


if __name__ == "__main__":
    unittest.main()
