"""Nexo Operating Model v3.

A local, deterministic, human-in-the-loop operating system for a single insurance
brokerage in Argentina. Data comes in as an uploaded Excel workbook, is validated
fail-closed, and is snapshotted into a local DuckDB store. Five agents compute
figures deterministically in code (never the model), propose actions, and draft
Spanish prose; a human approves every action. No cloud, no outbound execution.

Three non-negotiables override everything else:
  1. Every number is computed in code, traceable to its inputs. The model never
     produces, estimates, rounds, or fills in a figure.
  2. Human-in-the-loop on every action; approvals are recorded immutably.
  3. It fails closed: missing data / failed validation / low confidence means
     flag and stop, never guess and proceed.
"""

__version__ = "3.0.0"
