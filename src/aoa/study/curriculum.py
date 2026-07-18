"""Seed curriculum: DE ↔ physics ↔ economics with proofs and AOA mesh.

No external textbooks required — cards encode the critical graduate cores
needed for applications and cross-field transfer.
"""

from __future__ import annotations

from dataclasses import dataclass

FIELDS = ("de", "physics", "econ", "bridge")


@dataclass(frozen=True)
class KnowledgeCard:
    """One integrable concept: statement, proof sketch, applications, mesh."""

    id: str
    field: str
    title: str
    statement: str
    proof_sketch: str
    applications: tuple[str, ...] = ()
    aoa_mesh: str = ""
    bridges: tuple[str, ...] = ()
    drill_prompt: str = ""
    check_keywords: tuple[str, ...] = ()

    def to_context(self) -> dict:
        return {
            "id": self.id,
            "field": self.field,
            "title": self.title,
            "statement": self.statement,
            "proof_sketch": self.proof_sketch,
            "applications": list(self.applications),
            "aoa_mesh": self.aoa_mesh,
            "bridges": list(self.bridges),
            "drill_prompt": self.drill_prompt,
            "check_keywords": list(self.check_keywords),
        }

    def training_pair(self) -> dict[str, str]:
        """Instruction/response pair for future LoRA / sLM distillation."""
        apps = "; ".join(self.applications)
        response = (
            f"Statement: {self.statement}\n\n"
            f"Proof sketch:\n{self.proof_sketch}\n\n"
            f"Applications: {apps}\n\n"
            f"AOA mesh: {self.aoa_mesh}"
        )
        return {
            "instruction": self.drill_prompt or f"State and prove: {self.title}",
            "response": response,
            "card_id": self.id,
            "field": self.field,
        }


