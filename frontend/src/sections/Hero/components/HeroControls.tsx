export const HeroControls = () => {
  return (
    <div className="items-center box-border caret-transparent gap-x-1 flex flex-wrap gap-y-1">
      <button
        type="button"
        className="text-zinc-600 text-sm font-medium items-center bg-stone-100 caret-transparent gap-x-1.5 flex h-8 justify-center leading-[21px] gap-y-1.5 text-center text-nowrap w-8 border border-stone-200 p-0 rounded-full border-solid hover:text-zinc-900 hover:bg-blue-100 hover:border-blue-100"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 5v14M5 12h14" strokeLinecap="round" />
        </svg>
      </button>


      <div className="items-center box-border caret-transparent gap-x-1 flex gap-y-1 ml-auto">
        <div className="relative items-center box-border caret-transparent gap-x-1 flex gap-y-1 md:gap-x-2 md:gap-y-2">
          <div className="box-border caret-transparent"></div>
          <button
            type="button"
            className="relative text-zinc-600 text-sm font-medium items-center bg-stone-100 caret-transparent gap-x-2 flex h-8 justify-center leading-[21px] gap-y-2 text-center text-nowrap w-8 z-10 border border-stone-200 p-0 rounded-full border-solid hover:bg-blue-100 hover:border-blue-100"
          >
            <span aria-hidden="true" className="text-lg">≡</span>
          </button>
          <button
            type="submit"
            className="items-center bg-zinc-900 caret-transparent flex h-8 justify-center opacity-50 text-center w-8 p-0 rounded-full"
          >
            <span aria-hidden="true" className="text-stone-50">→</span>
          </button>
        </div>
      </div>
    </div>
  );
};
