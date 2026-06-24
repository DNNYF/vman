# VMAN Frontend

Vite + React + TypeScript dashboard for the VMAN secure VPS fleet manager.

## Stack

- **Vite 5** — dev server and production bundler.
- **React 18** + **TypeScript 5** (strict mode).
- **Tailwind CSS 3** + `tailwindcss-animate`.
- **shadcn/ui-style components** — small, dependency-light primitives
  implemented directly in `src/components/ui/` (no CLI / Radix required
  at the foundation level; future tasks can add Radix Slot, Dialog,
  Toast, etc. as needed).
- **react-router-dom 6** for routing.
- **lucide-react** for icons.

## Layout

```
src/
  app/         # AppShell, App router
  components/  # ui/ primitives (Button, Card, Input, …)
  lib/         # cn helper, typed api client
  pages/       # OverviewPage, AuthPages, ErrorPages
  styles/      # globals.css with Tailwind layers and design tokens
```

## Scripts

```bash
npm install
npm run dev      # http://127.0.0.1:5173, proxies /api to :8000
npm run build    # tsc -b && vite build, output in dist/
npm run preview  # serve the built bundle
```

## Environment

The dev server proxies `/api` to `http://127.0.0.1:8000` (the FastAPI
backend). In production, the built `dist/` is intended to be served by
a reverse proxy (Caddy / Nginx / Cloudflare Tunnel) that also routes
`/api` to the backend.

## Status

This is the **Task 15 — frontend foundation** milestone. It provides:

- Buildable Vite + React + TS app.
- Tailwind + shadcn-style design tokens.
- App shell with sidebar navigation and header.
- Stub pages: Overview, Login, Setup, 404, error.
- Typed `api` client with session-cookie and CSRF-token plumbing.
- Health-check ping to the backend on the overview page.

Subsequent tasks (16–25) will add the host, job, recipe, audit, and
backup UIs on top of this foundation.
