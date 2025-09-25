import { NavbarLogo } from "@/sections/Navbar/components/NavbarLogo";
import { DesktopNavigation } from "@/sections/Navbar/components/DesktopNavigation";
import { NavbarActions } from "@/sections/Navbar/components/NavbarActions";

export const Navbar = () => {
  return (
    <nav className="sticky items-center box-border caret-transparent flex flex-col justify-between w-full z-50 bg-white/70 backdrop-blur-md border-b border-solid border-stone-200 shadow-sm top-0">
      <div className="items-center box-border caret-transparent flex h-16 justify-between max-w-screen-2xl w-full mx-auto px-2 md:px-4">
        <div className="items-center box-border caret-transparent gap-x-8 flex gap-y-8 pl-0 md:pl-8">
          <NavbarLogo />
          <DesktopNavigation />
        </div>
        <NavbarActions />
      </div>
    </nav>
  );
};
