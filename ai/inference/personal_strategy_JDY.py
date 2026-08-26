"""JDY 개인화 횡단면 랭킹 전략.

이 모듈은 주문을 전송하지 않는다. 시점 기준(as-of) 데이터만 사용해
BUY/HOLD/REDUCE/SELL/WATCH 의견, 목표 비중, 승인 대기 주문 의도를 만든다.

전략 개요
---------
1. KOSPI/KOSDAQ 보통주 중 유동성과 재무 건전성 필터를 통과한 종목을 고른다.
2. 품질 30%, 성장 25%, 가치 15%, 기관수급 20%, 산업 펀더멘털 10%로
   섹터중립 구조점수를 계산한다.
3. 구조점수 상위 종목 중 장기 추세가 유지되고 단기 과열이 해소된 눌림목을
   신규 진입 후보로 삼는다.
4. 종목당 20%, 섹터당 30%, 최대 10종목 제약으로 목표 비중을 계산한다.

입력 데이터 계약
------------------
prices (필수):
    symbol, date, open, high, low, close, volume, trading_value
fundamentals (필수, point-in-time):
    symbol, known_at, sector, roe, roa, operating_margin,
    operating_cash_flow, net_income, total_assets, total_debt, total_equity,
    revenue_yoy, operating_income_yoy, market_cap, fcf,
    enterprise_value, ebitda
flows (필수):
    symbol, date, foreign_net_buy, pension_net_buy
metadata (선택):
    symbol, security_type, market, status
current_positions (선택):
    symbol, current_weight

모든 금액 컬럼과 순매수 컬럼은 같은 통화 단위를 사용해야 한다. ``pension_net_buy``는 KRX의
공개 분류인 '연기금 등'을 뜻하며 국민연금 단독 거래로 해석하면 안 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


PRICE_COLUMNS = {
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trading_value",
}
FUNDAMENTAL_COLUMNS = {
    "symbol",
    "known_at",
    "sector",
    "roe",
    "roa",
    "operating_margin",
    "operating_cash_flow",
    "net_income",
    "total_assets",
    "total_debt",
    "total_equity",
    "revenue_yoy",
    "operating_income_yoy",
    "market_cap",
    "fcf",
    "enterprise_value",
    "ebitda",
}
FLOW_COLUMNS = {"symbol", "date", "foreign_net_buy", "pension_net_buy"}


@dataclass(frozen=True)
class JDYStrategyConfig:
    """검증 전 전략 파라미터. 백테스트 전에 전략군과 탐색 범위를 고정한다."""

    min_history_days: int = 140
    max_price_staleness_days: int = 7
    max_flow_staleness_days: int = 10
    max_fundamental_age_days: int = 550
    min_average_trading_value: float = 5_000_000_000.0
    min_market_cap: float = 300_000_000_000.0
    min_sector_peers: int = 5
    max_holdings: int = 10
    min_holdings: int = 5
    max_names_per_sector: int = 2
    max_name_weight: float = 0.20
    max_sector_weight: float = 0.30
    first_entry_fraction: float = 0.40
    reduce_fraction: float = 0.30
    structural_candidate_percentile: float = 0.70
    exit_structural_percentile: float = 0.50
    rsi_entry_low: float = 40.0
    rsi_entry_high: float = 60.0
    rsi_overheated: float = 70.0
    zscore_overheated: float = 1.75
    gap_overheated: float = 0.05
    abnormal_turnover_multiple: float = 3.0
    trend_break_days: int = 3


@dataclass
class JDYPositionRiskState:
    """손절 모듈과 공유하는 최소 포지션 상태.

    손절 조건 계산은 ``personal_strategy_JDY_loss_cut.py``가 담당한다.
    원본 전략은 상태 계약과 가격 관측값 저장만 제공한다.
    """

    symbol: str
    entry_price: float = 0.0
    entry_timestamp: pd.Timestamp | None = None
    highest_price_since_entry: float = 0.0
    lowest_price_since_entry: float = float("inf")
    initial_stop: float | None = None
    active_stop: float | None = None
    initial_risk_r: float | None = None
    holding_days: int = 0
    status: str = "INACTIVE"
    last_stop_reason: str = ""
    cooldown_until: pd.Timestamp | None = None
    last_observed_at: pd.Timestamp | None = None

    def open(self, price: float, timestamp: str | pd.Timestamp) -> None:
        observed_at = _timestamp(timestamp)
        self.entry_price = float(price)
        self.entry_timestamp = observed_at
        self.highest_price_since_entry = float(price)
        self.lowest_price_since_entry = float(price)
        self.initial_stop = None
        self.active_stop = None
        self.initial_risk_r = None
        self.holding_days = 0
        self.status = "MONITORING"
        self.last_stop_reason = ""
        self.last_observed_at = observed_at

    def observe(self, price: float, timestamp: str | pd.Timestamp) -> None:
        observed_at = _timestamp(timestamp)
        value = float(price)
        self.highest_price_since_entry = max(self.highest_price_since_entry, value)
        self.lowest_price_since_entry = min(self.lowest_price_since_entry, value)
        if self.last_observed_at is None or observed_at.normalize() > self.last_observed_at.normalize():
            self.holding_days += 1
        self.last_observed_at = observed_at


class PersonalStrategyJDY:
    """섹터중립 품질성장·기관수급·눌림목 랭킹 전략."""

    def __init__(self, config: JDYStrategyConfig | None = None) -> None:
        self.config = config or JDYStrategyConfig()

    def generate_recommendations(
        self,
        as_of: str | pd.Timestamp,
        prices: pd.DataFrame,
        fundamentals: pd.DataFrame,
        flows: pd.DataFrame,
        metadata: pd.DataFrame | None = None,
        current_positions: pd.DataFrame | None = None,
        loss_cut_monitor: object | None = None,
        loss_cut_states: dict[str, JDYPositionRiskState] | None = None,
    ) -> pd.DataFrame:
        """시점 기준 추천과 목표 비중을 반환한다.

        반환값의 ``order_intent``는 반드시 사람의 승인을 거쳐야 하며 주문 API에
        바로 전달하면 안 된다. 입력 데이터가 부족하거나 오래된 종목은 fail-closed
        방식으로 신규 매수 대상에서 제외한다.
        """

        cutoff = _timestamp(as_of)
        prices = self._prepare_prices(prices, cutoff)
        fundamentals = self._prepare_fundamentals(fundamentals, cutoff)
        flows = self._prepare_flows(flows, cutoff)

        latest = self._latest_technicals(prices)
        latest = latest.merge(fundamentals, on="symbol", how="left", validate="one_to_one")
        latest = latest.merge(
            self._institutional_features(flows, prices),
            on="symbol",
            how="left",
            validate="one_to_one",
        )
        latest["price_age_days"] = (cutoff - latest["date"]).dt.days
        latest["flow_age_days"] = (cutoff - latest["flow_latest_date"]).dt.days
        latest["fundamental_age_days"] = (cutoff - latest["known_at"]).dt.days

        if metadata is not None:
            latest = self._merge_metadata(latest, metadata)

        latest = self._fundamental_features(latest)
        latest = self._eligibility_flags(latest)
        latest = self._structural_scores(latest)
        latest = self._tactical_scores(latest)
        latest = self._rank_and_select(latest)

        positions = self._positions(current_positions)
        latest = latest.merge(positions, on="symbol", how="left")
        latest["current_weight"] = latest["current_weight"].fillna(0.0)
        latest["is_held"] = latest["current_weight"] > 0
        latest = self._actions_and_weights(latest)
        latest = self._order_intents(latest)

        columns = [
            "as_of",
            "symbol",
            "sector",
            "close",
            "eligible",
            "structural_score",
            "structural_percentile",
            "tactical_score",
            "final_score",
            "rank",
            "selected",
            "trend_ok",
            "pullback_ready",
            "overheated",
            "action",
            "reason",
            "current_weight",
            "target_weight",
            "weight_delta",
            "order_intent",
            "requires_human_approval",
        ]
        latest["as_of"] = cutoff
        output = latest.reindex(columns=columns).sort_values(
            ["selected", "final_score"], ascending=[False, False], na_position="last"
        ).reset_index(drop=True)
        if loss_cut_monitor is not None:
            if not hasattr(loss_cut_monitor, "evaluate_jdy"):
                raise TypeError("loss_cut_monitor는 evaluate_jdy 메서드를 제공해야 합니다.")
            output = loss_cut_monitor.evaluate_jdy(
                as_of=cutoff,
                recommendations=output,
                prices=prices,
                states=loss_cut_states if loss_cut_states is not None else {},
            )
        return output

    def _prepare_prices(self, frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
        _require_columns(frame, PRICE_COLUMNS, "prices")
        result = frame.copy()
        result["date"] = pd.to_datetime(result["date"], errors="raise").dt.tz_localize(None)
        result = result[result["date"] <= cutoff].sort_values(["symbol", "date"])
        if result.empty:
            raise ValueError("as_of 이전의 prices 데이터가 없습니다.")
        if result.duplicated(["symbol", "date"]).any():
            raise ValueError("prices에 symbol/date 중복 행이 있습니다.")
        numeric = PRICE_COLUMNS - {"symbol", "date"}
        result[list(numeric)] = result[list(numeric)].apply(pd.to_numeric, errors="coerce")
        return result

    def _prepare_fundamentals(
        self, frame: pd.DataFrame, cutoff: pd.Timestamp
    ) -> pd.DataFrame:
        _require_columns(frame, FUNDAMENTAL_COLUMNS, "fundamentals")
        result = frame.copy()
        result["known_at"] = pd.to_datetime(result["known_at"], errors="raise").dt.tz_localize(None)
        result = result[result["known_at"] <= cutoff]
        if result.empty:
            raise ValueError("as_of 이전에 공시된 fundamentals 데이터가 없습니다.")
        result = result.sort_values(["symbol", "known_at"]).drop_duplicates(
            "symbol", keep="last"
        )
        numeric = FUNDAMENTAL_COLUMNS - {"symbol", "known_at", "sector"}
        result[list(numeric)] = result[list(numeric)].apply(pd.to_numeric, errors="coerce")
        return result

    def _prepare_flows(self, frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
        _require_columns(frame, FLOW_COLUMNS, "flows")
        result = frame.copy()
        result["date"] = pd.to_datetime(result["date"], errors="raise").dt.tz_localize(None)
        result = result[result["date"] <= cutoff].sort_values(["symbol", "date"])
        if result.duplicated(["symbol", "date"]).any():
            raise ValueError("flows에 symbol/date 중복 행이 있습니다.")
        numeric = FLOW_COLUMNS - {"symbol", "date"}
        result[list(numeric)] = result[list(numeric)].apply(pd.to_numeric, errors="coerce")
        return result

    def _latest_technicals(self, prices: pd.DataFrame) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for symbol, group in prices.groupby("symbol", sort=False):
            group = group.sort_values("date").copy()
            close = group["close"]
            group["history_days"] = np.arange(1, len(group) + 1)
            for window in (20, 60, 120):
                group[f"sma{window}"] = close.rolling(window, min_periods=window).mean()
            group["sma120_20d_ago"] = group["sma120"].shift(20)
            group["sma120_slope"] = group["sma120"] / group["sma120_20d_ago"] - 1.0
            group["volatility60"] = close.pct_change().rolling(60, min_periods=40).std()
            group["adv20"] = group["trading_value"].rolling(20, min_periods=15).mean()
            group["turnover_multiple"] = group["trading_value"] / group["adv20"]
            group["rsi14"] = _rsi(close, 14)
            mean20 = close.rolling(20, min_periods=20).mean()
            std20 = close.rolling(20, min_periods=20).std(ddof=0)
            group["zscore20"] = (close - mean20) / std20.replace(0, np.nan)
            lower = mean20 - 2.0 * std20
            upper = mean20 + 2.0 * std20
            group["bollinger_pct_b"] = (close - lower) / (upper - lower).replace(0, np.nan)
            group["gap"] = group["open"] / close.shift(1) - 1.0
            group["below_sma120"] = close < group["sma120"]
            group["trend_break_count"] = _consecutive_true(group["below_sma120"])
            frames.append(group.tail(1))
        return pd.concat(frames, ignore_index=True)

    def _institutional_features(
        self, flows: pd.DataFrame, prices: pd.DataFrame
    ) -> pd.DataFrame:
        daily_value = prices[["symbol", "date", "trading_value"]]
        merged = flows.merge(daily_value, on=["symbol", "date"], how="left")
        rows: list[dict[str, float | str]] = []
        for symbol, group in merged.groupby("symbol", sort=False):
            group = group.sort_values("date")
            row: dict[str, float | str | pd.Timestamp] = {
                "symbol": symbol,
                "flow_latest_date": group["date"].max(),
            }
            for window in (20, 60):
                sample = group.tail(window)
                denominator = sample["trading_value"].sum(min_count=1)
                if not np.isfinite(denominator) or denominator <= 0:
                    row[f"foreign_flow_{window}"] = np.nan
                    row[f"pension_flow_{window}"] = np.nan
                else:
                    row[f"foreign_flow_{window}"] = sample["foreign_net_buy"].sum(
                        min_count=1
                    ) / denominator
                    row[f"pension_flow_{window}"] = sample["pension_net_buy"].sum(
                        min_count=1
                    ) / denominator
            rows.append(row)
        return pd.DataFrame(rows)

    def _merge_metadata(self, frame: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
        _require_columns(metadata, {"symbol"}, "metadata")
        keep = [
            column
            for column in ("symbol", "security_type", "market", "status")
            if column in metadata.columns
        ]
        clean = metadata[keep].drop_duplicates("symbol", keep="last")
        return frame.merge(clean, on="symbol", how="left", validate="one_to_one")

    def _fundamental_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        assets = result["total_assets"].replace(0, np.nan)
        equity = result["total_equity"].replace(0, np.nan)
        market_cap = result["market_cap"].replace(0, np.nan)
        enterprise_value = result["enterprise_value"].replace(0, np.nan)
        result["cashflow_on_assets"] = result["operating_cash_flow"] / assets
        result["accrual_quality"] = (
            result["operating_cash_flow"] - result["net_income"]
        ) / assets
        result["low_leverage"] = -(result["total_debt"] / equity)
        result["earnings_yield"] = result["net_income"] / market_cap
        result["fcf_yield"] = result["fcf"] / market_cap
        result["ebitda_to_ev"] = result["ebitda"] / enterprise_value
        return result

    def _eligibility_flags(self, frame: pd.DataFrame) -> pd.DataFrame:
        c = self.config
        result = frame.copy()
        metadata_ok = pd.Series(True, index=result.index)
        if "security_type" in result:
            metadata_ok &= result["security_type"].fillna("COMMON").str.upper().isin(
                {"COMMON", "COMMON_STOCK", "STOCK"}
            )
        if "market" in result:
            metadata_ok &= result["market"].fillna("KOSPI").str.upper().isin(
                {"KOSPI", "KOSDAQ"}
            )
        if "status" in result:
            metadata_ok &= result["status"].fillna("ACTIVE").str.upper().eq("ACTIVE")

        result["fundamental_ok"] = (
            (result["operating_cash_flow"] > 0)
            & (result["net_income"] > 0)
            & (result["operating_margin"] > 0)
            & (result["total_equity"] > 0)
        )
        result["liquidity_ok"] = result["adv20"] >= c.min_average_trading_value
        result["size_ok"] = result["market_cap"] >= c.min_market_cap
        result["history_ok"] = result["history_days"] >= c.min_history_days
        result["freshness_ok"] = (
            result["price_age_days"].between(0, c.max_price_staleness_days)
            & result["flow_age_days"].between(0, c.max_flow_staleness_days)
            & result["fundamental_age_days"].between(0, c.max_fundamental_age_days)
        )
        result["flow_ok"] = (
            result[["foreign_flow_60", "pension_flow_60"]].fillna(-np.inf).max(axis=1) >= 0
        ) & (
            result[["foreign_flow_60", "pension_flow_60"]].fillna(0).sum(axis=1) >= 0
        )
        result["eligible"] = (
            metadata_ok
            & result["fundamental_ok"]
            & result["liquidity_ok"]
            & result["size_ok"]
            & result["history_ok"]
            & result["freshness_ok"]
            & result["flow_ok"]
        )
        return result

    def _structural_scores(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        features = {
            "quality_score": [
                "roe",
                "roa",
                "operating_margin",
                "cashflow_on_assets",
                "accrual_quality",
                "low_leverage",
            ],
            "growth_score": ["revenue_yoy", "operating_income_yoy"],
            "value_score": ["earnings_yield", "fcf_yield", "ebitda_to_ev"],
            "institution_score": [
                "foreign_flow_20",
                "foreign_flow_60",
                "pension_flow_20",
                "pension_flow_60",
            ],
        }
        eligible = result["eligible"]
        for score_name, columns in features.items():
            ranked = pd.DataFrame(index=result.index)
            for column in columns:
                ranked[column] = _sector_percentile(
                    result[column].where(eligible),
                    result["sector"],
                    self.config.min_sector_peers,
                )
            result[score_name] = ranked.mean(axis=1, skipna=True) * 100.0

        # 산업 펀더멘털은 해당 산업 구성원의 성장점수 중앙값으로 정의한다.
        result["sector_score"] = result.groupby("sector", dropna=False)[
            "growth_score"
        ].transform("median")
        result["structural_score"] = (
            0.30 * result["quality_score"]
            + 0.25 * result["growth_score"]
            + 0.15 * result["value_score"]
            + 0.20 * result["institution_score"]
            + 0.10 * result["sector_score"]
        ).where(eligible)
        result["structural_percentile"] = result["structural_score"].rank(
            pct=True, method="average"
        )
        return result

    def _tactical_scores(self, frame: pd.DataFrame) -> pd.DataFrame:
        c = self.config
        result = frame.copy()
        result["trend_ok"] = (
            (result["close"] > result["sma120"]) & (result["sma120_slope"] > 0)
        )
        rsi_score = (1.0 - (result["rsi14"] - 50.0).abs() / 20.0).clip(0, 1)
        band_score = (1.0 - (result["bollinger_pct_b"] - 0.5).abs() / 0.5).clip(0, 1)
        distance20 = (result["close"] / result["sma20"] - 1.0).abs()
        distance60 = (result["close"] / result["sma60"] - 1.0).abs()
        moving_average_score = (1.0 - pd.concat([distance20, distance60], axis=1).min(axis=1) / 0.08).clip(0, 1)
        normal_volume_score = (
            1.0 - (result["turnover_multiple"] - 1.0).abs() / 2.0
        ).clip(0, 1)
        result["tactical_score"] = 100.0 * (
            0.30 * rsi_score
            + 0.30 * band_score
            + 0.30 * moving_average_score
            + 0.10 * normal_volume_score
        )
        result["pullback_ready"] = (
            result["trend_ok"]
            & result["rsi14"].between(c.rsi_entry_low, c.rsi_entry_high)
            & result["bollinger_pct_b"].between(0.30, 0.70)
            & (pd.concat([distance20, distance60], axis=1).min(axis=1) <= 0.08)
        )
        result["overheated"] = (
            (result["rsi14"] >= c.rsi_overheated)
            | (result["zscore20"] >= c.zscore_overheated)
            | (result["gap"] >= c.gap_overheated)
            | (result["turnover_multiple"] >= c.abnormal_turnover_multiple)
        )
        overheat_count = pd.concat(
            [
                result["rsi14"] >= c.rsi_overheated,
                result["zscore20"] >= c.zscore_overheated,
                result["gap"] >= c.gap_overheated,
                result["turnover_multiple"] >= c.abnormal_turnover_multiple,
            ],
            axis=1,
        ).sum(axis=1)
        result["overheat_penalty"] = 7.5 * overheat_count
        result["final_score"] = (
            0.70 * result["structural_score"]
            + 0.30 * result["tactical_score"]
            - result["overheat_penalty"]
        ).where(result["eligible"])
        return result

    def _rank_and_select(self, frame: pd.DataFrame) -> pd.DataFrame:
        c = self.config
        result = frame.copy()
        candidates = result[
            result["eligible"]
            & result["trend_ok"]
            & (result["structural_percentile"] >= c.structural_candidate_percentile)
        ].sort_values("final_score", ascending=False)
        selected: list[str] = []
        sector_counts: dict[str, int] = {}
        for row in candidates.itertuples():
            sector = str(row.sector)
            if sector_counts.get(sector, 0) >= c.max_names_per_sector:
                continue
            selected.append(row.symbol)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            if len(selected) >= c.max_holdings:
                break
        result["selected"] = result["symbol"].isin(selected)
        result["portfolio_ready"] = len(selected) >= c.min_holdings
        result["rank"] = result["final_score"].rank(
            method="first", ascending=False, na_option="bottom"
        ).astype("Int64")
        return result

    def _positions(self, frame: pd.DataFrame | None) -> pd.DataFrame:
        if frame is None:
            return pd.DataFrame(columns=["symbol", "current_weight"])
        _require_columns(frame, {"symbol", "current_weight"}, "current_positions")
        result = frame[["symbol", "current_weight"]].copy()
        result["current_weight"] = pd.to_numeric(result["current_weight"], errors="raise")
        if result.duplicated("symbol").any():
            raise ValueError("current_positions에 symbol 중복 행이 있습니다.")
        return result

    def _actions_and_weights(self, frame: pd.DataFrame) -> pd.DataFrame:
        c = self.config
        result = frame.copy()
        hard_exit = result["is_held"] & (
            ~result["fundamental_ok"]
            | (result["trend_break_count"] >= c.trend_break_days)
        )
        rank_exit = result["is_held"] & (
            result["structural_percentile"].fillna(0) < c.exit_structural_percentile
        )
        reduce = result["is_held"] & ~hard_exit & ~rank_exit & (
            result["overheated"] | ~result["selected"]
        )
        buy = (
            ~result["is_held"]
            & result["selected"]
            & result["portfolio_ready"]
            & result["pullback_ready"]
            & ~result["overheated"]
        )
        hold = result["is_held"] & ~hard_exit & ~rank_exit & ~reduce
        watch = ~result["is_held"] & result["selected"] & ~buy

        result["action"] = "IGNORE"
        result.loc[watch, "action"] = "WATCH"
        result.loc[buy, "action"] = "BUY"
        result.loc[hold, "action"] = "HOLD"
        result.loc[reduce, "action"] = "REDUCE"
        result.loc[hard_exit | rank_exit, "action"] = "SELL"

        result["reason"] = "랭킹 또는 필터 미충족"
        result.loc[watch, "reason"] = "구조점수 상위이나 눌림목 진입조건 대기"
        result.loc[buy, "reason"] = "구조점수·추세·눌림목 조건 충족"
        result.loc[hold, "reason"] = "보유 조건 유지"
        result.loc[reduce & result["overheated"], "reason"] = "단기 과열: 분할익절 후보"
        result.loc[reduce & ~result["selected"], "reason"] = "선정 순위 이탈: 비중 축소"
        result.loc[rank_exit, "reason"] = "구조점수 하위 50%: 교체 후보"
        result.loc[hard_exit, "reason"] = "재무 또는 장기 추세 훼손"

        active = result["selected"] & result["action"].isin(["BUY", "HOLD", "REDUCE"])
        result["target_weight"] = 0.0
        active_count = int(active.sum())
        if active_count:
            equal_weight = min(1.0 / active_count, c.max_name_weight)
            result.loc[active, "target_weight"] = equal_weight
            # 신규 주문은 40%만 제안한다. 나머지 30%+30%는 후속 신호에서 승인한다.
            result.loc[result["action"].eq("BUY"), "target_weight"] *= c.first_entry_fraction
            result.loc[result["action"].eq("REDUCE"), "target_weight"] *= 1.0 - c.reduce_fraction
            sector_total = result.groupby("sector", dropna=False)["target_weight"].transform("sum")
            scale = (c.max_sector_weight / sector_total).clip(upper=1.0).fillna(1.0)
            result["target_weight"] *= scale
        result["weight_delta"] = result["target_weight"] - result["current_weight"]
        return result

    def _order_intents(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        tolerance = 0.0025
        result["order_intent"] = "NONE"
        result.loc[result["weight_delta"] > tolerance, "order_intent"] = "BUY_TO_WEIGHT"
        result.loc[result["weight_delta"] < -tolerance, "order_intent"] = "SELL_TO_WEIGHT"
        result["requires_human_approval"] = result["order_intent"].ne("NONE")
        return result


def run_personal_strategy_jdy(
    as_of: str | pd.Timestamp,
    prices: pd.DataFrame,
    fundamentals: pd.DataFrame,
    flows: pd.DataFrame,
    metadata: pd.DataFrame | None = None,
    current_positions: pd.DataFrame | None = None,
    config: JDYStrategyConfig | None = None,
    loss_cut_monitor: object | None = None,
    loss_cut_states: dict[str, JDYPositionRiskState] | None = None,
) -> pd.DataFrame:
    """함수형 호출을 원하는 자동매매 파이프라인용 공개 진입점."""

    return PersonalStrategyJDY(config).generate_recommendations(
        as_of=as_of,
        prices=prices,
        fundamentals=fundamentals,
        flows=flows,
        metadata=metadata,
        current_positions=current_positions,
        loss_cut_monitor=loss_cut_monitor,
        loss_cut_states=loss_cut_states,
    )


def _require_columns(frame: pd.DataFrame, required: Iterable[str], name: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{name}에 필수 컬럼이 없습니다: {', '.join(missing)}")


def _timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if result.tzinfo is not None:
        result = result.tz_localize(None)
    return result


def _rsi(close: pd.Series, window: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + relative_strength)
    return rsi.where(loss.ne(0), 100.0).where(gain.ne(0), 0.0)


def _consecutive_true(values: pd.Series) -> pd.Series:
    groups = (~values.fillna(False)).cumsum()
    return values.fillna(False).astype(int).groupby(groups).cumsum()


def _sector_percentile(
    values: pd.Series, sectors: pd.Series, min_sector_peers: int
) -> pd.Series:
    """5/95% 완화 후 섹터 내 순위, 표본이 작으면 전체 순위를 반환한다."""

    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=values.index)
    lower, upper = valid.quantile([0.05, 0.95])
    clipped = numeric.clip(lower, upper)
    overall = clipped.rank(pct=True, method="average")
    sector_rank = clipped.groupby(sectors, dropna=False).rank(pct=True, method="average")
    peer_count = clipped.groupby(sectors, dropna=False).transform("count")
    return sector_rank.where(peer_count >= min_sector_peers, overall)


__all__ = [
    "JDYStrategyConfig",
    "JDYPositionRiskState",
    "PersonalStrategyJDY",
    "run_personal_strategy_jdy",
]
