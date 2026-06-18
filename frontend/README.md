# Frontend — PUG Legal Case Control System

Next.js 14 (App Router) + TypeScript + Tailwind.

## Local Setup

```bash
npm install         # or: pnpm install
cp .env.example .env.local
npm run dev
```

Open: http://127.0.0.1:3000

The home page pings the backend at `NEXT_PUBLIC_API_URL` (default
`http://127.0.0.1:8000`) and shows green when the backend is up.

## Scripts

| Script         | Purpose                          |
|----------------|----------------------------------|
| `npm run dev`  | Dev server with hot reload       |
| `npm run build`| Production build                 |
| `npm start`    | Run production build             |
| `npm run lint` | ESLint                           |
| `npm run type-check` | TypeScript only check      |
| `npm run format`| Prettier write                  |

## Theming

- Brand palette: `pug-navy.*` and `pug-gold.*` in `tailwind.config.ts`.
- Light / Dark mode via `next-themes` (system, light, dark) — toggle in the
  header.
