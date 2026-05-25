from __future__ import annotations

import math


def _confidence_multiplier(forecast_confidence: str) -> float:
    return {"High": 0.75, "Medium": 1.0, "Low": 1.35}.get(forecast_confidence, 1.15)


def estimate_probability_above_threshold(
    threshold: float,
    accumulated: float,
    forecast_remaining: float,
    historical_month_avg: float,
    days_remaining: int,
    forecast_confidence: str,
) -> dict:
    """Transparent MVP model for rainfall threshold probabilities.

    This is not a market-making model. It turns the current projection into a
    smooth probability using forecast uncertainty, time remaining, and local
    monthly climatology as broad guide rails.
    """
    projected_total = accumulated + forecast_remaining
    buffer = projected_total - threshold

    climatology_scale = max(historical_month_avg * 0.18, 0.20)
    time_scale = max(days_remaining, 1) * 0.035
    confidence_scale = _confidence_multiplier(forecast_confidence)
    uncertainty = max((climatology_scale + time_scale) * confidence_scale, 0.12)

    probability = 1 / (1 + math.exp(-(buffer / uncertainty)))

    if accumulated > threshold:
        probability = max(probability, 0.97)
    elif days_remaining <= 2 and projected_total < threshold:
        probability = min(probability, 0.18)

    probability = round(max(0.01, min(probability, 0.99)), 2)

    if forecast_confidence == "Low":
        confidence = "Low"
    elif abs(buffer) <= uncertainty * 0.8:
        confidence = "Medium"
    else:
        confidence = "High"

    if buffer >= 0.25:
        explanation = (
            f"Projected rainfall is {buffer:.2f} inches above the threshold, "
            "so the model leans toward occurrence."
        )
    elif buffer >= -0.25:
        explanation = (
            f"Projected rainfall is only {abs(buffer):.2f} inches from the threshold, "
            "so small forecast changes can move the outcome."
        )
    else:
        explanation = (
            f"Projected rainfall is {abs(buffer):.2f} inches below the threshold, "
            "so more rain is needed before month-end."
        )

    return {
        "probability": probability,
        "confidence": confidence,
        "explanation": explanation,
    }


def recommendation_from_probability(probability: float, confidence: str) -> str:
    if confidence == "Low":
        return "Watch"
    if probability >= 0.70:
        return "Trade"
    if probability >= 0.40:
        return "Watch"
    return "Pass"
