"""Compatibility imports for the legacy notice-plan module name."""

from app.models.curated_plan import CuratedPlanPoi, CuratedTripPlan

NoticePlan = CuratedTripPlan
NoticePoi = CuratedPlanPoi

__all__ = ["CuratedPlanPoi", "CuratedTripPlan", "NoticePlan", "NoticePoi"]
