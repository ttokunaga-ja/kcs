# Tidepool activation flow — current specification

**Owner:** Product Design
**Build:** alpha-3.4
**Last reviewed:** 2026-06-22



## Intent

Help a new member produce a useful first weekly plan without requiring a pantry inventory or a long profile form.



## Flow

1. Welcome and one-sentence value framing.
2. Ask for a familiar dinner or a meal the household repeats.
3. Offer optional staples as a starting point, clearly labeled as editable.
4. Show the weekly plan before the shopping list so the resulting list has context.
5. Let the member adjust servings, skip a day, or save the plan for later.



## Interaction rules

- Preserve edits when a member moves backward.
- Keep the shopping list visibly connected to its plan.
- If no staples are chosen, use a calm empty state and offer manual entry.
- Avoid ranking meals as healthy, efficient, or ideal; the participant's routine should lead the choice.



## Research instrumentation

Emit `activation_started`, `starter_meal_added`, `staples_opened`, `plan_previewed`, and `first_list_saved`. Record build tag and session mode, not participant contact data.
