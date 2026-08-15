# Microstructure research lanes (workspace mesh)

AOA Financial meshes several **offline** HFT / LOB companions into one workspace.
None of these lanes place paper or live orders. Use
`aoa microstructure status` for a single availability snapshot.

## Lane map

| Lane | CLI / module | Companion repo | Role |
|------|--------------|----------------|------|
| Avellaneda–Stoikov | `aoa avellaneda` · `aoa.avellaneda_stoikov` | [avellaneda-stoikov](https://github.com/afidurko/avellaneda-stoikov) | Reservation price + optimal quotes + Monte-Carlo |
| VisualHFT studies | `aoa visualhft` · `aoa.visualhft` | [VisualHFT](https://github.com/afidurko/VisualHFT) | LOB imbalance, VPIN, OTR |
| hftbacktest + LOB | `aoa hft` · `aoa.hftbacktest` / `aoa.orderbook` | [hftbacktest](https://github.com/afidurko/hftbacktest), [HFT-Orderbook](https://github.com/afidurko/HFT-Orderbook) | Tick replay (optional) + vendored book |
| HFT patterns | `aoa.research.hft_patterns` | [hft](https://github.com/afidurko/hft) | Pairs bands, hedged maker, MA cross ideas |
| example-hftish | `aoa.research.hftish_patterns` | [example-hftish](https://github.com/afidurko/example-hftish) | Penny level-change / size imbalance |
| SGX order book | `aoa.research.sgx_orderbook_patterns` | [SGX-Full-OrderBook-…](https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy) | Depth rise / weighted book features |

## Commands

```bash
aoa microstructure status
aoa microstructure status --json

aoa avellaneda smoke
aoa visualhft smoke
aoa hft status
aoa hft book-smoke
```

## Safety

- All lanes report `offline_only` / `never_live`
- Not wired into `Executor`, swarm stages, or `AOA_ENV=live`
- Hard Safety Floor in `loop-constraints.md` still applies
- Sibling C++/desktop stacks are reference clones only (`./scripts/*-setup.sh`)

## Related how-tos

- [avellaneda-stoikov.md](avellaneda-stoikov.md)
- [visualhft-integration.md](visualhft-integration.md)
- [hftbacktest-integration.md](hftbacktest-integration.md)
- [hft-reference.md](hft-reference.md)
- [example-hftish-reference.md](example-hftish-reference.md)
- [sgx-orderbook-reference.md](sgx-orderbook-reference.md) (when present)
