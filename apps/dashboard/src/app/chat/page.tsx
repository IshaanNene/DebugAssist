import { api } from "@/lib/api";
import { ApiDown, Badge, Empty, when } from "@/components/ui";

interface Message {
  at: string;
  to: string;
  title: string;
  text: string;
  level: "info" | "success" | "warning" | "alert";
  links: Record<string, string>;
  fields: Record<string, string>;
}

const TONE = { info: "blue", success: "green", warning: "amber", alert: "red" } as const;

export default async function Chat() {
  const messages = await api<Message[]>("/api/inbox");
  return (
    <div className="max-w-3xl space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Chat inbox</h1>
        <p className="text-sm text-muted">
          What DebugAssist posted to the team chat. With <code className="font-mono">DISCORD_WEBHOOK_URL</code> set, these go to
          Discord instead of this local inbox.
        </p>
      </header>
      {messages === null ? (
        <ApiDown />
      ) : messages.length === 0 ? (
        <Empty>No messages yet.</Empty>
      ) : (
        messages.map((m, i) => (
          <article key={i} className="rounded-lg border border-line bg-panel p-4">
            <div className="flex items-center justify-between text-xs text-muted">
              <span>
                to <span className="font-medium text-ink">{m.to}</span>
              </span>
              <span>{when(m.at)}</span>
            </div>
            <div className="mt-2 flex items-start gap-2">
              <Badge tone={TONE[m.level] ?? "gray"}>{m.level}</Badge>
              <h2 className="font-semibold">{m.title}</h2>
            </div>
            <p className="mt-1 text-sm">{m.text}</p>
            {Object.keys(m.fields ?? {}).length > 0 && (
              <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
                {Object.entries(m.fields).map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-muted">{k}</dt>
                    <dd className="truncate">{v}</dd>
                  </div>
                ))}
              </dl>
            )}
            <div className="mt-2 flex gap-3 text-xs">
              {Object.entries(m.links ?? {})
                .filter(([, url]) => url)
                .map(([label, url]) => (
                  <a key={label} href={url} className="text-llm hover:underline">
                    {label}
                  </a>
                ))}
            </div>
          </article>
        ))
      )}
    </div>
  );
}
