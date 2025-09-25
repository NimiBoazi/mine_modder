export const CommunityHeader = () => {
  return (
    <div className="box-border caret-transparent gap-x-2 flex flex-col gap-y-2 md:gap-x-4 md:gap-y-4">
      <div className="[align-items:normal] box-border caret-transparent gap-x-2 flex flex-col gap-y-2 w-full md:items-center md:gap-x-4 md:flex-row md:gap-y-4">
        <div className="items-center box-border caret-transparent flex w-full">
          <p className="text-2xl font-medium box-border caret-transparent leading-9">
            From the Community
          </p>
        </div>
      </div>
      <div className="box-border caret-transparent gap-x-2 flex flex-col justify-between gap-y-2 w-full md:gap-x-4 md:flex-row md:gap-y-4">
        <button
          type="button"
          role="combobox"
          className="text-sm items-center bg-transparent shadow-[rgba(0,0,0,0)_0px_0px_0px_0px,rgba(0,0,0,0)_0px_0px_0px_0px,rgba(0,0,0,0.05)_0px_1px_2px_0px] caret-transparent flex h-9 justify-between leading-[21px] text-center text-nowrap w-36 border border-stone-200 px-3 py-2 rounded-md border-solid"
        >
          <span className="box-border caret-transparent flow-root text-nowrap overflow-hidden">
            Popular
          </span>
          <span aria-hidden="true" className="box-border caret-transparent shrink-0 h-4 w-4 opacity-50">v</span>
        </button>
        <div className="box-content caret-black gap-x-[normal] block flex-nowrap min-h-0 min-w-0 gap-y-[normal] md:aspect-auto md:box-border md:caret-transparent md:gap-x-2 md:flex md:flex-wrap md:min-h-[auto] md:min-w-[auto] md:overscroll-x-auto md:overscroll-y-auto md:gap-y-2 md:snap-align-none md:snap-normal md:snap-none md:decoration-auto md:underline-offset-auto md:[mask-position:0%] md:bg-left-top md:scroll-m-0 md:scroll-p-[auto]">
          <div className="text-base font-normal [align-items:normal] bg-transparent box-content caret-black block h-auto leading-[normal] min-h-0 min-w-0 p-0 rounded-none md:text-sm md:font-medium md:items-center md:aspect-auto md:bg-stone-100 md:box-border md:caret-transparent md:flex md:h-9 md:leading-[21px] md:min-h-[auto] md:min-w-[auto] md:overscroll-x-auto md:overscroll-y-auto md:snap-align-none md:snap-normal md:snap-none md:decoration-auto md:underline-offset-auto md:[mask-position:0%] md:bg-left-top md:px-3 md:py-2 md:scroll-m-0 md:scroll-p-[auto] md:rounded-bl md:rounded-br md:rounded-tl md:rounded-tr hover:bg-stone-100/80">
            Discover
          </div>
          <div className="text-base font-normal [align-items:normal] box-content caret-black block h-auto leading-[normal] min-h-0 min-w-0 p-0 rounded-none md:text-sm md:font-medium md:items-center md:aspect-auto md:box-border md:caret-transparent md:flex md:h-9 md:leading-[21px] md:min-h-[auto] md:min-w-[auto] md:overscroll-x-auto md:overscroll-y-auto md:snap-align-none md:snap-normal md:snap-none md:decoration-auto md:underline-offset-auto md:border md:border-stone-200 md:[mask-position:0%] md:bg-left-top md:px-3 md:py-2 md:scroll-m-0 md:scroll-p-[auto] md:rounded-bl md:rounded-br md:rounded-tl md:rounded-tr md:border-solid">
            Internal Tools
          </div>
          <div className="text-base font-normal [align-items:normal] box-content caret-black block h-auto leading-[normal] min-h-0 min-w-0 p-0 rounded-none md:text-sm md:font-medium md:items-center md:aspect-auto md:box-border md:caret-transparent md:flex md:h-9 md:leading-[21px] md:min-h-[auto] md:min-w-[auto] md:overscroll-x-auto md:overscroll-y-auto md:snap-align-none md:snap-normal md:snap-none md:decoration-auto md:underline-offset-auto md:border md:border-stone-200 md:[mask-position:0%] md:bg-left-top md:px-3 md:py-2 md:scroll-m-0 md:scroll-p-[auto] md:rounded-bl md:rounded-br md:rounded-tl md:rounded-tr md:border-solid">
            Website
          </div>
          <div className="text-base font-normal [align-items:normal] box-content caret-black block h-auto leading-[normal] min-h-0 min-w-0 p-0 rounded-none md:text-sm md:font-medium md:items-center md:aspect-auto md:box-border md:caret-transparent md:flex md:h-9 md:leading-[21px] md:min-h-[auto] md:min-w-[auto] md:overscroll-x-auto md:overscroll-y-auto md:snap-align-none md:snap-normal md:snap-none md:decoration-auto md:underline-offset-auto md:border md:border-stone-200 md:[mask-position:0%] md:bg-left-top md:px-3 md:py-2 md:scroll-m-0 md:scroll-p-[auto] md:rounded-bl md:rounded-br md:rounded-tl md:rounded-tr md:border-solid">
            Personal
          </div>
          <div className="text-base font-normal [align-items:normal] box-content caret-black block h-auto leading-[normal] min-h-0 min-w-0 p-0 rounded-none md:text-sm md:font-medium md:items-center md:aspect-auto md:box-border md:caret-transparent md:flex md:h-9 md:leading-[21px] md:min-h-[auto] md:min-w-[auto] md:overscroll-x-auto md:overscroll-y-auto md:snap-align-none md:snap-normal md:snap-none md:decoration-auto md:underline-offset-auto md:border md:border-stone-200 md:[mask-position:0%] md:bg-left-top md:px-3 md:py-2 md:scroll-m-0 md:scroll-p-[auto] md:rounded-bl md:rounded-br md:rounded-tl md:rounded-tr md:border-solid">
            Consumer App
          </div>
          <div className="text-base font-normal [align-items:normal] box-content caret-black block h-auto leading-[normal] min-h-0 min-w-0 p-0 rounded-none md:text-sm md:font-medium md:items-center md:aspect-auto md:box-border md:caret-transparent md:flex md:h-9 md:leading-[21px] md:min-h-[auto] md:min-w-[auto] md:overscroll-x-auto md:overscroll-y-auto md:snap-align-none md:snap-normal md:snap-none md:decoration-auto md:underline-offset-auto md:border md:border-stone-200 md:[mask-position:0%] md:bg-left-top md:px-3 md:py-2 md:scroll-m-0 md:scroll-p-[auto] md:rounded-bl md:rounded-br md:rounded-tl md:rounded-tr md:border-solid">
            B2B App
          </div>
          <div className="text-base font-normal [align-items:normal] box-content caret-black block h-auto leading-[normal] min-h-0 min-w-0 p-0 rounded-none md:text-sm md:font-medium md:items-center md:aspect-auto md:box-border md:caret-transparent md:flex md:h-9 md:leading-[21px] md:min-h-[auto] md:min-w-[auto] md:overscroll-x-auto md:overscroll-y-auto md:snap-align-none md:snap-normal md:snap-none md:decoration-auto md:underline-offset-auto md:border md:border-stone-200 md:[mask-position:0%] md:bg-left-top md:px-3 md:py-2 md:scroll-m-0 md:scroll-p-[auto] md:rounded-bl md:rounded-br md:rounded-tl md:rounded-tr md:border-solid">
            Prototype
          </div>
        </div>
        <div className="box-border caret-transparent flex justify-end w-36 ml-auto md:ml-0">
          <button className="text-sm font-medium items-center bg-transparent caret-transparent gap-x-2 flex h-9 justify-center leading-[21px] gap-y-2 text-center text-nowrap px-4 py-2 rounded-md hover:bg-blue-100">
            <a
              href="/projects/featured"
              className="box-border caret-transparent block text-nowrap"
            >
              View All
            </a>
          </button>
        </div>
      </div>
    </div>
  );
};
