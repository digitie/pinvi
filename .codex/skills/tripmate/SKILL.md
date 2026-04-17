---
name: tripmate
description: Use when working on TripMate, a travel planning web app. Provides product vocabulary, UX defaults, and implementation guardrails for itinerary, destination, budget, map, and collaboration features.
---

# TripMate Skill

## Product Shape

TripMate helps travelers plan trips from idea to itinerary:

- collect destinations and saved places
- compare dates, costs, travel time, and preferences
- create day-by-day itineraries
- coordinate companions
- track booking state, notes, and logistics

## Core Objects

- `Trip`: destination, date range, companions, budget, planning status
- `ItineraryDay`: one calendar day inside a trip
- `Place`: attraction, restaurant, cafe, hotel, station, airport, or custom stop
- `RouteLeg`: movement between places with duration, mode, and cost
- `BudgetItem`: expected or confirmed cost
- `CompanionPreference`: votes, constraints, must-see items, dietary or accessibility needs

## UX Defaults

- Start from the working surface: current trip, itinerary, saved places, or planning decision.
- Put dates, locations, cost, and travel time close to the action.
- Use compact lists and timelines for planning density.
- Use maps when location relationships matter, but keep the itinerary usable without a map.
- Support uncertain plans with states like `idea`, `shortlisted`, `booked`, and `skipped`.
- Keep collaboration visible through votes, comments, or preference summaries.

## Copy Style

- Short, concrete, travel-specific.
- Prefer "Add stop", "Compare dates", "Book stay", "Share plan", and "Split cost".
- Avoid generic SaaS phrasing such as "unlock productivity" or "streamline your workflow".

## Engineering Guardrails

- Model time zones explicitly when adding date or schedule logic.
- Do not assume all trips are international, solo, leisure, or flight-based.
- Keep costs currency-aware.
- Keep accessibility needs and dietary constraints as normal planning data, not edge cases.
- When integrating external APIs for maps, places, flights, hotels, weather, or AI, document the provider, env vars, rate limits, and fallback behavior.

## Verification Checklist

- Mobile layout supports itinerary editing without horizontal overflow.
- Empty states suggest one clear next action.
- Saved/demo data is visibly sample data.
- Date, currency, and distance formatting are consistent.
