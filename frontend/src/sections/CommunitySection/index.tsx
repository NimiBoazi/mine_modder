import { CommunityHeader } from "@/sections/CommunitySection/components/CommunityHeader";
import { ProjectGrid } from "@/sections/CommunitySection/components/ProjectGrid";

export const CommunitySection = () => {
  return (
    <div className="bg-stone-50 box-border caret-transparent gap-x-12 flex flex-col gap-y-12 w-full p-8 rounded-[20px]">
      <div className="box-border caret-transparent gap-x-5 flex flex-col gap-y-5">
        <CommunityHeader />
        <ProjectGrid />
        <div className="box-border caret-transparent flex justify-center">
          <button className="text-sm font-medium items-center bg-stone-50 caret-transparent gap-x-2 flex h-8 justify-center leading-[21px] gap-y-2 text-center text-nowrap border border-stone-200 mt-8 px-4 py-2 rounded-md border-solid hover:bg-zinc-900/20">
            Show More
          </button>
        </div>
      </div>
    </div>
  );
};
