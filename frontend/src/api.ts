import type { Document, QueryResponse } from './types'

export async function getDocuments(): Promise<Document[]> {
  const response = await fetch('/api/documents')
  if (!response.ok) throw new Error('Could not load the indexed document')
  return response.json()
}

export async function ask(question: string, documentId: string): Promise<QueryResponse> {
  const response = await fetch('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, document_id: documentId }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || 'The query failed')
  }
  return response.json()
}

