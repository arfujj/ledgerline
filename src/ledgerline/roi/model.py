"""Transparent ROI / opportunity model.

Inputs come only from (a) mined process metrics, cited [q:<query_id>], and (b) named
assumptions in config/roi_assumptions.yaml, cited [a:<id>]. The LLM never computes numbers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from ledgerline.process.metrics import ProcessMetrics

Scenario = Literal["low", "base", "high"]
# Assumptions where a *higher* value makes the opportunity *worse* (costs, discount, ramp).
COST_LIKE_PREFIXES = ("impl_cost_", "run_cost_", "discount_rate", "ramp_months_")


class Assumption(BaseModel):
    id: str
    base: float
    low: float
    high: float
    unit: str
    rationale: str


class Input(BaseModel):
    name: str
    value: float
    source: str  # "[q:...]" or "[a:...]" or "derived"


class OpportunityResult(BaseModel):
    id: str
    title: str
    process: str
    scenario: Scenario
    annual_hours_saved: float
    annual_value_usd: float
    implementation_cost_usd: float
    annual_run_cost_usd: float
    npv_usd: float
    payback_months: float | None
    time_to_value_months: float
    regulatory_sensitivity: int
    value_score: float = 0.0
    effort_score: float = 0.0
    priority: Literal["quick_win", "strategic_bet", "fill_in", "deprioritize"] = "fill_in"
    inputs: list[Input] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class Sensitivity(BaseModel):
    opportunity_id: str
    assumption_id: str
    npv_low: float
    npv_high: float

    @property
    def swing(self) -> float:
        return abs(self.npv_high - self.npv_low)


def load_assumptions(path: Path) -> dict[str, Assumption]:
    raw = yaml.safe_load(path.read_text())["assumptions"]
    return {k: Assumption(id=k, **v) for k, v in raw.items()}


def load_catalogue(path: Path) -> list[dict[str, Any]]:
    cat: list[dict[str, Any]] = yaml.safe_load(path.read_text())["opportunities"]
    return cat


class ROIModel:
    def __init__(
        self,
        assumptions: dict[str, Assumption],
        catalogue: list[dict[str, Any]],
        pm: ProcessMetrics,
        data_months: float | None = None,
    ) -> None:
        self.a = assumptions
        self.catalogue = catalogue
        self.pm = pm
        self._volumes: dict[str, tuple[float, list[str]]] = {}
        self.data_months, self._months_cite = self._data_window(data_months)

    def _data_window(self, override: float | None) -> tuple[float, str]:
        if override is not None:
            return override, "derived"
        res = self.pm.run("monthly_volume", "kyc")
        return float(len(res.rows)), res.cite()

    def value(
        self, aid: str, scenario: Scenario, overrides: dict[str, Scenario] | None = None
    ) -> float:
        sc = (overrides or {}).get(aid, scenario)
        a = self.a[aid]
        return float(getattr(a, sc))

    def _volume(self, opp: dict[str, Any]) -> tuple[float, list[str]]:
        """Annualised volume (events, or hours for unit=hours) and its citations."""
        if opp["id"] in self._volumes:
            return self._volumes[opp["id"]]
        v = opp["volume"]
        if v["metric"] == "ticket_categories":
            res = self.pm.run("ticket_categories")
            total = sum(
                float(r[v["field"]]) for r in res.records() if r["category"] in v["categories"]
            )
        else:
            res = self.pm.run(v["metric"], v["process"])
            total = sum(
                float(r[v["field"]]) for r in res.records() if r["activity"] in v["activities"]
            )
        annual = total * 12.0 / self.data_months
        cites = [res.cite(), self._months_cite]
        self._volumes[opp["id"]] = (annual, cites)
        return annual, cites

    def evaluate(
        self,
        opp: dict[str, Any],
        scenario: Scenario = "base",
        overrides: dict[str, Scenario] | None = None,
    ) -> OpportunityResult:
        def val(aid: str) -> float:
            return self.value(aid, scenario, overrides)

        volume, vcites = self._volume(opp)
        used = [
            opp["automation_rate"],
            opp["hourly_cost"],
            opp["impl_cost"],
            opp["ramp_months"],
            "run_cost_pct_of_impl",
            "discount_rate",
            "horizon_years",
        ]
        vol_spec = opp.get("volume", {})
        if vol_spec.get("unit") == "hours":
            factor = 1.0
            if vol_spec.get("hours_factor"):
                used.append(vol_spec["hours_factor"])
                factor = val(vol_spec["hours_factor"])
            hours = volume * factor * val(opp["automation_rate"])
        else:
            used.append(opp["touch_minutes"])
            hours = volume * val(opp["touch_minutes"]) / 60.0 * val(opp["automation_rate"])
        value = hours * val(opp["hourly_cost"])
        if opp.get("extra_value"):
            used.append(opp["extra_value"])
            value += val(opp["extra_value"])
        impl = val(opp["impl_cost"])
        run = impl * val("run_cost_pct_of_impl")
        ramp = val(opp["ramp_months"])
        rate = val("discount_rate")
        years = int(val("horizon_years"))
        npv = -impl
        for y in range(1, years + 1):
            # Months of benefit in year y after the ramp period.
            months_live = max(0.0, min(12.0, 12.0 * y - ramp))
            net = value * months_live / 12.0 - run
            npv += net / (1 + rate) ** y
        monthly_net = value / 12.0 - run / 12.0
        payback = (ramp + impl / monthly_net) if monthly_net > 0 else None
        inputs = [
            Input(name="annualised_volume", value=round(volume, 2), source=vcites[0]),
            Input(name="data_window_months", value=self.data_months, source=vcites[1]),
        ]
        inputs += [Input(name=aid, value=val(aid), source=f"[a:{aid}]") for aid in used]
        return OpportunityResult(
            id=opp["id"],
            title=opp["title"],
            process=opp["process"],
            scenario=scenario,
            annual_hours_saved=round(hours, 1),
            annual_value_usd=round(value, 0),
            implementation_cost_usd=round(impl, 0),
            annual_run_cost_usd=round(run, 0),
            npv_usd=round(npv, 0),
            payback_months=round(payback, 1) if payback else None,
            time_to_value_months=ramp,
            regulatory_sensitivity=int(opp["regulatory_sensitivity"]),
            inputs=inputs,
            citations=sorted(
                {i.source for i in inputs}, key=lambda c: (not c.startswith("[q:"), c)
            ),
        )

    def evaluate_all(self, scenario: Scenario = "base") -> list[OpportunityResult]:
        results = [self.evaluate(o, scenario) for o in self.catalogue]
        return classify(results)

    def sensitivity(self, opp: dict[str, Any]) -> list[Sensitivity]:
        """One-at-a-time (tornado) sensitivity on NPV for every assumption the opp uses."""
        base = self.evaluate(opp, "base")
        out = []
        for inp in base.inputs:
            if not inp.source.startswith("[a:"):
                continue
            aid = inp.name
            lo = self.evaluate(opp, "base", {aid: "low"}).npv_usd
            hi = self.evaluate(opp, "base", {aid: "high"}).npv_usd
            out.append(
                Sensitivity(opportunity_id=opp["id"], assumption_id=aid, npv_low=lo, npv_high=hi)
            )
        return sorted(out, key=lambda s: s.swing, reverse=True)

    def scenarios(self) -> dict[str, list[OpportunityResult]]:
        """Conservative/base/optimistic: cost-like assumptions move against value."""
        out: dict[str, list[OpportunityResult]] = {}
        for sc in ("low", "base", "high"):
            res = []
            for o in self.catalogue:
                ov: dict[str, Scenario] = {}
                if sc != "base":
                    for aid in self.a:
                        cost_like = aid.startswith(COST_LIKE_PREFIXES)
                        pessimistic = sc == "low"
                        ov[aid] = (
                            ("high" if cost_like else "low")
                            if pessimistic
                            else ("low" if cost_like else "high")
                        )
                res.append(self.evaluate(o, "base", ov).model_copy(update={"scenario": sc}))
            out[sc] = classify(res)
        return out


QUICK_WIN_MAX_TTV_MONTHS = 3
QUICK_WIN_MAX_IMPL_USD = 80_000
STRATEGIC_MIN_NPV_USD = 100_000


def classify(results: list[OpportunityResult]) -> list[OpportunityResult]:
    """Explicit priority rules (documented in ADR-007) plus 0-10 relative scores for the matrix.

    deprioritize: NPV <= 0 | quick_win: TTV <= 3 mo and impl <= $80k |
    strategic_bet: NPV >= $100k | otherwise fill_in.
    """
    if not results:
        return results
    max_v = max(r.annual_value_usd for r in results) or 1.0
    max_c = max(r.implementation_cost_usd for r in results) or 1.0
    max_t = max(r.time_to_value_months for r in results) or 1.0
    out = []
    for r in results:
        v = round(10 * max(r.annual_value_usd, 0) / max_v, 2)
        e = round(
            10
            * (
                0.5 * r.implementation_cost_usd / max_c
                + 0.3 * r.time_to_value_months / max_t
                + 0.2 * r.regulatory_sensitivity / 5
            ),
            2,
        )
        if r.npv_usd <= 0:
            p = "deprioritize"
        elif (
            r.time_to_value_months <= QUICK_WIN_MAX_TTV_MONTHS
            and r.implementation_cost_usd <= QUICK_WIN_MAX_IMPL_USD
        ):
            p = "quick_win"
        elif r.npv_usd >= STRATEGIC_MIN_NPV_USD:
            p = "strategic_bet"
        else:
            p = "fill_in"
        out.append(r.model_copy(update={"value_score": v, "effort_score": e, "priority": p}))
    return sorted(out, key=lambda r: r.npv_usd, reverse=True)
