"""
Value Metrics Calculator

Calculates value-based investment metrics using Polars DataFrame operations.
Following the modular building blocks approach - small, focused functions.
"""

import polars as pl
from decimal import Decimal


def calculate_value_metrics(fundamentals_df: pl.DataFrame) -> Decimal:
    """
    Calculate composite value score (0-10).

    Value metrics include:
    - P/E ratio (lower is better)
    - P/B ratio (lower is better)
    - P/S ratio (lower is better)
    - PEG ratio (lower is better)
    - EV/EBITDA (lower is better)

    Args:
        fundamentals_df: Polars DataFrame with fundamental data

    Returns:
        Decimal: Value score (0-10, higher is better value)
    """
    if fundamentals_df.is_empty():
        return Decimal("5.0")  # Neutral score if no data

    # Get latest fundamentals
    latest = fundamentals_df.sort("period_end_date", descending=True).head(1)

    # Extract values
    pe = latest.select("pe_ratio").item() if "pe_ratio" in latest.columns else None
    pb = latest.select("pb_ratio").item() if "pb_ratio" in latest.columns else None
    ps = latest.select("ps_ratio").item() if "ps_ratio" in latest.columns else None
    peg = latest.select("peg_ratio").item() if "peg_ratio" in latest.columns else None
    ev_ebitda = latest.select("ev_ebitda").item() if "ev_ebitda" in latest.columns else None

    # Calculate individual scores (invert for valuation ratios - lower is better)
    scores = []

    if pe and pe > 0:
        # P/E score: 0-10 scale (P/E < 10 = 10, P/E > 30 = 0)
        pe_score = max(0, min(10, 10 - (pe - 10) * 0.5))
        scores.append(pe_score)

    if pb and pb > 0:
        # P/B score: 0-10 scale (P/B < 1 = 10, P/B > 5 = 0)
        pb_score = max(0, min(10, 10 - (pb - 1) * 2.5))
        scores.append(pb_score)

    if ps and ps > 0:
        # P/S score: 0-10 scale (P/S < 1 = 10, P/S > 5 = 0)
        ps_score = max(0, min(10, 10 - (ps - 1) * 2.5))
        scores.append(ps_score)

    if peg and peg > 0:
        # PEG score: 0-10 scale (PEG < 1 = 10, PEG > 3 = 0)
        peg_score = max(0, min(10, 10 - (peg - 1) * 5))
        scores.append(peg_score)

    if ev_ebitda and ev_ebitda > 0:
        # EV/EBITDA score: 0-10 scale (< 10 = 10, > 20 = 0)
        ev_score = max(0, min(10, 10 - (ev_ebitda - 10)))
        scores.append(ev_score)

    # Average of available scores
    if not scores:
        return Decimal("5.0")  # Neutral if no valid metrics

    avg_score = sum(scores) / len(scores)
    return Decimal(str(round(avg_score, 2)))


def calculate_pe_score(pe_ratio: float) -> float:
    """
    Calculate P/E ratio score (0-10).

    Single-purpose function following KISS principle.

    Args:
        pe_ratio: Price-to-earnings ratio

    Returns:
        float: Score 0-10 (higher is better value)
    """
    if not pe_ratio or pe_ratio <= 0:
        return 5.0  # Neutral for invalid/negative

    # Scoring logic:
    # P/E < 10: Excellent (10 points)
    # P/E 10-15: Good (7-10 points)
    # P/E 15-20: Fair (5-7 points)
    # P/E 20-30: Poor (2-5 points)
    # P/E > 30: Very poor (0-2 points)

    if pe_ratio < 10:
        return 10.0
    elif pe_ratio < 15:
        return 10.0 - (pe_ratio - 10) * 0.6
    elif pe_ratio < 20:
        return 7.0 - (pe_ratio - 15) * 0.4
    elif pe_ratio < 30:
        return 5.0 - (pe_ratio - 20) * 0.3
    else:
        return max(0.0, 2.0 - (pe_ratio - 30) * 0.1)


def calculate_pb_score(pb_ratio: float) -> float:
    """
    Calculate P/B ratio score (0-10).

    Args:
        pb_ratio: Price-to-book ratio

    Returns:
        float: Score 0-10
    """
    if not pb_ratio or pb_ratio <= 0:
        return 5.0

    # P/B < 1: Excellent (trading below book value)
    # P/B 1-3: Good to fair
    # P/B > 5: Poor (overvalued)

    if pb_ratio < 1:
        return 10.0
    elif pb_ratio < 3:
        return 10.0 - (pb_ratio - 1) * 2.5
    elif pb_ratio < 5:
        return 5.0 - (pb_ratio - 3) * 2.5
    else:
        return max(0.0, 0.5)


def is_undervalued(fundamentals_df: pl.DataFrame, threshold: float = 7.0) -> bool:
    """
    Determine if stock is undervalued based on value score.

    Simple boolean check for filtering.

    Args:
        fundamentals_df: Polars DataFrame with fundamentals
        threshold: Score threshold for "undervalued" (default 7.0)

    Returns:
        bool: True if undervalued
    """
    score = calculate_value_metrics(fundamentals_df)
    return float(score) >= threshold
