# Stage 5C validation checklist

Stage 5C validates the Python MBP end-to-end workflow without adding product features, routes, screens, data model changes, migrations, dependencies, or architecture.

## Automated coverage

- Complete MBP path: signup, current Sprint creation, pasted resume text review and confirmation, AI-assisted draft profile plus user confirmation, AI-assisted opportunity analysis plus company-context skip and opportunity confirmation, evidence extraction and approval, story generation from approved evidence, match generation plus user override confirmation, readiness preview generation, Razorpay webhook payment, Prep Kit generation, successful text practice through the practice service, seven-day plan generation, and Sprint completion.
- Failure and recovery journeys: forbidden workflow transitions, browser-redirect payment claims, invalid webhooks, duplicate webhook replay, Prep Kit generation failure preserving paid entitlement, invalid practice answers, premature plan generation, premature Sprint completion, generated story rejection for unapproved evidence, preview rejection for unapproved evidence references, match grounding to approved story evidence, and generated Prep Kit source-reference preservation.
- Cross-user access: Sprint, resume/document, profile, opportunity, evidence, story, matching, preview, payment checkout, paid artifacts, practice, plan task mutation, and Sprint completion reject records owned by another user and avoid mutating the owner's data.
- Scope leakage: installed apps, model registry, URL patterns, declared dependencies/settings, templates, management commands, and Stage 5C migration filenames are checked for deferred Redis, Celery, pgvector/vector/embedding, social login, expanded billing, notification/calendar, and audio/video practice scope.

## Manual acceptance checks

1. Sign up as a new user and create or reuse the current Interview Sprint.
2. Upload or paste a resume and confirm cleaned text before profile confirmation.
3. Confirm the generated profile before opportunity confirmation.
4. Confirm role context and company/JD analysis before evidence review.
5. Approve evidence before story generation.
6. Generate reusable stories that cite approved evidence only.
7. Confirm story matches before generating the readiness preview.
8. Verify the preview is free while the full Prep Kit stays locked.
9. Start payment and confirm that only a verified Razorpay webhook unlocks `PAID`.
10. Generate the Prep Kit after payment and verify generated material preserves source references.
11. Submit one text practice answer and receive structured feedback.
12. Generate the seven-day improvement plan and complete the Sprint.
13. Sign in as a second user and verify copied URLs or submitted IDs for every stage do not reveal or mutate the first user's data.
14. Confirm no deferred features appear in the UI: social login, subscriptions, coupons, credits, team billing, vector search, audio/video practice, notifications, calendar sync, or PDF export.

## Release-blocking rules

- AI must not change Sprint workflow state directly.
- Browser redirects must not mark payment paid.
- Payment webhooks must validate signatures, order IDs, amount, and currency.
- User-owned records must be filtered by authenticated ownership for every read and mutation.
- Upstream edits may mark dependent outputs stale, but stale paid artifacts must not be destructively deleted.
- Automated tests must use mocks/fakes for OpenAI, payment provider, and company-fetch paths.
