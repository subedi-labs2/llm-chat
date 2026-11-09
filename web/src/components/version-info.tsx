import type { HealthResponse } from "@/lib/api";

const WEB_VERSION = import.meta.env.VITE_APP_VERSION ?? "dev";
const WEB_COMMIT = import.meta.env.VITE_APP_COMMIT ?? "unknown";

function describe(name: string, version: string, commit: string) {
  return `${name} ${version} (commit ${commit})`;
}

export function VersionInfo({ api }: { api: HealthResponse | null }) {
  const parts = [{ name: "Web", version: WEB_VERSION, commit: WEB_COMMIT }];
  if (api !== null) {
    parts.push({ name: "API", version: api.version, commit: api.commit });
  }

  return (
    <footer className="pb-6 text-center text-xs text-slate-500 dark:text-slate-400">
      {parts.map(({ name, version, commit }, index) => (
        <span key={name}>
          {index > 0 && <span aria-hidden="true"> · </span>}
          <span title={describe(name, version, commit)}>
            {name} {version}
          </span>
        </span>
      ))}
    </footer>
  );
}
