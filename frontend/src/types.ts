export type Document = {
  id: string; title: string; filename: string; page_count: number; status: string
}

export type Evidence = {
  evidence_id: string
  child_id: string
  page: number
  section: string[]
  element_type: string
  content: string
  score: number
  image_url?: string
}

export type QueryResponse = {
  answer: string
  insufficient_evidence: boolean
  citations: { evidence_id: string; page: number; section?: string; image_url?: string }[]
  retrieved_evidence: Evidence[]
  calculations: { operation: string; value: string; expression: string }[]
  timings_ms: Record<string, number>
}

