import type { ReactNode } from 'react'
import {
  ArrowClockwise,
  CircleNotch,
  Info,
  WarningCircle,
} from '@phosphor-icons/react'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="state-panel compact" role="status">
      <CircleNotch size={18} className="spin" />
      <span>{label}</span>
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="state-panel">
      <span className="state-icon"><Info size={19} /></span>
      <strong>{title}</strong>
      <p>{description}</p>
      {action}
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="state-panel error" role="alert">
      <span className="state-icon"><WarningCircle size={19} /></span>
      <strong>Couldn’t load data</strong>
      <p>{message}</p>
      {onRetry && (
        <button className="secondary-button" onClick={onRetry}>
          <ArrowClockwise size={13} /> Retry
        </button>
      )}
    </div>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase()
  return <span className={`status-text ${normalized}`}>{status}</span>
}
