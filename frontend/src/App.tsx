import { Navbar } from "@/sections/Navbar";
// import { Hero } from "@/sections/Hero";
import { StageContainer } from "@/sections/Stages/StageContainer";
// import { CommunitySection } from "@/sections/CommunitySection";
// import { Footer } from "@/sections/Footer";
const bgUrl = new URL("../Minecraft-PS4-Wallpapers-14.jpg", import.meta.url).href;

export const App = () => {
  return (
    <body className="text-zinc-900 text-base not-italic normal-nums font-normal accent-auto bg-stone-50 box-border flex flex-col tracking-[normal] leading-6 list-outside list-disc min-h-[1000px] text-start indent-[0px] normal-case visible border-separate font-cameraplainvariable">
      <div className="box-border hidden"></div>
      <div className="box-border flex basis-[0%] flex-col grow">
        <div className="relative bg-stone-50 box-border min-h-[1000px] w-full">
          <div
            className="absolute box-border w-full overflow-hidden inset-0"
            style={{
              backgroundImage: `url(${bgUrl})`,
              backgroundSize: "cover",
              backgroundPosition: "center",
            }}
          ></div>
          <Navbar />
          <main className="box-border max-w-screen-2xl w-full overflow-hidden mx-auto px-2 md:px-4">
            <div className="relative box-border w-full">
              <StageContainer />
              {/* <CommunitySection /> */}
            </div>
          </main>
          {/* <div className="relative box-border caret-transparent max-w-screen-2xl w-full z-10 mt-6 mb-4 mx-auto px-2 md:px-4">
            <Footer />
          </div> */}
        </div>
        <section
          aria-label="Notifications alt+T"
          className="box-border"
        ></section>
      </div>
      <div className="absolute box-border block"></div>
      <iframe
        title="Netlify identity widget"
        src="about://blank"
        className="fixed box-border hidden h-full w-full z-[99] left-0 top-0"
      ></iframe>
    </body>
  );
};