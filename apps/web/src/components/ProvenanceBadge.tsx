import type { Provenance } from '../api/client'

const labels: Record<Provenance, string> = {
  measured: '实测',
  estimated: '估算',
  simulated: '仿真',
}

export function ProvenanceBadge({ value, detail }: { value: Provenance; detail?: string }) {
  return (
    <span className={`badge provenance ${value}`} title={detail}>
      {labels[value]}
    </span>
  )
}
