import { CommunityFilters } from "@/sections/CommunitySection/components/CommunityFilters";

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
      <CommunityFilters />
    </div>
  );
};