_CARDS: tuple[KnowledgeCard, ...] = (
    KnowledgeCard(
        id="de-picard",
        field="de",
        title="Picard–Lindelöf existence and uniqueness",
        statement=(
            "If f is Lipschitz in y (uniformly in t on a rectangle) and continuous in t, "
            "the IVP y'=f(t,y), y(t0)=y0 has a unique local solution."
        ),
        proof_sketch=(
            "1) Rewrite as integral equation y = T[y] = y0 + ∫_{t0}^t f(s,y(s)) ds.\n"
            "2) On a small ball in C([t0,t0+h]), T is a contraction (Lipschitz + small h).\n"
            "3) Banach fixed-point ⇒ unique fixed point = unique local solution.\n"
            "4) Continuability: extend until the graph exits every compact set."
        ),
        applications=(
            "ODE well-posedness for mean-reverting signals",
            "Unique filter trajectories given Lipschitz updates",
        ),
        aoa_mesh=(
            "Plasticity trust updates and signal adapters must be Lipschitz-bounded "
            "so online learning has a unique trajectory per cycle history."
        ),
        bridges=("bridge-ou-meanrev", "de-gronwall"),
        drill_prompt=(
            "State Picard–Lindelöf. Outline the contraction-mapping proof and "
            "what fails without a Lipschitz condition."
        ),
        check_keywords=("lipschitz", "contraction", "banach", "integral", "unique"),
    ),
    KnowledgeCard(
        id="de-gronwall",
        field="de",
        title="Gronwall inequality",
        statement=(
            "If u(t) ≤ α + ∫_{t0}^t β(s)u(s) ds with β≥0, then "
            "u(t) ≤ α exp(∫_{t0}^t β)."
        ),
        proof_sketch=(
            "1) Let R(t)=α+∫ β u. Then u≤R and R'=β u ≤ β R.\n"
            "2) For R>0, (ln R)' ≤ β ⇒ ln R(t)−ln α ≤ ∫β ⇒ R≤α e^{∫β}.\n"
            "3) Hence u≤α e^{∫β}. Discrete and differential forms follow similarly."
        ),
        applications=(
            "Continuous dependence on initial data",
            "Stability estimates for numerical schemes",
        ),
        aoa_mesh=(
            "Bounds how far conviction/trust can drift under noisy cycle shocks — "
            "use as a sanity envelope on plasticity updates."
        ),
        bridges=("de-picard", "de-lyapunov"),
        drill_prompt="State Gronwall's inequality and prove the integral form.",
        check_keywords=("integral", "exp", "beta", "continuous dependence"),
    ),
    KnowledgeCard(
        id="de-lyapunov",
        field="de",
        title="Lyapunov stability for autonomous systems",
        statement=(
            "If V is C¹, positive definite near an equilibrium x*, and V̇≤0, "
            "then x* is stable; if V̇<0 (definite), it is asymptotically stable."
        ),
        proof_sketch=(
            "1) Stability: sublevel sets {V≤c} are positively invariant when V̇≤0; "
            "shrink c so the set sits in any neighborhood of x*.\n"
            "2) Asymptotic: LaSalle or strict decrease ⇒ trajectories approach the "
            "largest invariant set in {V̇=0}, which is {x*} when V̇ is definite."
        ),
        applications=(
            "Prove mean-reversion equilibria are attracting",
            "Certify risk dampers do not oscillate unboundedly",
        ),
        aoa_mesh=(
            "Treat portfolio exposure error as state; design a Lyapunov-like "
            "penalty so risk guards drive the state toward the cash-feasible set."
        ),
        bridges=("bridge-ou-meanrev", "econ-hjb"),
        drill_prompt=(
            "Define Lyapunov stability vs asymptotic stability. Give the V / V̇ "
            "criteria and a one-line LaSalle idea."
        ),
        check_keywords=("positive definite", "vdot", "invariant", "asymptotic"),
    ),
    KnowledgeCard(
        id="de-fundamental-matrix",
        field="de",
        title="Fundamental matrix for linear ODEs",
        statement=(
            "For x'=A(t)x, a fundamental matrix Φ satisfies Φ'=AΦ and det Φ≠0; "
            "solutions are x=Φ c. For constant A, Φ(t)=exp(tA)."
        ),
        proof_sketch=(
            "1) Columns of Φ are independent solutions ⇒ span the solution space.\n"
            "2) Abel/Liouville: (det Φ)' = tr(A) det Φ ⇒ det never zero if nonzero once.\n"
            "3) Variation of parameters for x'=Ax+g uses Φ∫ Φ^{-1}g."
        ),
        applications=(
            "Closed-form factor dynamics",
            "Impulse-response of linear signal filters",
        ),
        aoa_mesh=(
            "Multi-timeframe technical features are a linear filter bank; "
            "the fundamental matrix is the propagator of that filter."
        ),
        bridges=("de-heat-fourier", "bridge-bs-heat"),
        drill_prompt=(
            "Define a fundamental matrix. State Liouville's formula and how "
            "variation of parameters uses Φ."
        ),
        check_keywords=("fundamental", "liouville", "variation of parameters", "exp"),
    ),
    KnowledgeCard(
        id="de-heat-fourier",
        field="de",
        title="Heat equation via Fourier / Gaussian kernel",
        statement=(
            "u_t = κ u_xx on ℝ has solution u(·,t)=G_t * u0 with "
            "G_t(x)=(4πκt)^{-1/2} exp(-x²/(4κt))."
        ),
        proof_sketch=(
            "1) Fourier transform: û_t = −κ ξ² û ⇒ û(ξ,t)=û0(ξ)e^{-κξ²t}.\n"
            "2) Inverse transform of e^{-κξ²t} is the Gaussian kernel G_t.\n"
            "3) Convolution theorem ⇒ u=G_t*u0. Maximum principle ⇒ uniqueness."
        ),
        applications=(
            "Diffusive smoothing of noisy series",
            "Link to Black–Scholes after log-price change of variables",
        ),
        aoa_mesh=(
            "News/sentiment shocks diffuse across correlated names; "
            "kernel width ~ effective information half-life."
        ),
        bridges=("bridge-bs-heat", "phys-diffusion"),
        drill_prompt=(
            "Derive the fundamental solution of the heat equation on the line "
            "using Fourier transforms."
        ),
        check_keywords=("fourier", "gaussian", "convolution", "maximum principle"),
    ),
    KnowledgeCard(
        id="phys-lagrangian",
        field="physics",
        title="Euler–Lagrange equations",
        statement=(
            "Stationarity of S[q]=∫ L(q,q̇,t) dt implies "
            "d/dt(∂L/∂q̇)=∂L/∂q for each coordinate."
        ),
        proof_sketch=(
            "1) Vary q→q+εη with η vanishing at endpoints.\n"
            "2) δS=∫(∂L/∂q η + ∂L/∂q̇ η̇)dt = 0.\n"
            "3) Integrate by parts on the η̇ term; arbitrary η ⇒ Euler–Lagrange."
        ),
        applications=(
            "Derive equations of motion from energy functionals",
            "Constrained optimization via extended Lagrangians",
        ),
        aoa_mesh=(
            "Portfolio choice can be cast as extremizing an expected-utility "
            "action with constraints enforced by multipliers (risk guards)."
        ),
        bridges=("phys-hamiltonian", "econ-kuhn-tucker", "phys-noether"),
        drill_prompt="Derive the Euler–Lagrange equation from δS=0.",
        check_keywords=("variation", "integrate by parts", "euler", "stationary"),
    ),
    KnowledgeCard(
        id="phys-hamiltonian",
        field="physics",
        title="Hamiltonian phase-space dynamics",
        statement=(
            "With p=∂L/∂q̇ and H=p q̇−L, Hamilton's equations are "
            "q̇=∂H/∂p, ṗ=−∂H/∂q. H is conserved if ∂L/∂t=0."
        ),
        proof_sketch=(
            "1) Legendre transform L→H assumed regular (convex in q̇).\n"
            "2) dH= q̇ dp − (∂L/∂q)dq − (∂L/∂t)dt; substitute EL ⇒ Hamilton form.\n"
            "3) Ḣ=∂H/∂t, so autonomy ⇒ conservation of H."
        ),
        applications=(
            "Phase-space portraits for oscillators and regimes",
            "Symplectic integrators preserve qualitative structure",
        ),
        aoa_mesh=(
            "Cycle checkpoints are phase-space snapshots of the swarm state; "
            "meshing edits should be symplectic-like (structure-preserving), "
            "not arbitrary overwrites."
        ),
        bridges=("phys-lagrangian", "econ-hjb", "phys-noether"),
        drill_prompt=(
            "Define the Hamiltonian via Legendre transform and derive "
            "Hamilton's equations."
        ),
        check_keywords=("legendre", "phase space", "conserved", "hamilton"),
    ),
    KnowledgeCard(
        id="phys-noether",
        field="physics",
        title="Noether's theorem (sketch)",
        statement=(
            "A continuous symmetry of the action yields a conserved current; "
            "time-translation ⇒ energy, space-translation ⇒ momentum."
        ),
        proof_sketch=(
            "1) Infinitesimal symmetry: δq=ε K(q,t) leaves S invariant up to a "
            "total time derivative.\n"
            "2) On-shell, the EL identity rearranges to d/dt(p·K − F)=0.\n"
            "3) That density is the Noether charge."
        ),
        applications=(
            "Identify invariants before solving dynamics",
            "Check numerical schemes for spurious drift of conserved quantities",
        ),
        aoa_mesh=(
            "Cash-account invariant: risk guards are the 'symmetry' enforcing "
            "conservation of feasibility (no margin). Breaking the symmetry "
            "(live without ack) is forbidden."
        ),
        bridges=("phys-lagrangian", "phys-hamiltonian"),
        drill_prompt=(
            "State Noether's theorem and identify the conserved quantity for "
            "time-translation invariance."
        ),
        check_keywords=("symmetry", "conserved", "energy", "noether"),
    ),
    KnowledgeCard(
        id="phys-diffusion",
        field="physics",
        title="Diffusion, Brownian motion, and Fokker–Planck",
        statement=(
            "For dX=μ dt+σ dW, the density p satisfies the Fokker–Planck PDE "
            "p_t=−∂x(μ p)+½∂xx(σ² p)."
        ),
        proof_sketch=(
            "1) Itô on f(X): df= (μ f'+½σ² f'')dt + σ f' dW.\n"
            "2) Take expectations; integrate by parts against p ⇒ weak form of FP.\n"
            "3) Stationary density balances drift and diffusion fluxes."
        ),
        applications=(
            "Option pricing kernels",
            "Hitting-time / stop-loss probabilities",
        ),
        aoa_mesh=(
            "Monte-Carlo simulator paths are discrete Itô; scenario stress is "
            "changing (μ,σ) and re-reading the Fokker–Planck mass in the tails."
        ),
        bridges=("de-heat-fourier", "bridge-bs-heat", "bridge-ou-meanrev"),
        drill_prompt=(
            "Write the Fokker–Planck equation for dX=μ dt+σ dW and sketch the "
            "Itô-to-PDE derivation."
        ),
        check_keywords=("ito", "fokker", "density", "diffusion"),
    ),
    KnowledgeCard(
        id="econ-kuhn-tucker",
        field="econ",
        title="Karush–Kuhn–Tucker conditions",
        statement=(
            "For min f(x) s.t. g(x)≤0, h(x)=0 (constraint qualifications), "
            "optima satisfy ∇f+λ∇g+μ∇h=0, λ≥0, λ·g=0, primal feasibility."
        ),
        proof_sketch=(
            "1) Form Lagrangian L=f+λg+μh.\n"
            "2) Under LICQ/MFCQ, no feasible descent direction ⇒ stationarity.\n"
            "3) Complementary slackness: inactive inequalities have λ_i=0.\n"
            "4) Sufficiency under convexity of f and g."
        ),
        applications=(
            "Consumer/producer problems with inequality constraints",
            "Portfolio caps and cash buffers as KKT inequalities",
        ),
        aoa_mesh=(
            "Deterministic risk guards are primal constraints; rejected proposals "
            "are complementary-slackness failures (λ>0 on the binding cap)."
        ),
        bridges=("phys-lagrangian", "econ-bellman"),
        drill_prompt=(
            "State the KKT conditions. Explain complementary slackness with a "
            "single inequality constraint."
        ),
        check_keywords=("lagrangian", "complementary", "stationarity", "qualification"),
    ),
    KnowledgeCard(
        id="econ-bellman",
        field="econ",
        title="Bellman principle / dynamic programming",
        statement=(
            "V(x)=max_a { r(x,a) + γ E[V(x')|x,a] }. Optimal policies solve this "
            "fixed point under contraction of the Bellman operator (γ<1)."
        ),
        proof_sketch=(
            "1) Principle of optimality: suffixes of optimal plans are optimal.\n"
            "2) Bellman operator T is a γ-contraction on bounded functions.\n"
            "3) Banach ⇒ unique V*; policy improvement / value iteration converge."
        ),
        applications=(
            "Discrete trading/inventory problems",
            "When to realize gains vs hold under costs",
        ),
        aoa_mesh=(
            "Each swarm cycle is one DP stage; plasticity lessons approximate "
            "value-shaping bonuses from past realizations."
        ),
        bridges=("econ-hjb", "econ-kuhn-tucker", "de-picard"),
        drill_prompt=(
            "Write the Bellman equation. Why is the Bellman operator a contraction?"
        ),
        check_keywords=("contraction", "principle of optimality", "value", "gamma"),
    ),
    KnowledgeCard(
        id="econ-hjb",
        field="econ",
        title="Hamilton–Jacobi–Bellman equation",
        statement=(
            "In continuous time, 0=max_a { r(x,a) + ∇V·μ(x,a) + ½ tr(σσᵀ Hess V) } "
            "− δ V (plus boundary terms), the infinitesimal Bellman equation."
        ),
        proof_sketch=(
            "1) Discrete DP over dt, expand V(x+dx) by Itô.\n"
            "2) Divide by dt, send dt→0 ⇒ HJB.\n"
            "3) Viscosity solutions handle nonsmooth V; verification theorems "
            "recover optimality when a classical solution exists."
        ),
        applications=(
            "Merton portfolio problem",
            "Optimal execution with diffusion prices",
        ),
        aoa_mesh=(
            "Options strategist + portfolio manager approximate a constrained HJB: "
            "maximize expected utility subject to cash-account σ-structure."
        ),
        bridges=("econ-bellman", "phys-hamiltonian", "phys-diffusion", "bridge-bs-heat"),
        drill_prompt=(
            "Derive the HJB equation from discrete dynamic programming plus Itô's lemma."
        ),
        check_keywords=("ito", "infinitesimal", "viscosity", "verification"),
    ),
    KnowledgeCard(
        id="econ-nash",
        field="econ",
        title="Nash equilibrium existence (finite games)",
        statement=(
            "Every finite strategic-form game has a mixed-strategy Nash equilibrium "
            "(Nash 1950), via a Kakutani fixed-point on best-response correspondences."
        ),
        proof_sketch=(
            "1) Mixed strategy simplex is compact convex.\n"
            "2) Best-response correspondence is nonempty, convex-valued, u.h.c.\n"
            "3) Kakutani ⇒ fixed point = Nash profile.\n"
            "4) Pure equilibria need not exist; mixed ones do."
        ),
        applications=(
            "Bull/bear research debates",
            "Risk-seeking vs conservative committees",
        ),
        aoa_mesh=(
            "TradingAgents research/risk debates seek a facilitator-selected "
            "equilibrium of competing theses — not a pure-strategy consensus."
        ),
        bridges=("econ-bellman", "bridge-sdf-martingale"),
        drill_prompt=(
            "State Nash's existence theorem for finite games and sketch the "
            "fixed-point argument."
        ),
        check_keywords=("kakutani", "best response", "mixed", "simplex"),
    ),
    KnowledgeCard(
        id="bridge-bs-heat",
        field="bridge",
        title="Black–Scholes ↔ heat equation",
        statement=(
            "Under dS=μS dt+σS dW, a European claim satisfies the BS PDE; "
            "x=log S and τ=T−t (with discounting) reduce it to the heat equation."
        ),
        proof_sketch=(
            "1) Itô on V(S,t); impose driftless discounted portfolio ⇒ BS PDE.\n"
            "2) Set x=ln S, τ=T−t, strip lower-order terms by exponential integrating factor.\n"
            "3) Remaining operator is κ ∂xx − ∂τ. Solve with Gaussian kernel; transform back."
        ),
        applications=(
            "Closed-form calls/puts",
            "Greeks as heat-kernel sensitivities",
        ),
        aoa_mesh=(
            "Andrea/FinancePy context and options strategist inherit this map: "
            "vol = diffusion coefficient in the heat picture."
        ),
        bridges=("de-heat-fourier", "phys-diffusion", "econ-hjb"),
        drill_prompt=(
            "Show how the Black–Scholes PDE reduces to the heat equation under "
            "log-price and time-to-maturity coordinates."
        ),
        check_keywords=("log", "heat", "ito", "volatility", "european"),
    ),
    KnowledgeCard(
        id="bridge-ou-meanrev",
        field="bridge",
        title="Ornstein–Uhlenbeck ↔ mean reversion",
        statement=(
            "dX=θ(μ−X)dt+σ dW is Gaussian, Markov, mean-reverting with "
            "E[X_t]=μ+(x0−μ)e^{-θt} and known variance envelope."
        ),
        proof_sketch=(
            "1) Integrating factor e^{θt}: d(e^{θt}X)=θμ e^{θt}dt + σ e^{θt}dW.\n"
            "2) Integrate; take expectation ⇒ exponential pull to μ.\n"
            "3) Itô isometry ⇒ Var→ σ²/(2θ). Lyapunov V=(x−μ)² gives asymptotic stability of the mean."
        ),
        applications=(
            "Pairs trading / residual z-scores",
            "Trust score pull-to-prior in plasticity",
        ),
        aoa_mesh=(
            "Symbol trust and low-rank signal adapters should OU-revert toward 0 "
            "unless reinforced — prevents runaway conviction from one lucky cycle."
        ),
        bridges=("de-lyapunov", "phys-diffusion", "de-picard"),
        drill_prompt=(
            "Solve the OU SDE for the mean path and explain the stationary variance."
        ),
        check_keywords=("integrating factor", "mean", "variance", "theta", "stationary"),
    ),
    KnowledgeCard(
        id="bridge-free-energy",
        field="bridge",
        title="Free energy ↔ certainty-equivalent utility",
        statement=(
            "In exponential utility / Gibbs measures, F=−β^{-1} log ∫ e^{-β E} "
            "plays the role of a certainty equivalent; minimizing free energy "
            "⇔ maximizing entropic utility."
        ),
        proof_sketch=(
            "1) Softmax / Gibbs: p∝ e^{-β E}.\n"
            "2) Free energy F=E_p[E]−β^{-1} H(p).\n"
            "3) Variational principle: F=−β^{-1} log Z. Map E→loss, β→ risk aversion."
        ),
        applications=(
            "Risk-sensitive control",
            "Temperature-like exploration in debates",
        ),
        aoa_mesh=(
            "Alan/risk veto temperature: higher β ⇒ sharper rejection of fragile "
            "proposals; free-energy view unifies physics and portfolio choice."
        ),
        bridges=("phys-diffusion", "econ-hjb", "econ-kuhn-tucker"),
        drill_prompt=(
            "Define Helmholtz free energy for a Gibbs measure and relate it to "
            "entropic / exponential utility."
        ),
        check_keywords=("gibbs", "entropy", "beta", "certainty", "variational"),
    ),
    KnowledgeCard(
        id="bridge-sdf-martingale",
        field="bridge",
        title="SDF / risk-neutral martingale pricing",
        statement=(
            "No-arbitrage (FTAP) ⇔ existence of an equivalent measure Q under which "
            "discounted traded assets are martingales; prices are E^Q[payoff]."
        ),
        proof_sketch=(
            "1) Define gains processes; NA ⇒ separating hyperplane ⇒ state prices.\n"
            "2) Normalize to a probability Q∼P; discounted price = conditional expectation.\n"
            "3) Complete markets ⇒ unique Q; incomplete ⇒ a convex set of Q's."
        ),
        applications=(
            "Derivative pricing consistency checks",
            "Detect static arbitrage in option chains",
        ),
        aoa_mesh=(
            "Options strategist must not propose structures that admit static "
            "arbitrage vs the chain; risk manager enforces cash feasibility on top."
        ),
        bridges=("bridge-bs-heat", "econ-nash", "econ-hjb"),
        drill_prompt=(
            "State the First Fundamental Theorem of Asset Pricing and explain "
            "the role of the risk-neutral measure."
        ),
        check_keywords=("martingale", "equivalent", "no-arbitrage", "measure", "discount"),
    ),
)


def all_cards() -> tuple[KnowledgeCard, ...]:
    return _CARDS


def get_card(card_id: str) -> KnowledgeCard | None:
    for card in _CARDS:
        if card.id == card_id:
            return card
    return None


def cards_by_field(field: str) -> list[KnowledgeCard]:
    field = field.strip().lower()
    return [c for c in _CARDS if c.field == field]


def related_cards(card_id: str) -> list[KnowledgeCard]:
    card = get_card(card_id)
    if card is None:
        return []
    out: list[KnowledgeCard] = []
    for bid in card.bridges:
        other = get_card(bid)
        if other is not None:
            out.append(other)
    return out
