// Canonical open-source links for the project. Single source so the header,
// hero, and footer never drift. These point at the working git remote.
// TODO(owner): confirm the canonical PUBLIC repo URL — this is the working
// remote (`naman-ranka/siliconcrew`); a public mirror may be the OSS home.
export const REPO_URL = "https://github.com/naman-ranka/siliconcrew";
export const ISSUES_URL = `${REPO_URL}/issues`;
export const NEW_ISSUE_URL = `${REPO_URL}/issues/new`;
// README is the closest thing to hosted docs today; retarget when docs ship.
export const DOCS_URL = `${REPO_URL}#readme`;
export const LICENSE_URL = `${REPO_URL}/blob/main/LICENSE`;

// Sourced from README.md badge — NVIDIA CVDP `no_commercial` split, graded in
// the pinned reference container. Honest, not a self-report. Keep in sync with
// the README; do NOT invent a number here.
export const CVDP_RESULT = {
  label: "CVDP no_commercial",
  value: "68.5%",
  detail: "63/92, graded in NVIDIA's reference container (preliminary)",
} as const;
