# Implementation Rules

## 1. Scope Authority

- The Python MBP blueprint is the authority for all implementation stages.
- Any former ten-week production plan is post-MBP backlog only.
- When documents conflict, prefer the MBP documentation that preserves the complete, truthful value loop with the least architecture.

## 2. Architecture Rules

Use:

- Django modular monolith.
- Django ORM.
- Django templates.
- HTMX.
- PostgreSQL.
- Pydantic structured outputs.

Do not use:

- Next.js.
- FastAPI.
- Redis.
- Celery.
- Microservices.
- pgvector.
- Model router.
- Multi-agent framework.

## 3. Django Boundaries

- Views stay thin and handle request/response orchestration only.
- Forms validate user input.
- Services own business rules.
- Models store state.
- Workflow transitions go through one workflow service.
- AI access goes through `EvidraAIService`.
- Do not create generalized abstractions before at least one real consumption point exists.

## 4. Workflow State Rules

Approved Sprint states:

- `DRAFT`
- `RESUME_READY`
- `PROFILE_CONFIRMED`
- `OPPORTUNITY_CONFIRMED`
- `EVIDENCE_REVIEW`
- `EVIDENCE_APPROVED`
- `STORIES_READY`
- `MATCHING_READY`
- `PREVIEW_READY`
- `PAYMENT_PENDING`
- `PAID`
- `PREPKIT_READY`
- `PRACTICE_ACTIVE`
- `PLAN_READY`
- `COMPLETED`

Rules:

- State transitions must be transactional.
- AI output must never change Sprint state directly.
- Browser redirects must never transition a Sprint to `PAID`.
- Invalid transitions fail safely without corrupting prior work.
- Users cannot skip approval stages.

## 5. Ownership Rules

- Direct ownership applies to user-owned entities such as documents, profiles, evidence cards, and stories.
- Inherited ownership applies through `sprint_id`, `profile_id`, `plan_id`, or another parent owned by the user.
- All queries that read or mutate user data must be user-filtered.
- Do not trust browser-submitted IDs without server-side ownership checks.
- Cross-user access tests are required for sensitive entities and workflows.

## 6. AI Rules

AI may:

- Extract profile candidates.
- Analyze JDs.
- Extract one-page company context from approved text.
- Extract evidence candidates.
- Generate stories from approved evidence.
- Score story components.
- Generate preview/prep-kit text from approved inputs.
- Evaluate text practice answers.
- Phrase plan tasks created by deterministic rules.

AI may not:

- Transition workflow state.
- Approve evidence.
- Set payment status.
- Grant access.
- Invent metrics, employers, achievements, or sensitive attributes.
- Remove provenance.
- Perform broad web research.

Every AI operation uses:

- Minimal input.
- Fixed Pydantic schema.
- Validation.
- One retry for structural failures.
- Fake clients in tests.

## 7. Evidence Rules

- Every evidence card requires provenance.
- Metrics must appear in source text or be supplied by user correction.
- AI cannot approve evidence.
- Rejected and unapproved evidence is excluded from stories, matching, preview, Prep Kit, practice, and plans.
- Duplicates are not auto-merged; user review is required.

## 8. Story Rules

- Stories use approved evidence only.
- Stories cannot contain unsupported metrics.
- User edits are preserved.
- Regeneration must not overwrite user-edited stories.
- Stories remain reusable across opportunities.

## 9. Matching Rules

- Match against fixed role-pack keys.
- AI may return component scores.
- Python calculates final score.
- Explicit gaps must be shown.
- User overrides are stored.
- No vector matching or embeddings in the MBP.

## 10. Preview Rules

- The preview is free.
- The preview may include one matched-story excerpt.
- The preview must not include offer probability.
- Paid Prep Kit access is gated by verified payment.

## 11. Payment Rules

- Razorpay is assumed for the first MBP.
- Only verified webhooks can mark a payment `PAID`.
- Webhook handling must be idempotent.
- Failed payment preserves prior work.
- Validate signature, amount, order, and Sprint ownership/entitlement.

## 12. Prep Kit Rules

- Verified payment is required before generation.
- Prep Kit outputs must include source references where applicable.
- Prep Kit must not include unsupported metrics or outcome guarantees.
- Generation failure is recoverable.
- Paid entitlement survives generation failure.

## 13. Practice Rules

- Practice is text only.
- Attempts are append-only.
- Feedback and improved answers cannot invent facts.
- Do not evaluate demographics, appearance, accent, voice, or protected attributes.

## 14. Seven-Day Plan Rules

- Use a Python rule-based plan engine.
- Tasks must be traceable to a weakness, story, evidence card, or question.
- Maximum two major tasks per day.
- Do not create generic confidence tasks.
- AI may phrase deterministic tasks only.

## 15. Staleness Table

| Upstream change | Downstream output marked stale |
| --- | --- |
| Resume replaced or confirmed text edited | Profile draft, evidence, stories, matches, preview, Prep Kit, practice recommendations, plan. |
| Profile edited or reconfirmed | Evidence, stories, matches, preview, Prep Kit, practice recommendations, plan. |
| Opportunity/JD/company context edited | Matches, preview, Prep Kit, question bank, practice priorities, plan. |
| Evidence approved/rejected/edited | Stories, matches, preview, Prep Kit, practice priorities, plan. |
| Story edited/regenerated | Matches, preview, Prep Kit, practice question recommendations, plan. |
| Interview date changed | Seven-day plan and final review timing. |

## 16. Idempotency List

- Resume processing.
- Profile extraction.
- Evidence extraction.
- Story generation.
- Matching.
- Razorpay webhook handling.
- Prep Kit job creation.

## 17. External Service Testing Rules

Mock where needed:

- OpenAI.
- Razorpay.
- Company HTTP fetch.
- Object storage.

Automated tests must not rely on live external services.

## 18. Security Rules

- Do not commit secrets.
- Do not expose stack traces to users.
- Enforce URL safety for company context fetches.
- Validate uploads by extension, MIME, and size.
- Validate payment signatures, amounts, orders, and idempotency.
- Preserve prior work when validation, AI, payment, or external calls fail.
