# VisualHFT Positions / Orders tab empty

Upstream: [visualHFT/VisualHFT#46](https://github.com/visualHFT/VisualHFT/issues/46).

This is usually **not** a missing API key. The desktop Positions/Orders grid only
shows orders for the **selected session date** (top-right), and the default
filter is **Working** (open orders only). Filled / historical orders are hidden.

## Operator checklist (no code)

1. Confirm a connector that streams **private user orders** is started (e.g.
   Kraken with `InitializeUserPrivateOrders`). Public L2-only plugins never
   populate Positions.
2. Set the session date control to **today** (maintainer note: only today’s
   date is supported until historical session pull lands).
3. Switch the orders filter from **Working** → **All** or **Filled**.
4. Confirm keys belong to an account that actually has orders **today**.

## Code fix (recommended on your VisualHFT fork)

Cloud agents cannot push to `afidurko/VisualHFT` with the current token. Apply
this patch locally on Windows against the fork:

```bash
cd /path/to/VisualHFT
git apply /path/to/AOA-Financial/patches/visualhft/0001-positions-orders-empty-ux.patch
```

Or edit `ViewModel/vmPosition.cs` manually:

1. Default `_selectedFilter` / `SelectedFilter` to `"All"` (not `"Working"`).
2. In `ReloadOrders()`, **do not** reset `SelectedFilter = "Working"` — call
   `ApplyFilter()` so the user’s filter is preserved.
3. Optionally expose an `EmptyOrdersHint` string when the filtered view is empty.

## Plugin Manager (upstream #29)

[visualHFT/VisualHFT#29](https://github.com/visualHFT/VisualHFT/issues/29) is a
large product enhancement (marketplace, versioning, paid plugins). It is **not**
a one-line bug fix. Track upstream; AOA’s Python study lane does not depend on it.

## AOA side

```bash
./scripts/visualhft-setup.sh
./scripts/workspaces-setup-all.sh
export AOA_VISUALHFT_URL=https://github.com/afidurko/VisualHFT
aoa workspaces status
aoa visualhft smoke
```
