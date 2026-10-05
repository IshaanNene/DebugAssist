// A unified diff, one file per block, coloured by line type.
export function Diff({ diff }: { diff: string }) {
  if (!diff.trim()) return <p className="text-sm text-muted">No diff.</p>;
  const files = diff.split(/^(?=diff --git )/m).filter((f) => f.trim());
  return (
    <div className="space-y-3">
      {files.map((f, i) => {
        const name = f.match(/^diff --git a\/(\S+)/)?.[1] ?? `file ${i + 1}`;
        const lines = f.split("\n").filter((l) => !/^(diff --git|index |--- |\+\+\+ )/.test(l));
        return (
          <details key={i} open className="overflow-hidden rounded border border-line">
            <summary className="cursor-pointer bg-bg px-3 py-1.5 font-mono text-xs">{name}</summary>
            <pre className="overflow-x-auto text-xs leading-5">
              {lines.map((l, j) => (
                <div
                  key={j}
                  className={
                    l.startsWith("+")
                      ? "bg-emerald-500/10 px-3 text-emerald-700 dark:text-emerald-300"
                      : l.startsWith("-")
                        ? "bg-red-500/10 px-3 text-red-700 dark:text-red-300"
                        : l.startsWith("@@")
                          ? "px-3 text-muted"
                          : "px-3"
                  }
                >
                  {l || " "}
                </div>
              ))}
            </pre>
          </details>
        );
      })}
    </div>
  );
}
