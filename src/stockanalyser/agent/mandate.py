"""The research mandate — the three coordinates fixed before any data is pulled.

Every run is parameterised by a ``Mandate`` = (Side × Market × Depth):

* **Side**  — sell-side (a recommendation for clients) vs buy-side (a capital
  decision for a book). Reframes the whole output.
* **Market** — the geography/regime profile (see :mod:`.markets`).
* **Depth** — how far down to drill, L0 (snapshot) → L5 (living coverage).

The :class:`MandateRouter` sets these from explicit arguments, falling back to
light keyword inference over the request, and finally to sensible defaults. The
market is intentionally allowed to stay *generic* here and be refined once the
listing is resolved and its exchange is known.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum

from .markets import MarketProfile, GENERIC, infer_profile


class Side(str, Enum):
    SELL_SIDE = "sell-side"
    BUY_SIDE = "buy-side"

    @property
    def label(self) -> str:
        return "Sell-side" if self is Side.SELL_SIDE else "Buy-side"


class Depth(IntEnum):
    SNAPSHOT = 0      # L0 — quick take
    SCREEN = 1        # L1 — triage
    BRIEF = 2         # L2 — company brief / tearsheet
    DEEP_DIVE = 3     # L3 — full model + thesis
    INITIATION = 4    # L4 — initiation of coverage
    COVERAGE = 5      # L5 — living coverage

    @property
    def code(self) -> str:
        return f"L{int(self)}"

    @property
    def label(self) -> str:
        return {
            0: "L0 · Snapshot",
            1: "L1 · Screen",
            2: "L2 · Company Brief",
            3: "L3 · Deep Dive",
            4: "L4 · Initiation",
            5: "L5 · Living Coverage",
        }[int(self)]


# ── keyword inference tables ─────────────────────────────────────────────────
_BUY_SIDE_CUES = (
    "buy side", "buy-side", "buyside", "should i buy", "should i own", "position",
    "position size", "sizing", "portfolio", "hedge fund", "pm view", "ic memo",
    "own it", "go long", "short candidate", "risk/reward", "risk reward",
)
_SELL_SIDE_CUES = (
    "sell side", "sell-side", "sellside", "initiate", "initiation", "coverage",
    "price target", "rating", "recommend", "recommendation", "publish", "client note",
)
# order matters: deeper phrases win over shallow ones
_DEPTH_CUES: tuple[tuple[tuple[str, ...], Depth], ...] = (
    (("living coverage", "maintain coverage", "earnings preview", "earnings review",
      "estimate revision", "update the model", "post-results"), Depth.COVERAGE),
    (("initiate", "initiation", "initiating coverage", "full initiation"), Depth.INITIATION),
    (("deep dive", "deep-dive", "full thesis", "build a model", "dcf", "sum-of-the-parts",
      "sotp", "variant"), Depth.DEEP_DIVE),
    (("brief", "tearsheet", "tear sheet", "one pager", "one-pager", "overview"), Depth.BRIEF),
    (("screen", "triage", "shortlist", "which of these", "rank these"), Depth.SCREEN),
    (("snapshot", "quick take", "quick look", "quick read", "tl;dr", "at a glance"),
     Depth.SNAPSHOT),
)


@dataclass
class Mandate:
    side: Side
    depth: Depth
    market: MarketProfile
    inferred: dict[str, bool] = field(default_factory=dict)

    @property
    def headline(self) -> str:
        return f"{self.side.label} · {self.depth.label} · {self.market.name}"

    def with_market(self, market: MarketProfile) -> "Mandate":
        """Return a copy with the market refined (keeps inference bookkeeping)."""
        note = dict(self.inferred)
        note["market"] = True
        return Mandate(side=self.side, depth=self.depth, market=market, inferred=note)


class MandateRouter:
    """Turns a free-text request + optional overrides into a :class:`Mandate`."""

    def __init__(
        self,
        default_side: Side = Side.SELL_SIDE,
        default_depth: Depth = Depth.BRIEF,
    ) -> None:
        self.default_side = default_side
        self.default_depth = default_depth

    def route(
        self,
        query: str,
        *,
        side: Side | str | None = None,
        depth: Depth | int | str | None = None,
        market: str | None = None,
    ) -> Mandate:
        q = (query or "").lower()
        inferred: dict[str, bool] = {}

        # ── side ──
        if side is not None:
            resolved_side = _coerce_side(side)
        else:
            hit = self._infer_side(q)
            inferred["side"] = hit is not None
            resolved_side = hit if hit is not None else self.default_side

        # ── depth ── (note: Depth.SNAPSHOT == 0 is falsy, so test `is not None`)
        if depth is not None:
            resolved_depth = _coerce_depth(depth)
        else:
            hit = self._infer_depth(q)
            inferred["depth"] = hit is not None
            resolved_depth = hit if hit is not None else self.default_depth

        # ── market (may stay generic, refined after resolve) ──
        profile = infer_profile(market=market, query=query)
        inferred["market"] = market is None and not profile.is_generic

        return Mandate(side=resolved_side, depth=resolved_depth,
                       market=profile, inferred=inferred)

    @staticmethod
    def _infer_side(q: str) -> Side | None:
        buy = any(cue in q for cue in _BUY_SIDE_CUES)
        sell = any(cue in q for cue in _SELL_SIDE_CUES)
        if buy and not sell:
            return Side.BUY_SIDE
        if sell and not buy:
            return Side.SELL_SIDE
        return None

    @staticmethod
    def _infer_depth(q: str) -> Depth | None:
        for phrases, depth in _DEPTH_CUES:
            if any(phrase in q for phrase in phrases):
                return depth
        return None


def _coerce_side(value: Side | str) -> Side:
    if isinstance(value, Side):
        return value
    v = str(value).strip().lower().replace("_", "-")
    if v in ("buy", "buy-side", "buyside", "b"):
        return Side.BUY_SIDE
    if v in ("sell", "sell-side", "sellside", "s"):
        return Side.SELL_SIDE
    raise ValueError(f"Unknown side: {value!r} (use 'sell-side' or 'buy-side')")


def _coerce_depth(value: Depth | int | str) -> Depth:
    if isinstance(value, Depth):
        return value
    if isinstance(value, int):
        return Depth(value)
    v = str(value).strip().lower()
    aliases = {
        "l0": Depth.SNAPSHOT, "snapshot": Depth.SNAPSHOT, "quick": Depth.SNAPSHOT,
        "l1": Depth.SCREEN, "screen": Depth.SCREEN, "triage": Depth.SCREEN,
        "l2": Depth.BRIEF, "brief": Depth.BRIEF, "tearsheet": Depth.BRIEF,
        "l3": Depth.DEEP_DIVE, "deep": Depth.DEEP_DIVE, "deep-dive": Depth.DEEP_DIVE,
        "l4": Depth.INITIATION, "initiation": Depth.INITIATION, "initiate": Depth.INITIATION,
        "l5": Depth.COVERAGE, "coverage": Depth.COVERAGE, "living": Depth.COVERAGE,
    }
    if v in aliases:
        return aliases[v]
    if v.isdigit():
        return Depth(int(v))
    raise ValueError(f"Unknown depth: {value!r} (use L0..L5 or a name)")
