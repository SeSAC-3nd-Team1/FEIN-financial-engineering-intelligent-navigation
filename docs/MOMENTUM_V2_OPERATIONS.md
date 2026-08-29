# Momentum v2 service operation

The service default for `strategy_id=momentum` is `risk-adjusted-momentum-v2`.
`price-momentum-v1` remains available only as a research/baseline model.

1. Load the current Feature Store history (including listed shares and market cap).
2. Run `docker compose --profile ai run --rm recommendation-generator`.
3. Confirm `/model-artifacts/risk-adjusted-momentum-v2.json` is `ready`, generated,
   fresh, has 19--20 recommendations, a 0.95 total, and no weight above 0.05.
4. The Backend reads that artifact for the initial AUTO virtual investment.
5. At a later quarter, call the internal `MomentumInvestmentService.rebalance` job
   for eligible AUTO momentum accounts. It calculates values at current market
   prices, sells before buying, and records snapshot/account/symbol/side keys.

Artifact publication is atomic. A failed generator run does not replace the
previous artifact. Automatic investment and rebalancing reject missing, fallback,
stale, non-ready, non-v2, or invalid-weight snapshots; they never fall back to v1.

## Production boundary and remaining risks

The repository currently provides the generator command and an internal Backend
rebalance operation. Production deployment does not yet schedule the generator,
mount `/model-artifacts` into the Container App, or invoke quarterly rebalancing
automatically. Until those Azure Job/volume/scheduler resources are configured,
AUTO execution is intentionally manual and must be treated as an operational
precondition rather than an unattended production workflow.

The service backtest keeps correctness by loading the full point-in-time symbol
set and recomputing v2 features. A production-sized dataset should be benchmarked
before enabling long-range requests; a versioned feature/target cache is the next
recommended optimization without changing the point-in-time universe contract.
