import { HeroForm } from "@/sections/Hero/components/HeroForm";

export const Hero = () => {
  return (
    <section className="items-center box-border caret-transparent flex flex-col justify-center w-full mb-5 py-[200px] md:mb-0">
      <div className="items-center box-border caret-transparent flex flex-col text-center mb-4 px-4 md:mb-6">
        <div className="items-center box-border caret-transparent gap-x-2 flex flex-col justify-center gap-y-2 w-full"></div>
        <h1 className="text-3xl font-medium items-center box-border caret-transparent gap-x-1 flex leading-[30px] gap-y-1 mb-2 md:text-5xl md:gap-x-0 md:leading-[48px] md:gap-y-0 md:mb-2.5">
          <span className="text-3xl box-border caret-transparent block tracking-[-0.75px] leading-[30px] pt-0.5 md:text-5xl md:tracking-[-1.2px] md:leading-[48px] md:pt-0">
            Mine Modder
            <span className="static text-3xl box-border caret-transparent inline h-auto tracking-[-0.75px] leading-[30px] text-wrap w-auto overflow-visible m-0 md:absolute md:text-5xl md:block md:h-px md:tracking-[-1.2px] md:leading-[48px] md:text-nowrap md:w-px md:overflow-hidden md:-m-px">
              MineModder
            </span>
          </span>

        </h1>
        <p className="text-zinc-900/70 text-lg box-border caret-transparent leading-[22.5px] max-w-[279.053px] mb-6 md:text-xl md:leading-[25px] md:max-w-full">
          Create MineCraft mods with a single prompt
        </p>
      </div>
      <div className="box-border caret-transparent max-w-screen-md w-full">
        <div className="relative box-border caret-transparent w-full">
          <div className="items-center box-border caret-transparent flex flex-col w-full">
            <div className="relative box-border caret-transparent h-full w-full">
              <HeroForm />
            </div>
            <div className="box-border caret-transparent h-10"></div>
          </div>
        </div>
      </div>
    </section>
  );
};
