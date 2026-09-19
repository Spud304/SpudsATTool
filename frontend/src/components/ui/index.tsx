import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TableHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import clsx from 'clsx'

/** The one place visual styling lives. Pages compose these; a design pass edits this file. */

export function Panel({
  title,
  actions,
  children,
  className,
  testId,
}: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  testId?: string
}) {
  return (
    <section className={clsx('rounded border border-line bg-panel', className)} data-testid={testId}>
      {title !== undefined ? (
        <header className="flex min-h-9 flex-wrap items-center justify-between gap-x-2 gap-y-1 border-b border-line bg-[var(--panel-head)] px-3 py-1">
          <h2 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--panel-head-fg)]">{title}</h2>
          {actions}
        </header>
      ) : null}
      <div className="p-3">{children}</div>
    </section>
  )
}

type ButtonVariant = 'default' | 'primary' | 'danger' | 'ghost'

export function Button({
  variant = 'default',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      {...props}
      className={clsx(
        'inline-flex h-7 items-center gap-1 rounded border px-2.5 text-[12px] font-medium disabled:cursor-not-allowed disabled:opacity-50',
        variant === 'default' && 'border-line bg-panel-2 hover:border-muted',
        variant === 'primary' && 'border-transparent bg-accent text-accent-fg hover:brightness-110',
        variant === 'danger' && 'border-transparent bg-bad/15 text-bad hover:bg-bad/25',
        variant === 'ghost' && 'border-transparent text-muted hover:bg-panel-2 hover:text-fg',
        className,
      )}
    />
  )
}

export function LinkButton({ href, children, variant = 'primary', testId }: { href: string; children: ReactNode; variant?: ButtonVariant; testId?: string }) {
  return (
    <a
      data-testid={testId}
      href={href}
      className={clsx(
        'inline-flex h-7 items-center rounded border px-2.5 text-[12px] font-medium',
        variant === 'primary' && 'border-transparent bg-accent text-accent-fg hover:brightness-110',
        variant === 'default' && 'border-line bg-panel-2 hover:border-muted',
        variant === 'ghost' && 'border-transparent text-muted hover:text-fg',
      )}
    >
      {children}
    </a>
  )
}

export function Input({ className, invalid, ...props }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      {...props}
      className={clsx(
        'h-7 rounded border bg-bg px-2 text-[12px] text-fg placeholder:text-muted focus:border-accent focus:outline-none',
        invalid ? 'border-warn' : 'border-line',
        className,
      )}
    />
  )
}

export function Textarea({ className, invalid, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  return (
    <textarea
      {...props}
      className={clsx(
        'mono rounded border bg-bg p-2 text-[12px] leading-snug text-fg placeholder:text-muted focus:border-accent focus:outline-none',
        invalid ? 'border-warn' : 'border-line',
        className,
      )}
    />
  )
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={clsx('h-7 rounded border border-line bg-bg px-1.5 text-[12px] text-fg focus:border-accent focus:outline-none', className)}
    />
  )
}

export function Checkbox(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input type="checkbox" {...props} className={clsx('accent-[var(--accent)]', props.className)} />
}

export type Tone = 'muted' | 'ok' | 'warn' | 'bad' | 'info' | 'accent'

export function Badge({ tone = 'muted', children, testId }: { tone?: Tone; children: ReactNode; testId?: string }) {
  return (
    <span
      data-testid={testId}
      className={clsx(
        'inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide',
        tone === 'muted' && 'bg-panel-2 text-muted',
        tone === 'ok' && 'bg-ok/15 text-ok',
        tone === 'warn' && 'bg-warn/15 text-warn',
        tone === 'bad' && 'bg-bad/15 text-bad',
        tone === 'info' && 'bg-info/15 text-info',
        tone === 'accent' && 'bg-accent/15 text-accent',
      )}
    >
      {children}
    </span>
  )
}

/** `hover` tints the row under the pointer so the eye can follow it across a wide list. */
export function Table({ children, className, hover = false, ...props }: TableHTMLAttributes<HTMLTableElement> & { children: ReactNode; hover?: boolean }) {
  return (
    <div className={clsx('overflow-x-auto', className)}>
      <table
        {...props}
        className={clsx(
          'w-full border-collapse text-left text-body [&_td]:border-t [&_td]:border-line [&_td]:px-2 [&_td]:py-1 [&_th]:px-2 [&_th]:py-1 [&_th]:text-[11px] [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-muted',
          hover && '[&_tbody_tr:hover]:bg-panel-2',
        )}
      >
        {children}
      </table>
    </div>
  )
}

export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-0.5 text-[11px] text-muted">
      {label}
      {children}
    </label>
  )
}

/** An empty list or panel: what is missing, one line on why or what to do, and the action that fills it when the viewer may. */
export function Empty({ children, hint, action, testId }: { children: ReactNode; hint?: ReactNode; action?: ReactNode; testId?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-6 text-center text-muted" data-testid={testId}>
      <p>{children}</p>
      {hint ? <p className="text-[12px]">{hint}</p> : null}
      {action ? <div>{action}</div> : null}
    </div>
  )
}

export function ErrorText({ error, testId }: { error: unknown; testId?: string }) {
  if (!error) return null
  return (
    <p className="text-bad" data-testid={testId}>
      {error instanceof Error ? error.message : String(error)}
    </p>
  )
}

export function Mono({ children, className, testId }: { children: ReactNode; className?: string; testId?: string }) {
  return (
    <span className={clsx('mono', className)} data-testid={testId}>
      {children}
    </span>
  )
}
