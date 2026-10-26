"""Scheduling engine.

    problem.py        pure dataclasses: the solver's input (no DB, no OR-Tools)
    snapshot.py       DB -> Problem
    model_builder.py  Problem -> CP-SAT model (+ rule plugins)
    evaluate.py       pure: check a schedule, compute KPIs and violations
    solve.py          run a T_SolverRuns row end to end and write results
"""
