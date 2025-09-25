import React from "react";

export const HeroTextarea = React.forwardRef<HTMLTextAreaElement, { placeholder?: string }>(
  ({ placeholder = "Ask MineModder to create a mod that..." }, ref) => {
    return (
      <div className="relative items-center box-border flex basis-[0%] grow">
        <textarea
          ref={ref}
          placeholder={placeholder}
          className="bg-transparent box-border caret-zinc-900 flex basis-[0%] grow h-20 leading-[22px] max-h-[200px] min-h-20 text-ellipsis text-nowrap w-full p-2 rounded-md focus:outline-none"
        ></textarea>
      </div>
    );
  }
);

HeroTextarea.displayName = "HeroTextarea";
