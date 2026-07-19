import { AlertCircle, LoaderCircle } from 'lucide-react'

export function LoadingState({ label = '正在加载' }: { label?: string }) {
  return (
    <div className="page-state" role="status">
      <LoaderCircle className="spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="notice danger" role="alert">
      <AlertCircle aria-hidden="true" />
      <span>{message}</span>
    </div>
  )
}
