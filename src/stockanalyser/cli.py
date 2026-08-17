"""Command-line interface.

    stockanalyser analyse "Hitachi Energy"          # terminal summary
    stockanalyser analyse POWERINDIA --html out.html # + dashboard
    stockanalyser analyse RELIANCE --json out.json   # machine-readable
    stockanalyser list                               # bundled sample companies
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from .config import Config
from .data.offline import OfflineProvider
from .report import build_report, CompanyNotFound, render_dashboard, report_to_json

# ANSI (skipped when not a tty)
def _c(code, s, tty):
    return f"\033[{code}m{s}\033[0m" if tty else s


def _print_report(report, tty):
    c = report.company
    bar = "═" * 58
    print(_c("1", f"\n{bar}", tty))
    print(_c("1", f" {c.name}  ({c.ticker})", tty))
    print(f" {c.sector or 'Sector n/a'} · {c.industry or ''}")
    print(_c("1", bar, tty))
    v = report.verdict.value
    vcolor = "32" if "Buy" in v else "31" if "Avoid" in v else "33"
    print(f" Composite: {_c('1', str(report.composite_score)+'/100', tty)}   "
          f"Verdict: {_c(vcolor+';1', v, tty)}")
    print()
    for name, lens in report.lenses.items():
        score = f"{lens.score:>5}" if lens.score is not None else "  n/a"
        col = "32" if (lens.score or 0) >= 60 else "31" if (lens.score or 100) < 45 else "33"
        print(f"  {_c(col, score, tty)}  {_c('1', name.ljust(12), tty)} {lens.summary[:96]}")
    print()
    print(_c("1", " Analyst read", tty))
    print(f"   {report.narrative}\n")
    if report.bull_thesis:
        print(_c("32;1", " Bull case:", tty))
        for b in report.bull_thesis[:4]:
            print(f"   + {b}")
    if report.bear_thesis:
        print(_c("31;1", " Bear case:", tty))
        for b in report.bear_thesis[:4]:
            print(f"   - {b}")
    if report.monitorables:
        print(_c("33;1", " Monitorables:", tty))
        for m in report.monitorables[:4]:
            print(f"   • {m}")
    if report.warnings:
        print(_c("33", "\n ⚠ " + " ".join(report.warnings), tty))
    print()


def cmd_analyse(args):
    cfg = Config.default()
    cfg.provider = args.provider
    cfg.use_llm = not args.no_llm
    try:
        report = build_report(args.query, cfg)
    except CompanyNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    tty = sys.stdout.isatty()
    if not args.quiet:
        _print_report(report, tty)

    if args.html:
        out = Path(args.html)
        out.write_text(render_dashboard(report), encoding="utf-8")
        print(f" dashboard → {out.resolve()}")
        if args.open:
            webbrowser.open(out.resolve().as_uri())
    if args.json:
        Path(args.json).write_text(report_to_json(report), encoding="utf-8")
        print(f" json      → {Path(args.json).resolve()}")
    return 0


def cmd_research(args):
    from .agent import research
    from .agent.core import CompanyNotFound as _NF  # re-exported build error
    cfg = Config.default()
    cfg.provider = args.provider
    cfg.use_llm = not args.no_llm
    try:
        out = research(args.query, side=args.side, depth=args.depth,
                       market=args.market, config=cfg,
                       coverage_store=args.coverage_store)
    except _NF as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not args.quiet:
        print("\n" + out.product + "\n")
    if args.json:
        import json
        payload = {
            "mandate": {
                "side": out.mandate.side.value,
                "depth": out.mandate.depth.label,
                "market": out.mandate.market.key,
            },
            "company": out.company.ticker,
            "composite_score": out.composite_score,
            "verdict": out.verdict.value,
            "call": {"headline": out.call.headline, "conviction": out.call.conviction,
                     "forensic_gate": out.call.gate},
            "generated_at": out.generated_at,
        }
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f" json → {Path(args.json).resolve()}")
    return 0


def cmd_list(args):
    for c in OfflineProvider().catalogue():
        print(f"  {c.symbol.ljust(12)} {c.name}  ({c.sector or 'n/a'})")
    print("\n  (bundled illustrative snapshots — any other ticker resolves to "
          "synthetic price history)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="stockanalyser",
        description="Multi-lens equity analysis: technical, fundamental, forensic, "
                    "sectoral & qualitative — name in, framework + dashboard out.")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("analyse", help="analyse a company by name or ticker")
    a.add_argument("query", help="company name or ticker, e.g. 'Hitachi Energy' or POWERINDIA")
    a.add_argument("--provider", default="auto",
                   choices=["auto", "offline", "yfinance", "alphavantage", "screener"])
    a.add_argument("--html", metavar="FILE", help="write the HTML dashboard here")
    a.add_argument("--json", metavar="FILE", help="write the machine-readable report here")
    a.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    a.add_argument("--no-llm", action="store_true", help="force deterministic narrative")
    a.add_argument("--quiet", action="store_true", help="suppress the terminal summary")
    a.set_defaults(func=cmd_analyse)

    r = sub.add_parser("research",
                       help="run the research agent (mandate: side × market × depth)")
    r.add_argument("query", help="company name or ticker")
    r.add_argument("--side", choices=["sell-side", "buy-side"], default=None,
                   help="research posture (inferred from the query if omitted)")
    r.add_argument("--depth", default=None,
                   help="L0..L5 or a name (snapshot/screen/brief/deep-dive/initiation/coverage)")
    r.add_argument("--market", default=None,
                   help="market key: US, IN, GB, EU, JP, HK, CN, AU, SG (inferred if omitted)")
    r.add_argument("--coverage-store", default=None, metavar="DIR",
                   help="directory for coverage memory (L4+); default ~/.stockanalyser/coverage")
    r.add_argument("--provider", default="auto",
                   choices=["auto", "offline", "yfinance", "alphavantage", "screener"])
    r.add_argument("--json", metavar="FILE", help="write a machine-readable summary here")
    r.add_argument("--no-llm", action="store_true", help="force deterministic output")
    r.add_argument("--quiet", action="store_true", help="suppress the printed product")
    r.set_defaults(func=cmd_research)

    l = sub.add_parser("list", help="list bundled sample companies")
    l.set_defaults(func=cmd_list)

    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        p.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
