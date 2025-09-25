export const LoadingStage = ({ messages }: { messages: string[] }) => {
  const last = messages[messages.length - 1] || "Working...";
  return (
    <div className="bg-stone-100 shadow-[rgba(0,0,0,0)_0px_0px_0px_0px,rgba(0,0,0,0)_0px_0px_0px_0px,rgba(0,0,0,0.1)_0px_20px_25px_-5px,rgba(0,0,0,0.1)_0px_8px_10px_-6px] box-border caret-transparent gap-x-2 flex flex-col gap-y-2 w-full border border-stone-200 p-3 rounded-[28px] border-solid">
      <div className="box-border caret-transparent flex items-center gap-4">
        {/* Left: loading animation (spinner) */}
        <div className="h-12 w-12 rounded-full border-4 border-zinc-300 border-t-zinc-900 animate-spin" aria-label="loading" />
        {/* Right: current status */}
        <div className="flex-1">
          <div className="text-sm text-zinc-700 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-zinc-400" />
            <span>{last}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

