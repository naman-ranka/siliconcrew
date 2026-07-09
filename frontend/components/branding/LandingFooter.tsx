"use client";

import { Github, CircleDot } from "lucide-react";
import { Logo } from "./Logo";
import { REPO_URL, ISSUES_URL, DOCS_URL, LICENSE_URL } from "./links";

/**
 * Small, standard open-source footer for the `/` landing: mark + the links a
 * credible OSS project carries (GitHub, Issues, Docs, License). No fabricated
 * build stamp or telemetry — only true, external references.
 */
export function LandingFooter() {
  const link = (href: string, label: string, icon?: React.ReactNode) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="inline-flex items-center gap-1 hover:text-foreground"
    >
      {icon}
      {label}
    </a>
  );

  return (
    <footer
      data-testid="landing-footer"
      className="mt-10 pt-5 border-t border-border flex items-center gap-x-5 gap-y-2 flex-wrap text-[11.5px] text-muted-foreground"
    >
      <span className="inline-flex items-center gap-1.5 text-foreground/80">
        <Logo className="h-3.5 w-3.5 text-primary" />
        <span className="font-medium">SiliconCrew</span>
      </span>
      <span className="text-muted-foreground/70">Open source, MIT-licensed</span>
      <div className="ml-auto flex items-center gap-x-5 gap-y-2 flex-wrap">
        {link(REPO_URL, "GitHub", <Github className="h-3.5 w-3.5" />)}
        {link(ISSUES_URL, "Issues", <CircleDot className="h-3.5 w-3.5" />)}
        {link(DOCS_URL, "Docs")}
        {link(LICENSE_URL, "License")}
      </div>
    </footer>
  );
}
