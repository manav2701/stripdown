# Signal reference

What each signal type means, where it comes from, and what it misses. Read the
rows for the stacks that apply; skip the rest.

## route

The best proxy for "a thing a user can reach".

| Stack | Where it comes from |
|---|---|
| Next.js app router | `app/**/page.tsx`, `app/**/route.ts` — name is the directory path |
| Next.js pages router | `pages/**/*.tsx` (`_app`, `_document`, `_error` excluded) |
| SvelteKit | `src/routes/**/+page.svelte`, `+server.ts` |
| Remix | `app/routes/**` |
| Nuxt / Astro | `pages/**/*.vue`, `src/pages/**` |
| Rails | `config/routes.rb` (`resources :x`, `get '/x'`), `app/controllers/*_controller.rb` |
| Django | `path(...)` / `re_path(...)` in `urls.py`, plus `<app>/views.py` |
| Laravel | `Route::get(...)` in `routes/*.php`, `app/Http/Controllers/*Controller.php` |
| Express / Fastify / Nest | `app.get('/x')`, `router.post('/x')`, `.route({url})`, `@Controller` |
| FastAPI / Flask | `@app.get("/x")`, `@bp.route("/x")` |
| Spring / ASP.NET | `@GetMapping("/x")`, `[HttpGet("x")]` |
| Go | `HandleFunc("/x")`, chi/echo `.Get("/x")` |
| Phoenix / Axum | `get "/x"` in `router.ex`, `.route("/x", ...)` |

Misses: routes built by string concatenation, registered in a loop, or
generated from config. If the product has a plugin or extension system, its
routes will not appear — ask.

## event

Analytics call sites: `posthog.capture`, `analytics.track`, `mixpanel.track`,
`amplitude.track` / `logEvent`, `gtag('event', ...)`, `trackEvent`,
`rudderanalytics.track`, and the Python `capture(distinct_id, 'event')` shape.

This is the highest-confidence signal here, because event names are almost
always string literals. Use `--names event` to get the full set — that is
effectively the repository's tracking plan, extracted from the code.

Misses: names built by concatenation (`track('user_' + verb)`), events sent
from a server you do not have the source for, and events defined in a
generated analytics wrapper (Avo and similar). Where you see a wrapper, read it
and map through it.

Worth noting: comparing this set against your analytics provider's event list
is a diff nothing else produces. Names in the code but not in the provider mean
the call never fires. Names in the provider but not in the code mean something
else is sending them.

## flag

LaunchDarkly (`boolVariation`, `variation`), PostHog
(`isFeatureEnabled`, `getFeatureFlag`), Unleash (`isEnabled`), Flagsmith
(`hasFeature`), GrowthBook (`isOn`, `getFeatureValue`), Statsig (`checkGate`),
Split (`getTreatment`), plus generic `featureFlags.X` / `flags.X` and
`FEATURE_*` / `ENABLE_*` environment variables. Both camelCase and snake_case
spellings are detected.

A flag that is on for everyone and never read is dead code, and a flag whose
code has been removed is a stale flag. Flag platforms detect that
server-side — this scan finds the call sites, which is the other half. Note
that a flag is usually a *fraction* of a feature, not a feature; do not create
one inventory entry per flag.

## entitlement

Plan and permission gates: `hasPermission`, `require_role`, `@PreAuthorize`,
CanCan `can?(:x)`, `plan === 'enterprise'`, `entitlements.x`, `isPro` /
`isPremium` / `isEnterprise`.

These matter out of proportion to their count: a feature behind a paid tier is
a selling point, so low usage does not mean low value. Tag these features and
set `gates.contractual` with care.

## job

Celery `@shared_task`, Sidekiq workers, BullMQ `new Queue(...)` /
`new Worker(...)`, Spring `@Scheduled`, Django management commands, and cron
expressions in config.

Background work is the classic invisible feature: nobody sees it in the UI,
nothing instruments it, and it runs forever. A scheduled job with no events is
a textbook blind spot — a weekly digest email nobody opens costs real money and
appears in no dashboard.

## webhook

Route-like strings containing `webhook`. Usually an integration surface, so
`gates.public_api` is often `yes`: something outside your codebase depends on
the URL continuing to exist.

## table

`CREATE TABLE`, Django models, SQLAlchemy `__tablename__`, Prisma `model`,
TypeORM `@Entity`, ActiveRecord `create_table`, Knex `createTable`.

A table only written and never read is a strong hint of a feature that was
half-built or abandoned. Checking that is a grep, not an inference — do it
before claiming it.

## cli / graphql

`argparse` sub-parsers, `click` commands, Commander `.command()`, Cobra `Use:`;
GraphQL SDL types and resolver decorators. For a library or developer tool,
these *are* the product surface and the route signals will be empty.

---

## Failure modes worth a manual check

1. **Dead call sites look live.** A flag check inside a function nobody calls
   still shows up. Spot-check anything surprising.
2. **Commented-out code is scanned.** The scan does not strip comments.
3. **Generated and vendored code.** If `dist/`, `gen/` or committed vendor
   directories are tracked, they inflate every count. They are excluded by
   default where they use conventional names; check whether this repo does.
4. **Monorepos.** Run with `--root <package-dir>` per package, or the features
   of several products get mixed into one inventory.
5. **A product whose surface is not in this repo.** Mobile clients, a separate
   frontend, an admin app in another repository. The inventory then covers part
   of the product and must say so.
