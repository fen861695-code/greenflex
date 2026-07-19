import type { ReactNode } from 'react'

export function PageHeader({
  eyebrow,
  title,
  actions,
}: {
  eyebrow: string
  title: string
  actions?: ReactNode
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}
