import { useRef, useState } from "react";
import { HeroTextarea } from "@/sections/Hero/components/HeroTextarea";
import { HeroControls } from "@/sections/Hero/components/HeroControls";
import { HeroVersionSelect } from "@/sections/Hero/components/HeroVersionSelect";

const AVAILABLE_MC_VERSIONS = [
  "1.21.1",
  "1.21.3",
  "1.21.4",
  "1.21.5",
  "1.21.6",
  "1.21.7",
  "1.21.8",
];

export const HeroForm = ({ onSubmit }: { onSubmit?: (text: string, mcVersion?: string) => void }) => {
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const [mcVersion, setMcVersion] = useState<string>(AVAILABLE_MC_VERSIONS[0]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = inputRef.current?.value?.trim() || "";
    if (onSubmit) onSubmit(text, mcVersion);
  };

  return (
    <form
      onSubmit={handleSubmit}
      onClick={(e) => {
        const el = e.target as HTMLElement;
        // Do NOT steal focus when interacting with form controls
        if (el.closest("button, select, textarea, input, a, [role='button'], label, option")) return;
        inputRef.current?.focus();
      }}
      className="bg-stone-100 shadow-[rgba(0,0,0,0)_0px_0px_0px_0px,rgba(0,0,0,0.1)_0px_20px_25px_-5px,rgba(0,0,0,0.1)_0px_8px_10px_-6px] box-border gap-x-2 flex flex-col gap-y-2 w-full border border-stone-200 p-3 rounded-[28px] border-solid cursor-text"
    >
      <HeroTextarea ref={inputRef} />
      <div className="flex items-center justify-between gap-2 mt-1">
        <div className="w-full md:w-64">
          <HeroVersionSelect
            value={mcVersion}
            onChange={setMcVersion}
            options={AVAILABLE_MC_VERSIONS}
          />
        </div>
      </div>
      <HeroControls />
    </form>
  );
};
