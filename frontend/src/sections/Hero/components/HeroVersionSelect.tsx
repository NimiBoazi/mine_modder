import { useEffect, useRef, useState } from "react";

export function HeroVersionSelect({
  value,
  onChange,
  options,
  label = "Minecraft version",
}: {
  value: string;
  onChange: (next: string) => void;
  options: string[];
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onDocDown = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const target = e.target as HTMLElement | null;
      if (target && containerRef.current.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDocDown);
    return () => document.removeEventListener("mousedown", onDocDown);
  }, []);

  return (
    <div ref={containerRef} className="relative select-none">
      <div className="text-sm text-zinc-700 font-medium mb-1">{label}</div>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={(e) => {
          e.preventDefault();
          setOpen((v) => !v);
        }}
        className="w-full text-left bg-stone-50 text-zinc-900 border border-stone-200 rounded-lg px-3 py-2 text-sm shadow-sm hover:border-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-300"
      >
        <span>{value}</span>
        <span className="float-right text-zinc-500">▾</span>
      </button>

      {open && (
        <div
          role="listbox"
          aria-label={label}
          className="absolute z-20 mt-2 w-full bg-stone-50 border border-stone-200 rounded-xl shadow-[rgba(0,0,0,0.1)_0px_20px_25px_-5px,rgba(0,0,0,0.1)_0px_8px_10px_-6px] overflow-hidden"
        >
          <ul className="max-h-56 overflow-auto py-1">
            {options.map((opt) => {
              const active = opt === value;
              return (
                <li key={opt} className="px-1">
                  <button
                    type="button"
                    className={`w-full text-left rounded-md px-3 py-2 text-sm ${
                      active
                        ? "bg-blue-100 text-zinc-900"
                        : "bg-transparent text-zinc-800 hover:bg-blue-50"
                    }`}
                    onClick={(e) => {
                      e.preventDefault();
                      onChange(opt);
                      setOpen(false);
                    }}
                  >
                    {opt}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

