# TripMate Agent Guide

## Mission

TripMate is a travel planning web app. Help users move from vague travel ideas to a clear itinerary with places, dates, budget, logistics, and companion decisions.

## Product Principles

- Make planning feel lighter, not more bureaucratic.
- Prefer concrete next actions over generic inspiration.
- Keep travel information scannable: dates, places, cost, distance, opening hours, and booking state should be easy to compare.
- Design for collaborative planning. Assume trips may involve multiple people with different preferences.
- Treat safety, accessibility, and realistic logistics as first-class planning constraints.

## Engineering Defaults

- Use Next.js App Router patterns.
- Keep components small and route-focused until duplication proves an abstraction is useful.
- Prefer server components for static or server-fetched content.
- Use client components only for interactivity, browser APIs, or local UI state.
- Keep domain logic testable outside UI components where practical.
- Do not introduce external services, databases, auth, maps, payments, or AI providers without documenting the choice and required environment variables.

## UI Direction

- The first screen should feel like an actual trip planning workspace, not a generic SaaS landing page.
- Use restrained color, strong typography, and clear hierarchy.
- Avoid dashboard-card mosaics. Use cards only for repeated trip items, saved places, modals, or focused tools.
- Keep mobile planning flows comfortable: large tap targets, short labels, and no cramped side-by-side controls.
- Do not show implementation notes, design explanations, or keyboard shortcut instructions in the product UI.

## Verification

Before calling work complete:

- Run `npm run typecheck` when TypeScript changed.
- Run `npm run lint` when UI or app code changed.
- Run `npm run build` before release-oriented changes.
- For visual work, start the dev server and verify the page in a browser when possible.

## Naming

- Product name: TripMate
- Use `trip`, `itinerary`, `place`, `stay`, `route`, `budget`, and `companion` consistently in code and copy.
