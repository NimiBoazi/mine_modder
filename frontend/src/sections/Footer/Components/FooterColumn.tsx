export type FooterColumnProps = {
  title: string;
  links: Array<{
    text: string;
    href?: string;
    isButton?: boolean;
    buttonClassName?: string;
  }>;
};

export const FooterColumn = (props: FooterColumnProps) => {
  return (
    <div className="box-border caret-transparent">
      <h3 className="text-zinc-600 text-sm box-border caret-transparent leading-[21px]">
        {props.title}
      </h3>
      <ul className="box-border caret-transparent list-none mt-4 pl-0">
        {props.links.map((link, index) => (
          <li
            key={index}
            className={`box-border caret-transparent text-left ${index > 0 ? "mt-3" : ""}`}
          >
            {link.isButton ? (
              <button
                type="button"
                className={
                  link.buttonClassName ||
                  "text-sm bg-transparent caret-transparent leading-[21px] text-start p-0 hover:text-zinc-600"
                }
              >
                {link.text}
              </button>
            ) : (
              <a
                href={link.href}
                className="text-sm items-start box-border caret-transparent flex leading-[21px] hover:text-zinc-600"
              >
                {link.text}
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};
