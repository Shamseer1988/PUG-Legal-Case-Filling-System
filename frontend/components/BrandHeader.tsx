import { ThemeToggle } from './ThemeToggle';

export function BrandHeader() {
  return (
    <header className="border-b-4 border-pug-gold-500 bg-gradient-to-br from-pug-navy-800 via-pug-navy-600 to-pug-navy-500 text-white">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-5">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-pug-gold-500 font-extrabold text-pug-navy-800 shadow-gold">
          PUG
        </div>
        <div className="flex flex-col">
          <span className="text-xs font-semibold uppercase tracking-widest text-pug-gold-300">
            Paris United Group Holding
          </span>
          <h1 className="text-lg font-semibold leading-tight">
            Legal Case Control System
          </h1>
        </div>
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
