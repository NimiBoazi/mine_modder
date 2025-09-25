import { FooterBrand } from "@/sections/Footer/Components/FooterBrand";
import { FooterColumn } from "@/sections/Footer/Components/FooterColumn";

export const FooterContent = () => {
  return (
    <nav className="box-border caret-transparent gap-x-8 grid grid-cols-[repeat(2,minmax(0px,1fr))] gap-y-12 md:grid-cols-[repeat(6,minmax(0px,1fr))]">
      <FooterBrand />
      <FooterColumn
        title="Company"
        links={[
          { text: "Careers", href: "/careers" },
          { text: "Press & media", href: "/brand" },
          { text: "Enterprise", href: "/enterprise" },
          { text: "Security", href: "/security" },
          { text: "Partnerships", href: "/partnerships" },
        ]}
      />
      <FooterColumn
        title="Product"
        links={[
          { text: "Pricing", href: "/pricing" },
          { text: "Student discount", href: "/students" },
          { text: "Solutions", href: "/solutions" },
          { text: "Import from Figma", isButton: true },
          { text: "Changelog", href: "/changelog" },
          { text: "Status", href: "/status" },
        ]}
      />
      <FooterColumn
        title="Resources"
        links={[
          { text: "Learn", href: "/docs" },
          { text: "How-to guides", href: "/how-to" },
          { text: "Videos", href: "/videos" },
          { text: "Blog", href: "/blog" },
          { text: "Launched", href: "/launched" },
          { text: "Support", href: "/support" },
        ]}
      />
      <FooterColumn
        title="Legal"
        links={[
          { text: "Privacy policy", href: "/privacy" },
          {
            text: "Cookie settings",
            href: "/do-not-sell-or-share-my-personal-information",
          },
          { text: "Terms of Service", href: "/terms" },
          { text: "Platform rules", href: "/platform-rules" },
          { text: "Report abuse", href: "/abuse" },
          { text: "Report security concerns", href: "/security" },
        ]}
      />
      <FooterColumn
        title="Community"
        links={[
          { text: "Become a partner", href: "/partners/apply" },
          { text: "Hire a partner", href: "/partners" },
          { text: "Affiliates", href: "/affiliates" },

        ]}
      />
      <div className="box-border caret-transparent block col-end-[span_2] col-start-[span_2] min-h-[auto] min-w-[auto] w-fit md:hidden md:col-end-[span_3] md:col-start-[span_3] md:min-h-0 md:min-w-0">
        <button
          type="button"
          className="text-zinc-600 items-center bg-transparent caret-transparent gap-x-1 flex gap-y-1 text-center p-0 hover:underline"
        >

          <span className="text-sm box-border caret-transparent block leading-[21px] min-h-[auto] min-w-[auto] md:min-h-0 md:min-w-0">
            EN
          </span>
        </button>
      </div>
    </nav>
  );
};
