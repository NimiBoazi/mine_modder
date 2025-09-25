export const FooterBrand = () => {
  return (
    <div className="box-border caret-transparent flex flex-row col-end-[span_2] col-start-[span_2] h-full justify-between md:flex-col md:col-end-[span_1] md:col-start-[span_1]">
      <a href="/" className="box-border caret-transparent block w-fit text-xl font-semibold">
        MineModder
      </a>
      <div className="box-border caret-transparent hidden min-h-0 min-w-0 w-fit md:block md:min-h-[auto] md:min-w-[auto]">
        <button
          type="button"
          className="text-zinc-600 items-center bg-transparent caret-transparent gap-x-1 flex gap-y-1 text-center p-0 hover:underline"
        >

          <span className="text-sm box-border caret-transparent block leading-[21px] min-h-0 min-w-0 md:min-h-[auto] md:min-w-[auto]">
            EN
          </span>
        </button>
      </div>
    </div>
  );
};
